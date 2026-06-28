"""Integration: source-board classifier wired into POST /api/paste (Story 2.4).

Covers AC1 (classifier runs after parse, source_board lands in metadata),
AC2 (explicit `source_board` in the request body overrides heuristics), and
AC3 (unrecognised JD resolves to `other` and the pipeline still produces
artifacts + metadata end-to-end).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from tests.integration._web_helpers import (
    make_fake_classifier,
    stage_canonical_cv,
    stage_tailoring,
)

from jobhunter.board_classifier import Classification
from jobhunter.web.api import create_app

# --- AC1: heuristic classification reaches metadata.json -----------------


def test_upwork_jd_is_classified_as_upwork(tmp_path, monkeypatch) -> None:
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


def test_onlinejobs_ph_jd_is_classified(tmp_path, monkeypatch) -> None:
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


def test_linkedin_jd_is_classified(tmp_path, monkeypatch) -> None:
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


# --- AC3: unrecognised JD resolves to "other" and pipeline still completes


def test_unmatched_jd_resolves_to_other_and_pipeline_completes(
    tmp_path, monkeypatch,
) -> None:
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

    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    # Pipeline still produces CV + cover letter + metadata (AC3).
    assert (slug_dir / "cv.md").exists()
    assert (slug_dir / "cover-letter.md").exists()
    metadata = json.loads((slug_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["source_board"] == "other"
    assert metadata["artifacts_produced"] == ["cv", "cover_letter"]


# --- AC2: explicit source_board in request body overrides heuristics -----


def test_explicit_source_board_overrides_heuristic(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    # JD text says onlinejobs.ph but caller forces "linkedin".
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "Posted via onlinejobs.ph for a VA role.\n",
            "source": "n8n",
            "source_board": "linkedin",
        },
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "linkedin"


def test_omitted_source_board_runs_heuristics(tmp_path, monkeypatch) -> None:
    """When the body has no `source_board`, heuristics run (not an override)."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    seen_overrides: list[str | None] = []

    def recording_classifier(jd_text, parsed_jd, *, explicit_override=None):
        seen_overrides.append(explicit_override)
        return Classification(source_board="other", method="heuristic")

    out_root, _ = stage_tailoring(
        tmp_path, monkeypatch, fake_classify=recording_classifier
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Generic JD.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text
    assert seen_overrides == [None]


def test_explicit_source_board_threaded_to_classifier(
    tmp_path, monkeypatch,
) -> None:
    """The request body's `source_board` reaches `classify_board` as the override."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)

    seen_overrides: list[str | None] = []

    def recording_classifier(jd_text, parsed_jd, *, explicit_override=None):
        seen_overrides.append(explicit_override)
        return Classification(
            source_board=explicit_override or "other",
            method="explicit_override" if explicit_override else "heuristic",
        )

    out_root, _ = stage_tailoring(
        tmp_path, monkeypatch, fake_classify=recording_classifier
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={
            "jd_text": "JD\n",
            "source": "n8n",
            "source_board": "upwork",
        },
    )
    assert response.status_code == 200, response.text
    assert seen_overrides == ["upwork"]
    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "upwork"


# --- AC1: parsed_jd shape unchanged (source_board lives at metadata top-level)


def test_parsed_jd_dict_in_metadata_does_not_include_source_board(
    tmp_path, monkeypatch,
) -> None:
    """Story 2.3's `parsed_jd` shape is preserved; source_board lives one level up."""
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "upwork.com job.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert "source_board" not in metadata["parsed_jd"]
    assert metadata["source_board"] == "upwork"


# --- Stubbed classifier path (verify the injection seam works) -----------


def test_stubbed_classifier_is_honoured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    stage_canonical_cv(tmp_path, monkeypatch)
    out_root, _ = stage_tailoring(
        tmp_path,
        monkeypatch,
        fake_classify=make_fake_classifier(source_board="onlinejobs_ph"),
    )

    client = TestClient(create_app())
    response = client.post(
        "/api/paste",
        json={"jd_text": "Some JD.\n", "source": "browser"},
    )
    assert response.status_code == 200, response.text

    metadata = _read_metadata(out_root)
    assert metadata["source_board"] == "onlinejobs_ph"


def _read_metadata(out_root):
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    return json.loads((slug_dirs[0] / "metadata.json").read_text(encoding="utf-8"))
