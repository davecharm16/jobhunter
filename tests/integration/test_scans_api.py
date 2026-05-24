"""Story 7.5 — GET /api/scans aggregates per-flow ingest telemetry.

Pins the wire shape, the never-run empty state, the verdict mapping, and
the secret-hygiene guarantee (AC2/AC4 — the response body must never
expose credentials, tokens, or env-var values).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app


@pytest.fixture
def out_root(tmp_path, monkeypatch):
    """Point ./out/ at a per-test tmp dir so the route reads our fixtures."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    return out_dir


def _write_sidecar(
    out_root: Path,
    slug: str,
    *,
    jd_source: str,
    discovered_at: str | None = None,
    created_at: str = "2026-05-24T10:00:00Z",
    drift_verdicts: dict | None = None,
) -> Path:
    slug_dir = out_root / slug
    slug_dir.mkdir(parents=True, exist_ok=True)
    sidecar = {
        "slug": slug,
        "jd_source": jd_source,
        "source_board": "other",
        "discovered_at": discovered_at,
        "created_at": created_at,
        "drift_verdicts": drift_verdicts
        or {"fabrication": "pass", "content_loss": "pass", "keyword_stuffing": "pass"},
        "held": False,
        "cost": {
            "total_usd": "0.001000",
            "per_app_target_usd": "0.250000",
            "exceeded_per_app_target": False,
            "calls": [],
        },
    }
    target = slug_dir / "metadata.json"
    target.write_text(json.dumps(sidecar), encoding="utf-8")
    return target


# ---- AC1: response shape ----------------------------------------------------


def test_scans_returns_three_flow_entries_in_documented_shape(out_root: Path) -> None:
    client = TestClient(create_app())
    res = client.get("/api/scans")
    assert res.status_code == 200
    body = res.json()
    assert "flows" in body
    names = {flow["flow_name"] for flow in body["flows"]}
    assert names == {"upwork", "onlinejobs_ph", "linkedin_email"}
    for flow in body["flows"]:
        assert set(flow.keys()) == {
            "flow_name",
            "last_run_timestamp",
            "last_run_status",
            "jds_ingested_count",
            "last_error",
        }


def test_scans_never_run_when_no_metadata_present(out_root: Path) -> None:
    client = TestClient(create_app())
    body = client.get("/api/scans").json()
    for flow in body["flows"]:
        assert flow["last_run_status"] == "never_run"
        assert flow["last_run_timestamp"] is None
        assert flow["jds_ingested_count"] == 0
        assert flow["last_error"] is None


def test_scans_aggregates_count_and_latest_timestamp(out_root: Path) -> None:
    _write_sidecar(
        out_root,
        "u1",
        jd_source="upwork",
        discovered_at="2026-05-24T08:00:00Z",
    )
    _write_sidecar(
        out_root,
        "u2",
        jd_source="upwork",
        discovered_at="2026-05-24T10:00:00Z",
    )
    _write_sidecar(
        out_root,
        "o1",
        jd_source="onlinejobs_ph",
        discovered_at="2026-05-24T09:00:00Z",
    )
    client = TestClient(create_app())
    body = client.get("/api/scans").json()
    by_name = {f["flow_name"]: f for f in body["flows"]}
    assert by_name["upwork"]["jds_ingested_count"] == 2
    assert by_name["upwork"]["last_run_timestamp"] == "2026-05-24T10:00:00Z"
    assert by_name["upwork"]["last_run_status"] == "pass"
    assert by_name["onlinejobs_ph"]["jds_ingested_count"] == 1
    assert by_name["linkedin_email"]["last_run_status"] == "never_run"


def test_scans_status_fail_when_most_recent_has_drift_fail(out_root: Path) -> None:
    _write_sidecar(
        out_root,
        "ok",
        jd_source="upwork",
        discovered_at="2026-05-24T08:00:00Z",
    )
    _write_sidecar(
        out_root,
        "fail",
        jd_source="upwork",
        discovered_at="2026-05-24T10:00:00Z",
        drift_verdicts={
            "fabrication": "fail",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
    )
    body = TestClient(create_app()).get("/api/scans").json()
    upwork = next(f for f in body["flows"] if f["flow_name"] == "upwork")
    assert upwork["last_run_status"] == "fail"


def test_scans_falls_back_to_created_at_when_discovered_at_absent(
    out_root: Path,
) -> None:
    _write_sidecar(
        out_root,
        "no-discovered",
        jd_source="linkedin_email",
        discovered_at=None,
        created_at="2026-05-24T07:00:00Z",
    )
    body = TestClient(create_app()).get("/api/scans").json()
    li = next(f for f in body["flows"] if f["flow_name"] == "linkedin_email")
    assert li["last_run_timestamp"] == "2026-05-24T07:00:00Z"
    assert li["jds_ingested_count"] == 1


def test_scans_excludes_browser_paste_packages(out_root: Path) -> None:
    """The browser path's `jd_source: 'paste'` must not contribute to any flow."""
    _write_sidecar(
        out_root,
        "browser",
        jd_source="paste",
        discovered_at="2026-05-24T11:00:00Z",
    )
    body = TestClient(create_app()).get("/api/scans").json()
    for flow in body["flows"]:
        assert flow["jds_ingested_count"] == 0
        assert flow["last_run_status"] == "never_run"


# ---- AC2 / AC4: secret hygiene ----------------------------------------------


def test_scans_response_contains_no_secret_shaped_strings(out_root: Path) -> None:
    """The response body must never carry credential / token / env values."""
    # Populate one of each flow type.
    _write_sidecar(out_root, "u", jd_source="upwork")
    _write_sidecar(out_root, "o", jd_source="onlinejobs_ph")
    _write_sidecar(out_root, "l", jd_source="linkedin_email")
    res = TestClient(create_app()).get("/api/scans")
    raw = res.text  # raw JSON string

    # No ALL_CAPS env-var-style identifiers (LLM_API_KEY, INGEST_TOKEN,
    # IMAP_PASSWORD, etc.). The keyword "linkedin_email" is fine — it's
    # lowercase + underscore.
    assert not re.search(r"\b[A-Z][A-Z0-9_]{4,}\b", raw)

    # No secret-shaped sibling keys.
    forbidden_substrings = ("password", "token", "secret", "api_key", "imap_")
    body_lower = raw.lower()
    for needle in forbidden_substrings:
        assert needle not in body_lower, (
            f"response body must not contain '{needle}'"
        )
