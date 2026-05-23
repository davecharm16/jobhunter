"""GET /api/package/<slug> tests (Story 2.14).

The route reads `./out/<slug>/` directly from disk on every request and
returns the JD text, tailored CV markdown, tailored cover letter markdown,
Upwork-proposal markdown (when present), and the `metadata.json` sidecar.
These tests stage per-test `./out/<slug>/` directories under `tmp_path`, point
the route module's `OUT_ROOT` at them via `monkeypatch`, and exercise the
FastAPI app in-process via `TestClient` — no real network, no real LLM call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app
from jobhunter.web.routes import package as package_module


@pytest.fixture
def staged_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the package route's OUT_ROOT at a per-test tmp directory."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    monkeypatch.setattr(package_module, "OUT_ROOT", out_root)
    return out_root


def _write_package(
    out_root: Path,
    slug: str,
    *,
    metadata: dict[str, Any],
    jd_text: str | None = None,
    cv_markdown: str | None = None,
    cover_letter_markdown: str | None = None,
    upwork_proposal_markdown: str | None = None,
) -> Path:
    package_dir = out_root / slug
    package_dir.mkdir()
    (package_dir / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    if jd_text is not None:
        (package_dir / "jd.txt").write_text(jd_text, encoding="utf-8")
    if cv_markdown is not None:
        (package_dir / "cv.md").write_text(cv_markdown, encoding="utf-8")
    if cover_letter_markdown is not None:
        (package_dir / "cover-letter.md").write_text(
            cover_letter_markdown, encoding="utf-8"
        )
    if upwork_proposal_markdown is not None:
        (package_dir / "upwork-proposal.md").write_text(
            upwork_proposal_markdown, encoding="utf-8"
        )
    return package_dir


def _minimal_metadata(slug: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "jd_source": "browser",
        "artifacts_produced": ["cv.md", "cover-letter.md"],
        "cost": {
            "total_usd": "0.004200",
            "per_app_target_usd": "0.250000",
            "exceeded_per_app_target": False,
            "calls": [
                {
                    "model": "claude-test",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "usd_cost": "0.004200",
                    "purpose": "tailoring",
                },
            ],
        },
        "created_at": "2026-05-23T10:00:00Z",
        "source_board": "unknown",
        "parsed_jd": {
            "must_haves": ["Python"],
            "nice_to_haves": ["Docker"],
            "tone": "neutral",
            "seniority": "senior",
        },
        "red_flags": [],
        "prompt_templates": {"tailoring": "v1", "jd_parse": "v1"},
        "drift_verdicts": {
            "fabrication": "pending",
            "content_loss": "pending",
            "keyword_stuffing": "pending",
        },
        "override": {"applied": False, "reason": None},
        "error": None,
    }


# --- AC1: GET --------------------------------------------------------------


def test_get_package_returns_all_artifacts_and_metadata(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-acme-engineer-abcdef"
    metadata = _minimal_metadata(slug)
    _write_package(
        staged_out_root,
        slug,
        metadata=metadata,
        jd_text="Hiring a senior engineer...",
        cv_markdown="# Tailored CV\n\n- Skill: Python\n",
        cover_letter_markdown="Dear hiring manager,\n\nI am a fit.\n",
    )

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == slug
    assert body["jd_text"] == "Hiring a senior engineer..."
    assert body["cv_markdown"] == "# Tailored CV\n\n- Skill: Python\n"
    assert body["cover_letter_markdown"] == "Dear hiring manager,\n\nI am a fit.\n"
    assert body["upwork_proposal_markdown"] is None
    assert body["metadata"] == metadata


def test_get_package_returns_null_for_missing_optional_artifacts(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-no-jd-or-upwork-deadbe"
    metadata = _minimal_metadata(slug)
    _write_package(
        staged_out_root,
        slug,
        metadata=metadata,
        cv_markdown="# CV\n",
        cover_letter_markdown="Hello.\n",
    )

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["jd_text"] is None
    assert body["upwork_proposal_markdown"] is None
    assert body["cv_markdown"] == "# CV\n"
    assert body["cover_letter_markdown"] == "Hello.\n"


def test_get_package_returns_upwork_proposal_when_present(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-upwork-proposal-cafe12"
    metadata = _minimal_metadata(slug)
    metadata["source_board"] = "upwork"
    _write_package(
        staged_out_root,
        slug,
        metadata=metadata,
        cv_markdown="# CV\n",
        upwork_proposal_markdown="Hi! Here is my proposal...\n",
    )

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["upwork_proposal_markdown"] == "Hi! Here is my proposal...\n"
    assert body["metadata"]["source_board"] == "upwork"


def test_get_package_returns_404_for_unknown_slug(
    staged_out_root: Path,
) -> None:
    client = TestClient(create_app())
    response = client.get("/api/package/does-not-exist")

    assert response.status_code == 404
    assert "package_not_found" in response.json()["detail"]


def test_get_package_returns_404_when_metadata_missing(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-no-metadata-abcdef"
    package_dir = staged_out_root / slug
    package_dir.mkdir()
    (package_dir / "cv.md").write_text("# CV\n", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}")

    assert response.status_code == 404
    assert "package_metadata_missing" in response.json()["detail"]


def test_get_package_returns_500_when_metadata_malformed(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-bad-metadata-abcdef"
    package_dir = staged_out_root / slug
    package_dir.mkdir()
    (package_dir / "metadata.json").write_text("not json {{{", encoding="utf-8")

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}")

    assert response.status_code == 500
    assert "package_metadata_malformed" in response.json()["detail"]


def test_get_package_preserves_drift_verdicts_and_cost(
    staged_out_root: Path,
) -> None:
    slug = "2026-05-23-drift-cost-fedcba"
    metadata = _minimal_metadata(slug)
    metadata["drift_verdicts"] = {
        "fabrication": "pending",
        "content_loss": "pending",
        "keyword_stuffing": "pending",
    }
    metadata["cost"]["total_usd"] = "0.123456"
    _write_package(
        staged_out_root,
        slug,
        metadata=metadata,
        cv_markdown="# CV\n",
        cover_letter_markdown="Hi.\n",
    )

    client = TestClient(create_app())
    response = client.get(f"/api/package/{slug}")

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["drift_verdicts"]["fabrication"] == "pending"
    assert body["metadata"]["cost"]["total_usd"] == "0.123456"
    assert body["metadata"]["prompt_templates"]["tailoring"] == "v1"
