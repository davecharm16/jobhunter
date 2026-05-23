"""Story 4.4 — drift API exposes the populated content_loss block.

The Story 3.5 route already serves the full drift.json; Story 4.4's contract
is the SHAPE the frontend can rely on. These tests pin the wire-level
contract via TestClient — pass/fail bodies, presence/absence of
config_snapshot (Story 4.3 may or may not have populated it depending on
deployment ordering).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.config import PROJECT_ROOT
from jobhunter.web.api import create_app


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    """Point the drift route's OUT_ROOT at a per-test tmp dir."""
    out_root = tmp_path / "out"
    out_root.mkdir()
    import jobhunter.web.routes.drift as drift_module

    monkeypatch.setattr(drift_module, "OUT_ROOT", out_root)
    return out_root


def _write_drift(out_dir: Path, slug: str, document: dict) -> Path:
    slug_dir = out_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    target = slug_dir / "package.drift.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def test_content_loss_pass_block_round_trips_through_drift_api(out_dir: Path) -> None:
    _write_drift(
        out_dir,
        "demo-pass",
        {
            "fabrication_check": {
                "verdict": "pass",
                "claims_total": 0,
                "claims_sourced": 0,
                "claims_unsourced": 0,
                "traces": [],
                "unsourced_claims": [],
            },
            "content_loss": {
                "verdict": "pass",
                "check_version": "v1",
                "ran_at": "2026-05-23T12:00:00Z",
                "preserved_entries": [],
                "dropped_entries": [],
                "config_snapshot": {
                    "relevance_matcher": "tag_overlap",
                    "presence_matcher": "substring",
                    "tag_overlap_min": 1,
                },
            },
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-pass/drift")
    assert res.status_code == 200
    body = res.json()
    assert body["content_loss"]["verdict"] == "pass"
    assert body["content_loss"]["config_snapshot"]["relevance_matcher"] == "tag_overlap"


def test_content_loss_fail_block_carries_dropped_entries(out_dir: Path) -> None:
    _write_drift(
        out_dir,
        "demo-fail",
        {
            "content_loss": {
                "verdict": "fail",
                "check_version": "v1",
                "ran_at": "2026-05-23T12:00:00Z",
                "preserved_entries": [],
                "dropped_entries": [
                    {
                        "entry_id": "work[0]:abc12345",
                        "section": "work",
                        "primary_text": "Senior Engineer at Acme | Shipped TypeScript ingestion",
                        "jd_requirements_addressed": ["typescript"],
                        "reason": "silently_lost",
                    }
                ],
                "config_snapshot": {
                    "relevance_matcher": "tag_overlap",
                    "presence_matcher": "substring",
                    "tag_overlap_min": 1,
                },
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-fail/drift")
    assert res.status_code == 200
    body = res.json()
    cl = body["content_loss"]
    assert cl["verdict"] == "fail"
    assert cl["dropped_entries"][0]["reason"] == "silently_lost"
    assert cl["dropped_entries"][0]["jd_requirements_addressed"] == ["typescript"]


def test_content_loss_block_optional_when_only_fabrication_present(
    out_dir: Path,
) -> None:
    """Older drift.json (pre-Story-4.2) only has fabrication_check.

    The route serves the document verbatim; the frontend handles the absent
    `content_loss` key via TypeScript optional chaining.
    """
    _write_drift(
        out_dir,
        "demo-old",
        {
            "fabrication_check": {
                "verdict": "pass",
                "claims_total": 1,
                "claims_sourced": 1,
                "claims_unsourced": 0,
                "traces": [],
                "unsourced_claims": [],
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-old/drift")
    assert res.status_code == 200
    body = res.json()
    assert "fabrication_check" in body
    assert "content_loss" not in body


def test_content_loss_block_survives_without_config_snapshot(out_dir: Path) -> None:
    """Story 4.2 ships content_loss before Story 4.3 ships config_snapshot.

    A drift.json from that intermediate state should still serve cleanly.
    """
    _write_drift(
        out_dir,
        "demo-intermediate",
        {
            "content_loss": {
                "verdict": "pass",
                "check_version": "v1",
                "ran_at": "2026-05-23T12:00:00Z",
                "preserved_entries": [],
                "dropped_entries": [],
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-intermediate/drift")
    assert res.status_code == 200
    body = res.json()
    assert body["content_loss"]["verdict"] == "pass"
    assert "config_snapshot" not in body["content_loss"]
