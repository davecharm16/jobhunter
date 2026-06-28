"""Integration: per-board artifact-set selector wired into POST /api/paste (Story 2.8).

Covers AC1 (per-board defaults reach `metadata.artifacts_produced`), AC2
(`metadata.artifacts_override` in the request body wins over the default), and
AC3 (the metadata sidecar's `artifacts_produced` matches the selector's
output for each board).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_classifier,
    stage_canonical_cv,
    stage_tailoring,
)

from jobhunter.web.api import create_app

# --- AC1 + AC3: per-board defaults land in metadata.artifacts_produced ----


def test_upwork_board_produces_cv_and_upwork_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role posted on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "upwork"
    assert metadata["artifacts_produced"] == ["cv", "upwork_proposal"]


def test_linkedin_board_produces_cv_and_cover_letter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Apply via linkedin.com/jobs/view/12345.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "linkedin"
    assert metadata["artifacts_produced"] == ["cv", "cover_letter"]


def test_onlinejobs_ph_board_produces_cv_and_cover_letter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Looking for a VA via onlinejobs.ph.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "onlinejobs_ph"
    assert metadata["artifacts_produced"] == ["cv", "cover_letter"]


def test_other_board_defaults_to_cv_and_cover_letter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role at Acme. Email careers@acme.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "other"
    assert metadata["artifacts_produced"] == ["cv", "cover_letter"]


# --- AC2: metadata.artifacts_override overrides the per-board default -----


def test_artifacts_override_replaces_per_board_default(tmp_path, monkeypatch) -> None:
    """Upwork JD with override `["cv", "cover_letter"]` lands a cover_letter set."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role posted on upwork.com.\n",
            "source": "n8n",
            "metadata": {"artifacts_override": ["cv", "cover_letter"]},
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "upwork"
    assert metadata["artifacts_produced"] == ["cv", "cover_letter"]


def test_artifacts_override_can_request_all_three(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_classify=make_fake_classifier(source_board="linkedin"),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Some JD.\n",
            "source": "n8n",
            "metadata": {
                "artifacts_override": ["cv", "cover_letter", "upwork_proposal"],
            },
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["artifacts_produced"] == [
        "cv",
        "cover_letter",
        "upwork_proposal",
    ]


def test_metadata_without_artifacts_override_runs_per_board_default(
    tmp_path, monkeypatch,
) -> None:
    """A request body with `metadata` but no `artifacts_override` key falls back."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role posted on upwork.com.\n",
            "source": "n8n",
            "metadata": {"unrelated_key": "value"},
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["artifacts_produced"] == ["cv", "upwork_proposal"]


def test_omitted_metadata_runs_per_board_default(tmp_path, monkeypatch) -> None:
    """A request body without a `metadata` field at all keeps the default path live."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Apply via linkedin.com/jobs/view/12345.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["artifacts_produced"] == ["cv", "cover_letter"]


# --- AC3: cv.md + cover-letter.md are still written (Story 2.8 seam) ------


def test_cv_and_cover_letter_md_still_written_for_upwork_board(
    tmp_path, monkeypatch,
) -> None:
    """Story 2.8 seam: artifacts_produced advertises upwork_proposal but the
    actual write path is unchanged — cv.md + cover-letter.md ship until Story 2.7
    introduces the upwork-proposal.md write.
    """
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Senior Python role posted on upwork.com.\n",
            "source": "browser",
        },
    )
    assert response.status_code == 200, response.text

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    assert (slug_dir / "cv.md").exists()
    assert (slug_dir / "cover-letter.md").exists()
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["artifacts_produced"] == ["cv", "upwork_proposal"]


def _read_metadata(out_root):
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    return json.loads((slug_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
