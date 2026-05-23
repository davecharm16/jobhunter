"""Story 3.1 AC4: extraction-timeout end-to-end through POST /api/paste.

On `ClaimExtractionTimedOut`, `run_tailoring`:
- writes a minimal metadata sidecar with `error="extraction_timeout"`,
- does NOT write `claims.json` (no partial extraction data on disk),
- re-raises so the FastAPI route surfaces a 502.

The 502 wire comes from `ClaimExtractionTimedOut` extending `LLMCallTimedOut`
which extends `LLMCallFailed` — same path `ParseTimedOut` uses (Story 2.3).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from jobhunter.claim_extractor import ClaimExtractionTimedOut
from jobhunter.web.api import create_app
from tests.integration._web_helpers import (
    stage_canonical_cv,
    stage_tailoring,
)


def _timing_out_extractor(
    markdown_text, source_artifact, *, api_key, timeout_seconds, prompt,
):
    raise ClaimExtractionTimedOut("simulated extraction timeout")


def _stage_with_timeout(tmp_path, monkeypatch):
    import jobhunter.web.api as api_module

    out_root, ledger_path = stage_tailoring(tmp_path, monkeypatch)
    inner_run = api_module.run_tailoring

    def wrapped(canonical_cv, jd_text, **kwargs):
        kwargs.setdefault("llm_extract_claims", _timing_out_extractor)
        return inner_run(canonical_cv, jd_text, **kwargs)

    monkeypatch.setattr(api_module, "run_tailoring", wrapped)
    return out_root, ledger_path


def test_paste_extraction_timeout_returns_502(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    _stage_with_timeout(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    # ClaimExtractionTimedOut -> LLMCallFailed -> 502 (per FastAPI handler in
    # web/api.py, untouched by Story 3.1).
    assert response.status_code == 502
    assert "LLM call failed" in response.json()["detail"]


def test_paste_extraction_timeout_writes_minimal_failure_sidecar(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = _stage_with_timeout(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    metadata_path = slug_dir / "metadata.json"
    assert metadata_path.exists()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["error"] == "extraction_timeout"


def test_paste_extraction_timeout_does_not_write_claims_json(
    tmp_path, monkeypatch,
) -> None:
    """AC4: no partial extraction data on disk."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = _stage_with_timeout(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    assert not (slug_dir / "claims.json").exists()
    # Tailored markdown artifacts ARE present — that's the held-package
    # precondition Story 3.4 picks up.
    assert (slug_dir / "cv.md").exists()
    assert (slug_dir / "cover-letter.md").exists()


def test_extraction_timeout_does_not_leak_claims_tmp(tmp_path, monkeypatch) -> None:
    """The atomic write idiom (tmp + os.replace) must not leave .claims.tmp
    behind when the extractor blows up mid-call. The first extraction call
    raises before any write happens, so no tmp file is created — this test
    pins that invariant."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = _stage_with_timeout(tmp_path, monkeypatch)

    client = TestClient(create_app(), raise_server_exceptions=False)
    client.post(
        "/api/paste",
        json={"jd_text": "Senior Python role.\n", "source": "browser"},
    )
    slug_dir = next(p for p in out_root.iterdir() if p.is_dir())
    files = {p.name for p in slug_dir.iterdir()}
    assert ".claims.tmp" not in files
