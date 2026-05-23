"""Story 5.4 — drift API exposes the populated keyword_stuffing block.

The Story 3.5 route already serves the full drift.json; Story 5.4's contract
is the SHAPE the frontend can rely on. Pins the wire-level contract via
TestClient — pass / fail bodies, presence / absence of per-channel
overrides, and (Story 5.3 compatibility) the case where keyword_stuffing
is absent from the drift report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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


def _default_thresholds() -> dict:
    return {
        "max_density_pct": 1.5,
        "max_repetitions_per_artifact": 3,
        "dump_paragraph_min_tokens": 15,
        "dump_paragraph_max_keyword_ratio": 0.30,
        "comma_run_min_tokens": 4,
    }


def test_keyword_stuffing_pass_block_round_trips(out_dir: Path) -> None:
    _write_drift(
        out_dir,
        "demo-ks-pass",
        {
            "keyword_stuffing": {
                "verdict": "pass",
                "channel": "other",
                "density_violations": [],
                "dump_paragraph_locations": [],
                "thresholds_applied": _default_thresholds(),
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-ks-pass/drift")
    assert res.status_code == 200
    body = res.json()
    assert body["keyword_stuffing"]["verdict"] == "pass"
    assert body["keyword_stuffing"]["density_violations"] == []
    assert body["keyword_stuffing"]["dump_paragraph_locations"] == []


def test_keyword_stuffing_fail_block_carries_density_violations(out_dir: Path) -> None:
    _write_drift(
        out_dir,
        "demo-ks-density",
        {
            "keyword_stuffing": {
                "verdict": "fail",
                "channel": "linkedin",
                "density_violations": [
                    {
                        "keyword": "python",
                        "artifact": "cv.md",
                        "occurrences": 6,
                        "total_tokens": 100,
                        "density_pct": 6.0,
                        "threshold_breached": "max_density_pct",
                    }
                ],
                "dump_paragraph_locations": [],
                "thresholds_applied": _default_thresholds(),
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-ks-density/drift")
    assert res.status_code == 200
    ks = res.json()["keyword_stuffing"]
    assert ks["verdict"] == "fail"
    assert ks["density_violations"][0]["keyword"] == "python"
    assert ks["density_violations"][0]["threshold_breached"] == "max_density_pct"


def test_keyword_stuffing_fail_block_carries_dump_locations(out_dir: Path) -> None:
    _write_drift(
        out_dir,
        "demo-ks-dump",
        {
            "keyword_stuffing": {
                "verdict": "fail",
                "channel": "upwork",
                "density_violations": [],
                "dump_paragraph_locations": [
                    {
                        "artifact": "cv.md",
                        "paragraph_index": 2,
                        "kind": "comma_run_violation",
                        "matched_keywords": ["typescript", "node", "kubernetes", "graphql"],
                        "excerpt": "TypeScript, Node, Kubernetes, GraphQL.",
                    }
                ],
                "thresholds_applied": _default_thresholds(),
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-ks-dump/drift")
    assert res.status_code == 200
    ks = res.json()["keyword_stuffing"]
    assert ks["verdict"] == "fail"
    assert ks["dump_paragraph_locations"][0]["kind"] == "comma_run_violation"
    assert len(ks["dump_paragraph_locations"][0]["matched_keywords"]) == 4


def test_keyword_stuffing_per_channel_overrides_surface_in_thresholds_applied(
    out_dir: Path,
) -> None:
    """AC3: overrides differ from global defaults so the UI can flag them."""
    overridden = _default_thresholds()
    overridden["max_repetitions_per_artifact"] = 5
    overridden["dump_paragraph_max_keyword_ratio"] = 0.45
    _write_drift(
        out_dir,
        "demo-ks-override",
        {
            "keyword_stuffing": {
                "verdict": "pass",
                "channel": "upwork",
                "density_violations": [],
                "dump_paragraph_locations": [],
                "thresholds_applied": overridden,
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-ks-override/drift")
    assert res.status_code == 200
    ks = res.json()["keyword_stuffing"]
    assert ks["thresholds_applied"]["max_repetitions_per_artifact"] == 5
    assert ks["thresholds_applied"]["dump_paragraph_max_keyword_ratio"] == 0.45
    assert ks["channel"] == "upwork"


def test_keyword_stuffing_block_optional_when_only_fabrication_present(
    out_dir: Path,
) -> None:
    """Older drift.json (pre-Story-5.3) only has fabrication_check.

    The route serves the document verbatim; the frontend handles the absent
    `keyword_stuffing` key via TypeScript optional chaining.
    """
    _write_drift(
        out_dir,
        "demo-ks-absent",
        {
            "fabrication_check": {
                "verdict": "pass",
                "claims_total": 0,
                "claims_sourced": 0,
                "claims_unsourced": 0,
                "traces": [],
                "unsourced_claims": [],
            }
        },
    )
    client = TestClient(create_app())
    res = client.get("/api/package/demo-ks-absent/drift")
    assert res.status_code == 200
    body = res.json()
    assert "fabrication_check" in body
    assert "keyword_stuffing" not in body
