"""Story 3.4 AC3 end-to-end: the held-package sweep runs at pipeline start.

Writes a synthetic expired held package under the staged `out_root`, fires
POST /api/paste, and asserts the expired directory is gone + the audit log
has the expected JSON-lines entry.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient

from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.held_package import AUDIT_LOG_NAME, HELD_SIDECAR_NAME
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
)


FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)


def _write_expired_held_fixture(
    out_root: Path,
    slug: str,
    *,
    held_at: datetime,
    expires_at: datetime,
    failed_claims_count: int = 2,
) -> Path:
    """Synthesise a held package under out_root/slug/ with set timestamps."""
    pkg = out_root / slug
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "cv.md").write_text("stale\n", encoding="utf-8")
    (pkg / "cover-letter.md").write_text("stale\n", encoding="utf-8")
    (pkg / HELD_SIDECAR_NAME).write_text(
        json.dumps(
            {
                "held_at": held_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "held_by_check": "fabrication",
                "failed_claims": [{"x": i} for i in range(failed_claims_count)],
                "retention_expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "recoverable": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return pkg


def _passing_extractor() -> Callable[..., ClaimExtractionResult]:
    """Extractor that emits no claims so the new package passes the matcher."""

    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        return ClaimExtractionResult(
            claims=[],
            cost_usd=Decimal("0.000050"),
            input_tokens=5,
            output_tokens=3,
        )

    return fake_extract


def _stage(tmp_path, monkeypatch, *, cv: str = "hi\n", cover: str = "hi\n"):
    import jobhunter.web.api as api_module

    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
    )
    inner_run = api_module.run_tailoring

    def wrapped(canonical_cv, jd_text, **kwargs):
        kwargs.setdefault("llm_extract_claims", _passing_extractor())
        return inner_run(canonical_cv, jd_text, **kwargs)

    monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root


def _post_paste() -> int:
    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    return response.status_code


# ---- AC3: expired held packages are swept before any LLM work -----------


def test_pipeline_sweeps_expired_held_package_at_start(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root = _stage(tmp_path, monkeypatch)

    # Plant an expired held package: retention window ended 3 days ago.
    expired_pkg = _write_expired_held_fixture(
        out_root,
        "20260514t000000z-stale",
        held_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        expires_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    assert expired_pkg.exists()

    status = _post_paste()
    assert status == 200
    assert not expired_pkg.exists(), "expired held package directory should be gone"


def test_pipeline_writes_audit_log_entry_for_each_discard(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root = _stage(tmp_path, monkeypatch)

    _write_expired_held_fixture(
        out_root,
        "20260514t000000z-stale",
        held_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        expires_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        failed_claims_count=4,
    )

    _post_paste()
    audit_path = out_root / AUDIT_LOG_NAME
    assert audit_path.is_file()
    lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["slug"] == "20260514t000000z-stale"
    assert entry["held_at"] == "2026-05-14T00:00:00Z"
    assert entry["failed_claims_count"] == 4
    # The discarded_at timestamp is ISO 8601 UTC with `Z`.
    assert entry["discarded_at"].endswith("Z")


def test_pipeline_preserves_fresh_held_packages(tmp_path, monkeypatch) -> None:
    """A held package still inside its retention window survives the sweep."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root = _stage(tmp_path, monkeypatch)

    # Plant a held package whose retention is far in the future.
    fresh_pkg = _write_expired_held_fixture(
        out_root,
        "20260601t000000z-fresh",
        held_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2030, 1, 8, tzinfo=timezone.utc),
    )
    _post_paste()
    assert fresh_pkg.exists()
    audit_path = out_root / AUDIT_LOG_NAME
    if audit_path.exists():
        assert audit_path.read_text(encoding="utf-8") == ""


def test_pipeline_sweep_discards_only_expired_among_mixed_packages(
    tmp_path, monkeypatch,
) -> None:
    """A sweep can discard one slug and preserve another in the same run."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root = _stage(tmp_path, monkeypatch)

    stale = _write_expired_held_fixture(
        out_root,
        "20260514t000000z-stale",
        held_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        expires_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
    )
    fresh = _write_expired_held_fixture(
        out_root,
        "20260601t000000z-fresh",
        held_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2030, 1, 8, tzinfo=timezone.utc),
    )

    _post_paste()

    assert not stale.exists()
    assert fresh.exists()

    audit = (out_root / AUDIT_LOG_NAME).read_text(encoding="utf-8")
    audit_entries = [json.loads(line) for line in audit.splitlines() if line.strip()]
    audit_slugs = [e["slug"] for e in audit_entries]
    assert audit_slugs == ["20260514t000000z-stale"]


def test_pipeline_sweep_does_not_touch_passed_packages(tmp_path, monkeypatch) -> None:
    """A directory without `package.held.json` is left strictly alone."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root = _stage(tmp_path, monkeypatch)

    passed_pkg = out_root / "20260101t000000z-passed"
    passed_pkg.mkdir(parents=True)
    (passed_pkg / "cv.md").write_text("Python\n", encoding="utf-8")
    (passed_pkg / "metadata.json").write_text(
        json.dumps({"held": False}), encoding="utf-8"
    )

    _post_paste()

    assert passed_pkg.exists()
    assert (passed_pkg / "cv.md").exists()


def test_pipeline_sweep_failure_does_not_abort_pipeline(
    tmp_path, monkeypatch, caplog,
) -> None:
    """Best-effort contract: sweep failures are logged but never abort the pipeline."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root = _stage(tmp_path, monkeypatch)

    # Make the sweep raise by monkeypatching it. The pipeline must still
    # complete and return 200.
    import jobhunter.tailoring as tailoring_module

    def boom(*_args, **_kwargs):
        raise RuntimeError("sweep exploded")

    monkeypatch.setattr(
        tailoring_module.held_package, "sweep_expired", boom
    )

    status = _post_paste()
    assert status == 200
    # A new package directory should have been written despite the sweep
    # blowing up, proving the sweep failure is non-fatal.
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) >= 1
