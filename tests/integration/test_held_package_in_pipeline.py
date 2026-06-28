"""Story 3.4 AC1 + AC2 + AC4 end-to-end: held-package writer in the pipeline.

Drives the whole pipeline through POST /api/paste with a fabricated claim so
the matcher emits `fail`, then asserts:

- AC1: `package.held.json` lands next to the existing artifacts with the
  documented shape (held_at, held_by_check, failed_claims, retention_expires_at,
  recoverable).
- AC2: `metadata.json` carries `held: true` + `held_path`, and the held
  branch never imports a notification module (structural contract).
- AC4: a fabrication=fail still returns HTTP 200 — the package is held,
  not a pipeline error — and no code path turns a held package into "passed".
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_tailor,
    stage_canonical_cv,
    stage_tailoring,
)

import jobhunter.tailoring as tailoring_module
from jobhunter.claim_extractor import Claim, ClaimExtractionResult
from jobhunter.web.api import create_app


def _make_extractor(cv_claims, cover_claims) -> Callable[..., ClaimExtractionResult]:
    def fake_extract(
        markdown_text: str,
        source_artifact: str,
        *,
        api_key: str,
        timeout_seconds: float,
        prompt: Any,
    ) -> ClaimExtractionResult:
        raw = cv_claims if source_artifact == "cv" else cover_claims
        claims = [
            Claim(
                claim_id=f"{source_artifact}:{c['line_number']}:abcdef01",
                claim_type=c["claim_type"],
                claim_text=c["claim_text"],
                source_artifact=source_artifact,
                line_number=c["line_number"],
            )
            for c in raw
        ]
        return ClaimExtractionResult(
            claims=claims,
            cost_usd=Decimal("0.000420"),
            input_tokens=42,
            output_tokens=21,
        )

    return fake_extract


def _stage(tmp_path, monkeypatch, *, extractor, cv: str, cover: str):
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_tailor=make_fake_tailor(cv=cv, cover=cover),
    )

    inner_run = api_module.run_tailoring

    def wrapped(canonical_cv, jd_text, **kwargs):
        kwargs.setdefault("llm_extract_claims", extractor)
        return inner_run(canonical_cv, jd_text, **kwargs)

    monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root, ledger_path


def _post_paste(tmp_path, monkeypatch, *, cv: str, cover: str, cv_claims, cover_claims):
    """Convenience: stage + POST /api/paste in one call; return slug_dir."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    extractor = _make_extractor(cv_claims=cv_claims, cover_claims=cover_claims)
    out_root, _ = _stage(
        tmp_path, monkeypatch, extractor=extractor, cv=cv, cover=cover
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    return slug_dir, response


# ---- AC1: package.held.json shape ---------------------------------------


def test_paste_writes_package_held_json_on_fabrication_fail(
    tmp_path, monkeypatch,
) -> None:
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    held_path = slug_dir / "package.held.json"
    assert held_path.exists(), (
        f"package.held.json missing; out_dir contents: {list(slug_dir.iterdir())}"
    )


def test_held_json_carries_documented_top_level_fields(tmp_path, monkeypatch) -> None:
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    data = json.loads((slug_dir / "package.held.json").read_text(encoding="utf-8"))
    # Story 4.2: `dropped_high_impact_entries` is additive (AC6 path b) so
    # the held sidecar can also carry the content-loss check's `silently_lost`
    # drops. Fabrication-only fails (this test) leave it empty.
    # Story 5.3: `keyword_stuffing_violations` is additive (AC4) so the held
    # sidecar can also carry the keyword-stuffing check's density + placement
    # violations. Fabrication-only fails (this test) leave it empty too.
    assert set(data.keys()) == {
        "held_at",
        "held_by_check",
        "failed_claims",
        "retention_expires_at",
        "recoverable",
        "dropped_high_impact_entries",
        "keyword_stuffing_violations",
    }
    assert data["held_by_check"] == "fabrication"
    assert data["recoverable"] is True
    assert data["dropped_high_impact_entries"] == []
    assert data["keyword_stuffing_violations"] == []
    # ISO 8601 UTC with `Z` suffix.
    assert data["held_at"].endswith("Z")
    assert data["retention_expires_at"].endswith("Z")


def test_held_json_failed_claims_pin_artifact_path_and_columns(
    tmp_path, monkeypatch,
) -> None:
    """AC1: each failed claim carries `{artifact_path, line, column_start, column_end}`."""
    cv_markdown = "# CV\nled a 47-person engineering platform org\n"
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv=cv_markdown,
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 2,
            }
        ],
        cover_claims=[],
    )
    data = json.loads((slug_dir / "package.held.json").read_text(encoding="utf-8"))
    failed = data["failed_claims"]
    assert len(failed) == 1
    fc = failed[0]
    assert fc["source_artifact"] == "cv"
    assert fc["line_number"] == 2
    assert fc["artifact_path"] == str(slug_dir / "cv.md")
    # The claim starts at column 0 of line 2 ("led a 47-person ..."), and
    # ends at the length of the claim text.
    assert fc["column_start"] == 0
    assert fc["column_end"] == len("led a 47-person engineering platform org")


