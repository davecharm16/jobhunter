"""GET /api/drift/history integration tests (Story D3).

`GET /api/drift/history` reads every `./out/<slug>/metadata.json` (and
`./out/_overridden/<slug>/metadata.json`) plus the co-located
`package.drift.json` sidecars and returns a list of per-package drift
summary rows sorted newest-first by `created_at`.

Covers:
- Empty out/ → {"checks": []}, 200.
- Two staged packages with drift sidecars → two rows, newest-first, correct
  verdicts + held flag.
- A package dir missing `package.drift.json` → row present with verdicts
  omitted/empty, no 500.

Staging pattern mirrors `test_stats_api.py`: tmp + monkeypatch PROJECT_ROOT
via `jobhunter.config`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app


# ---- fixture helpers -------------------------------------------------------


def _stage_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point PROJECT_ROOT at *tmp_path* so `./out/` resolves into the fixture."""
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)

    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    return out_root


def _write_metadata(out_root: Path, payload: dict[str, Any]) -> Path:
    slug = payload["slug"]
    slug_dir = out_root / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_drift(out_root: Path, slug: str, doc: dict[str, Any]) -> Path:
    slug_dir = out_root / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "package.drift.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _metadata(
    *,
    slug: str = "20260520t000000z-acme",
    created_at: str = "2026-05-20T00:00:00Z",
    source_board: str = "linkedin",
    held: bool = False,
    drift_verdicts: dict[str, str] | None = None,
    job_title: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "slug": slug,
        "jd_source": "paste",
        "created_at": created_at,
        "source_board": source_board,
        "held": held,
        "drift_verdicts": drift_verdicts or {
            "fabrication": "pass",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
        "override": {"applied": False, "reason": None},
        "error": None,
    }
    if job_title is not None:
        body["job_title"] = job_title
    if company_name is not None:
        body["company_name"] = company_name
    return body


def _drift_doc(
    *,
    fabrication: str = "pass",
    content_loss: str = "pass",
    keyword_stuffing: str = "pass",
) -> dict[str, Any]:
    return {
        "fabrication_check": {"verdict": fabrication, "unsourced_claims": []},
        "content_loss": {"verdict": content_loss, "dropped_entries": []},
        "keyword_stuffing": {"verdict": keyword_stuffing, "density_violations": []},
    }


# ---- AC1: empty out/ -------------------------------------------------------


def test_drift_history_empty_out_root_returns_empty_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage_out_root(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/drift/history")

    assert response.status_code == 200
    assert response.json() == {"checks": []}


# ---- AC2: two packages, newest-first, correct verdicts + held flag ---------


def test_drift_history_two_packages_sorted_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)

    older_slug = "20260520t000000z-older"
    newer_slug = "20260525t120000z-newer"

    # older package: passes all checks, not held
    _write_metadata(
        out_root,
        _metadata(
            slug=older_slug,
            created_at="2026-05-20T00:00:00Z",
            source_board="linkedin",
            held=False,
            job_title="Software Engineer",
            company_name="OldCo",
        ),
    )
    _write_drift(out_root, older_slug, _drift_doc())

    # newer package: fabrication fail, held=True
    _write_metadata(
        out_root,
        _metadata(
            slug=newer_slug,
            created_at="2026-05-25T12:00:00Z",
            source_board="upwork",
            held=True,
            drift_verdicts={
                "fabrication": "fail",
                "content_loss": "pass",
                "keyword_stuffing": "pass",
            },
            job_title="Lead Developer",
            company_name="NewCo",
        ),
    )
    _write_drift(
        out_root,
        newer_slug,
        _drift_doc(fabrication="fail"),
    )

    client = TestClient(create_app())
    response = client.get("/api/drift/history")

    assert response.status_code == 200
    body = response.json()
    checks = body["checks"]
    assert len(checks) == 2

    # newest-first
    assert checks[0]["slug"] == newer_slug
    assert checks[1]["slug"] == older_slug

    # newer row: held=True, fabrication fail
    newer = checks[0]
    assert newer["held"] is True
    assert newer["source_board"] == "upwork"
    assert newer["created_at"] == "2026-05-25T12:00:00Z"
    assert newer["job_title"] == "Lead Developer"
    assert newer["company_name"] == "NewCo"
    assert newer["drift_verdicts"]["fabrication"] == "fail"
    assert newer["drift_verdicts"]["content_loss"] == "pass"
    assert newer["drift_verdicts"]["keyword_stuffing"] == "pass"

    # older row: held=False, all pass
    older = checks[1]
    assert older["held"] is False
    assert older["source_board"] == "linkedin"
    assert older["drift_verdicts"]["fabrication"] == "pass"
    assert older["drift_verdicts"]["content_loss"] == "pass"
    assert older["drift_verdicts"]["keyword_stuffing"] == "pass"


# ---- AC3: missing drift sidecar → row present, verdicts null, no 500 ------


def test_drift_history_missing_drift_sidecar_row_present_no_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)

    slug = "20260521t000000z-no-drift"
    _write_metadata(
        out_root,
        _metadata(slug=slug, created_at="2026-05-21T00:00:00Z"),
    )
    # deliberately do NOT write package.drift.json

    client = TestClient(create_app())
    response = client.get("/api/drift/history")

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert len(checks) == 1
    row = checks[0]
    assert row["slug"] == slug
    # drift_verdicts absent or None when sidecar is missing
    assert row["drift_verdicts"] is None


def test_drift_history_corrupt_drift_sidecar_row_present_no_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)

    slug = "20260522t000000z-bad-drift"
    _write_metadata(
        out_root,
        _metadata(slug=slug, created_at="2026-05-22T00:00:00Z"),
    )
    # write corrupt drift JSON
    drift_path = out_root / slug / "package.drift.json"
    drift_path.write_text("not { valid } json", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/api/drift/history")

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert len(checks) == 1
    assert checks[0]["slug"] == slug
    assert checks[0]["drift_verdicts"] is None


# ---- extra: metadata fields missing (job_title / company_name optional) ----


def test_drift_history_tolerates_absent_job_title_and_company_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    slug = "20260523t000000z-no-title"
    # build metadata WITHOUT job_title/company_name keys
    raw = _metadata(slug=slug)
    _write_metadata(out_root, raw)

    client = TestClient(create_app())
    response = client.get("/api/drift/history")

    assert response.status_code == 200
    checks = response.json()["checks"]
    assert len(checks) == 1
    assert checks[0]["job_title"] is None
    assert checks[0]["company_name"] is None


# ---- extra: slug dir missing metadata.json is skipped ----------------------


def test_drift_history_skips_dirs_without_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)

    # dir with metadata
    good_slug = "20260520t000000z-good"
    _write_metadata(out_root, _metadata(slug=good_slug))

    # dir without metadata
    bare_dir = out_root / "20260521t000000z-bare"
    bare_dir.mkdir()
    (bare_dir / "cv.md").write_text("# CV\n", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get("/api/drift/history")

    assert response.status_code == 200
    checks = response.json()["checks"]
    slugs = [r["slug"] for r in checks]
    assert good_slug in slugs
    assert "20260521t000000z-bare" not in slugs
