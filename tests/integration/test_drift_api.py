"""GET /api/package/<slug>/drift tests (Story 3.5).

The route reads `./out/<slug>/package.drift.json` on every request and returns
it verbatim. These tests stage per-test `./out/<slug>/` trees under `tmp_path`,
point the route module's `OUT_ROOT` at them via `monkeypatch`, and exercise
the FastAPI app in-process via `TestClient`.

Covers AC1:
- 200 with the parsed drift document when the file is present.
- 404 when the slug directory exists but no `package.drift.json` sidecar
  (e.g. Epic 1 walking-skeleton runs that predate the fabrication matcher).
- 404 when the slug directory does not exist at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from jobhunter.web.routes import drift as drift_module


@pytest.fixture
def staged_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the drift route's OUT_ROOT at a per-test tmp directory."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    monkeypatch.setattr(drift_module, "OUT_ROOT", out_root)
    return out_root


def _write_drift(out_root: Path, slug: str, doc: dict[str, Any]) -> Path:
    package_dir = out_root / slug
    package_dir.mkdir()
    drift_path = package_dir / "package.drift.json"
    drift_path.write_text(json.dumps(doc), encoding="utf-8")
    return drift_path


def _fab_pass() -> dict[str, Any]:
    return {
        "fabrication_check": {
            "verdict": "pass",
            "claims_total": 1,
            "claims_sourced": 1,
            "claims_unsourced": 0,
            "traces": [
                {
                    "claim_id": "cv:1:abc12345",
                    "claim_text": "Python",
                    "matched_canonical_entry_id": "skills[0].keywords[0]:abc12345",
                    "match_method": "exact_string",
                    "match_score": 1.0,
                },
            ],
            "unsourced_claims": [],
        },
    }


def _fab_fail() -> dict[str, Any]:
    return {
        "fabrication_check": {
            "verdict": "fail",
            "claims_total": 1,
            "claims_sourced": 0,
            "claims_unsourced": 1,
            "traces": [],
            "unsourced_claims": [
                {
                    "claim_id": "cv:9:deadbeef",
                    "claim_text": "led a 47-person engineering platform org",
                    "source_artifact": "cv",
                    "line_number": 9,
                    "reason": "no_canonical_match",
                },
            ],
        },
    }


# ---- AC1: 200 with the parsed drift document -----------------------------


def test_get_drift_returns_pass_document(staged_out_root: Path) -> None:
    slug = "2026-05-23-acme-pass-abcdef"
    doc = _fab_pass()
    _write_drift(staged_out_root, slug, doc)

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}/drift")

    assert response.status_code == 200
    assert response.json() == doc


def test_get_drift_returns_fail_document_with_unsourced_claims(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-acme-fail-cafe12"
    doc = _fab_fail()
    _write_drift(staged_out_root, slug, doc)

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}/drift")

    assert response.status_code == 200
    body = response.json()
    assert body["fabrication_check"]["verdict"] == "fail"
    unsourced = body["fabrication_check"]["unsourced_claims"]
    assert len(unsourced) == 1
    assert unsourced[0]["reason"] == "no_canonical_match"
    assert unsourced[0]["source_artifact"] == "cv"
    assert unsourced[0]["line_number"] == 9


def test_get_drift_preserves_future_sibling_keys(staged_out_root: Path) -> None:
    """Story 4.4/5.4 will add sibling keys; the route returns them verbatim."""
    slug = "2026-05-23-future-siblings-fedcba"
    doc = {
        "fabrication_check": _fab_pass()["fabrication_check"],
        "content_loss": {"verdict": "pending"},
        "keyword_stuffing": {"verdict": "pending"},
    }
    _write_drift(staged_out_root, slug, doc)

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}/drift")

    assert response.status_code == 200
    body = response.json()
    assert "fabrication_check" in body
    assert "content_loss" in body
    assert "keyword_stuffing" in body


# ---- AC1: 404 when slug directory exists but no drift sidecar -----------


def test_get_drift_returns_404_when_drift_sidecar_missing(
    staged_out_root: Path,
) -> None:
    """Epic 1 walking-skeleton runs predate the matcher: dir exists, no drift."""
    slug = "2026-05-23-no-drift-abcdef"
    package_dir = staged_out_root / slug
    package_dir.mkdir()
    (package_dir / "cv.md").write_text("# CV\n", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}/drift")

    assert response.status_code == 404
    assert "package_drift_not_found" in response.json()["detail"]


# ---- AC1: 404 when slug directory itself does not exist -----------------


def test_get_drift_returns_404_for_unknown_slug(
    staged_out_root: Path,
) -> None:
    client = TestClient(create_app())
    response = client.get("/api/package/does-not-exist/drift")

    assert response.status_code == 404
    assert "package_not_found" in response.json()["detail"]


# ---- AC1: 500 when drift sidecar is malformed JSON ----------------------


def test_get_drift_returns_500_when_drift_malformed(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-bad-drift-abcdef"
    package_dir = staged_out_root / slug
    package_dir.mkdir()
    (package_dir / "package.drift.json").write_text(
        "not json {{{", encoding="utf-8"
    )

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}/drift")

    assert response.status_code == 500
    assert "package_drift_malformed" in response.json()["detail"]