def test_held_json_mirrors_unsourced_claims_from_drift_report(
    tmp_path, monkeypatch,
) -> None:
    """AC1: `failed_claims[]` mirrors `unsourced_claims[]` from the drift report."""
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    drift = json.loads(
        (slug_dir / "package.drift.json").read_text(encoding="utf-8")
    )
    held = json.loads(
        (slug_dir / "package.held.json").read_text(encoding="utf-8")
    )
    unsourced_ids = sorted(
        c["claim_id"] for c in drift["fabrication_check"]["unsourced_claims"]
    )
    held_ids = sorted(c["claim_id"] for c in held["failed_claims"])
    assert held_ids == unsourced_ids
    assert len(held_ids) >= 1


# ---- AC1: held package is atomic — no .package.held.tmp left behind -----


def test_paste_held_json_has_no_dot_tmp_left_behind(tmp_path, monkeypatch) -> None:
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    names = {p.name for p in slug_dir.iterdir()}
    assert "package.held.json" in names
    assert ".package.held.tmp" not in names


# ---- AC2: metadata records held=true + held_path -----------------------


def test_paste_metadata_records_held_true_on_fabrication_fail(
    tmp_path, monkeypatch,
) -> None:
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is True
    assert metadata["held_path"] == str(slug_dir / "package.held.json")
    assert metadata["drift_verdicts"]["fabrication"] == "fail"


def test_paste_metadata_held_stays_false_on_fabrication_pass(
    tmp_path, monkeypatch,
) -> None:
    """When every claim is sourced, the metadata reports held=false + held_path=None."""
    # Story 5.3: CV/cover bodies extended with ~80-token prose filler so
    # the new keyword-stuffing density check (Stories 5.1-5.3) doesn't trip
    # on a short body where "python" would land above the 1.5% density
    # threshold. Adding filler keeps fabrication the only drift dimension
    # this test cares about.
    # ~100 distinct tokens — the keyword-stuffing matcher tokenizer is
    # picky about identifier shape; the Greek-alphabet padding sidesteps
    # any stop-word / short-token filtering surprises.
    filler = (
        " alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
        "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega "
    ) * 4
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="Python developer with broad experience" + filler + "\n",
        cover="Hello there, I am writing to express interest" + filler + "\n",
        cv_claims=[
            {"claim_type": "skill", "claim_text": "Python", "line_number": 1},
        ],
        cover_claims=[],
    )
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is False
    assert metadata["held_path"] is None
    # The held-package sidecar is not written on a pass.
    assert not (slug_dir / "package.held.json").exists()


# ---- AC2 structural: tailoring.py held branch imports no notify module --


def test_tailoring_module_does_not_import_any_notification_module() -> None:
    """Structural enforcement: `tailoring.py` never imports a notify surface.

    The held-package writer is the entire post-matcher branch on fail; if
    `tailoring.py` imports nothing notification-related, no held-state path
    can fire a notification — even by accident.
    """
    source = Path(tailoring_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = ("notify", "gchat", "google_chat", "webhook")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                lowered = alias.name.lower()
                for needle in forbidden:
                    assert needle not in lowered, (
                        f"tailoring.py imports forbidden module: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = (node.module or "").lower()
            for needle in forbidden:
                assert needle not in module_name, (
                    f"tailoring.py imports from forbidden module: {node.module}"
                )


# ---- AC4: hard-fail policy ---------------------------------------------


def test_paste_returns_200_even_when_package_is_held(tmp_path, monkeypatch) -> None:
    """AC4: held vs passed is a metadata distinction, not a route-level error."""
    _, response = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    assert response.status_code == 200


def test_paste_held_package_artifacts_remain_on_disk(tmp_path, monkeypatch) -> None:
    """AC4: artifacts stay on disk when the package is held (recoverable=true)."""
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    names = {p.name for p in slug_dir.iterdir()}
    assert {
        "cv.md",
        "cover-letter.md",
        "claims.json",
        "package.drift.json",
        "package.held.json",
        "metadata.json",
    }.issubset(names)


def test_no_code_path_promotes_held_package_to_passed(tmp_path, monkeypatch) -> None:
    """AC4: no code path promotes a HELD package to PASSED.

    Asserts the contract on disk: when metadata.held is true,
    drift_verdicts.fabrication is "fail" and a `package.held.json` sidecar
    exists alongside. Verifies the only way to "release" a held package
    is via Epic 6's override path — which is not implemented in Epic 3.
    """
    slug_dir, _ = _post_paste(
        tmp_path,
        monkeypatch,
        cv="led a 47-person engineering platform org\n",
        cover="hi\n",
        cv_claims=[
            {
                "claim_type": "metric",
                "claim_text": "led a 47-person engineering platform org",
                "line_number": 1,
            }
        ],
        cover_claims=[],
    )
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["held"] is True
    # No code path in Epic 3 sets `override.applied=True` — the override
    # release mechanism is Epic 6, Story 6.4.
    assert metadata["override"] == {"applied": False, "reason": None}
    # The held sidecar must coexist with the held metadata flag.
    assert (slug_dir / "package.held.json").exists()
