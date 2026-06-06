"""GET /api/stats integration tests (Story 2.12).

Uses FastAPI's `TestClient` to drive the route handler in-process. Synthesizes
metadata sidecars under a tmp `out/` and monkeypatches `PROJECT_ROOT` so the
route reads from the test fixture instead of the repo's real `./out/`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jobhunter.web.api import create_app


def _stage_out_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `PROJECT_ROOT` at *tmp_path* so `./out/` resolves into the fixture."""
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)

    import jobhunter.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_ROOT", tmp_path)
    return out_root


def _sidecar(
    *,
    slug: str = "20260520t000000z-acme",
    created_at: str = "2026-05-20T00:00:00Z",
    cost_total: str = "0.010000",
    source_board: str = "linkedin",
    drift: dict[str, str] | None = None,
    override_applied: bool = False,
    interview_reached: bool | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "slug": slug,
        "jd_source": "paste",
        "artifacts_produced": ["cv", "cover_letter"],
        "cost": {
            "total_usd": cost_total,
            "per_app_target_usd": "0.250000",
            "exceeded_per_app_target": False,
            "calls": [],
        },
        "created_at": created_at,
        "source_board": source_board,
        "parsed_jd": {},
        "red_flags": [],
        "prompt_templates": {},
        "drift_verdicts": dict(
            drift or {"fabrication": "pass", "content_loss": "pass", "keyword_stuffing": "pass"}
        ),
        "override": {"applied": override_applied, "reason": "ok" if override_applied else None},
        "error": None,
    }
    if interview_reached is not None:
        body["interview_reached"] = interview_reached
    return body


def _write(out_root: Path, payload: dict[str, Any]) -> Path:
    slug_dir = out_root / payload["slug"]
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- AC1: full response shape --------------------------------------------


def test_get_stats_returns_full_response_for_synthetic_sidecars(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    # monthly_spend_usd sums sidecars in the CURRENT calendar month. Date the
    # fixtures into this month dynamically so the assertion is deterministic
    # regardless of when the suite runs (the old hard-coded 2026-05 date made
    # this a time-bomb that broke once the calendar rolled past May 2026).
    this_month = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    _write(out_root, _sidecar(slug="a", cost_total="0.010000", created_at=this_month))
    _write(out_root, _sidecar(slug="b", cost_total="0.020000", created_at=this_month))

    client = TestClient(create_app())
    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["applications_total"] == 2
    assert body["cost_per_app_avg_usd"] == "0.015000"
    assert body["monthly_spend_usd"] == "0.030000"
    assert body["drift_catch_rate"] == "0.000"
    assert body["override_rate"] == "insufficient_data"
    assert body["interview_conversion_rate_30app"] == "insufficient_data"
    assert body["n"] == 2
    assert body["cost_regression_window"] is False


def test_get_stats_empty_out_root_returns_zero_totals(tmp_path, monkeypatch) -> None:
    _stage_out_root(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["applications_total"] == 0
    assert body["cost_per_app_avg_usd"] == "0.000000"
    assert body["drift_catch_rate"] == "insufficient_data"


def test_get_stats_drift_catch_rate_counts_any_failed_verdict(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(
            slug="held",
            drift={"fabrication": "fail", "content_loss": "pass", "keyword_stuffing": "pass"},
            override_applied=True,
        ),
    )
    _write(out_root, _sidecar(slug="clean"))

    client = TestClient(create_app())
    body = client.get("/api/stats").json()
    assert body["drift_catch_rate"] == "0.500"
    assert body["override_rate"] == "1.000"


# --- AC2: filters --------------------------------------------------------


def test_get_stats_since_filter(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="old", created_at="2026-03-15T00:00:00Z"))
    _write(out_root, _sidecar(slug="new", created_at="2026-04-15T00:00:00Z"))

    client = TestClient(create_app())
    response = client.get("/api/stats?since=2026-04-01")
    assert response.status_code == 200
    assert response.json()["applications_total"] == 1


def test_get_stats_board_filter(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="upwork-1", source_board="upwork"))
    _write(out_root, _sidecar(slug="linkedin-1", source_board="linkedin"))

    client = TestClient(create_app())
    response = client.get("/api/stats?board=upwork")
    assert response.status_code == 200
    assert response.json()["applications_total"] == 1


def test_get_stats_filters_compose(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(
        out_root,
        _sidecar(slug="a", source_board="upwork", created_at="2026-04-15T00:00:00Z"),
    )
    _write(
        out_root,
        _sidecar(slug="b", source_board="upwork", created_at="2026-03-15T00:00:00Z"),
    )
    _write(
        out_root,
        _sidecar(slug="c", source_board="linkedin", created_at="2026-04-15T00:00:00Z"),
    )

    client = TestClient(create_app())
    response = client.get("/api/stats?since=2026-04-01&board=upwork")
    assert response.status_code == 200
    assert response.json()["applications_total"] == 1


def test_get_stats_invalid_since_returns_422(tmp_path, monkeypatch) -> None:
    _stage_out_root(tmp_path, monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/stats?since=not-a-date")
    assert response.status_code == 422
    assert "not-a-date" in response.json()["detail"]


def test_get_stats_unknown_board_returns_zero_matches(tmp_path, monkeypatch) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(source_board="linkedin"))

    client = TestClient(create_app())
    response = client.get("/api/stats?board=craigslist")
    assert response.status_code == 200
    assert response.json()["applications_total"] == 0


# --- AC3: cost_regression_window flag ------------------------------------


def test_get_stats_cost_regression_window_true_when_avg_above_target(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="a", cost_total="0.300000"))
    _write(out_root, _sidecar(slug="b", cost_total="0.300000"))

    client = TestClient(create_app())
    body = client.get("/api/stats").json()
    assert body["cost_regression_window"] is True


def test_get_stats_cost_regression_window_false_at_target(
    tmp_path, monkeypatch,
) -> None:
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="a", cost_total="0.250000"))

    client = TestClient(create_app())
    body = client.get("/api/stats").json()
    assert body["cost_regression_window"] is False


# --- Bug-3 fix: drift_catches_total counts only fabrication holds ---------


def test_get_stats_drift_catches_total_present_and_zero_when_no_holds(
    tmp_path, monkeypatch,
) -> None:
    """drift_catches_total must always be present in the response body."""
    out_root = _stage_out_root(tmp_path, monkeypatch)
    _write(out_root, _sidecar(slug="a"))  # all-pass verdicts

    body = TestClient(create_app()).get("/api/stats").json()
    assert "drift_catches_total" in body
    assert body["drift_catches_total"] == 0


def test_get_stats_drift_catches_total_counts_only_fabrication_fails(
    tmp_path, monkeypatch,
) -> None:
    """drift_catches_total counts fabrication=='fail' holds only.

    Before the fix this field was absent, so StatsCard fell back to
    ``drift_catch_rate * total`` which included content-loss and keyword
    holds — wrong for "Fabrications prevented".
    """
    out_root = _stage_out_root(tmp_path, monkeypatch)

    # fabrication fail → counts
    _write(
        out_root,
        _sidecar(
            slug="fab-fail",
            drift={"fabrication": "fail", "content_loss": "pass", "keyword_stuffing": "pass"},
        ),
    )
    # content-loss-only fail → must NOT count
    _write(
        out_root,
        _sidecar(
            slug="content-fail",
            drift={"fabrication": "pass", "content_loss": "fail", "keyword_stuffing": "pass"},
        ),
    )
    # keyword-stuffing-only fail → must NOT count
    _write(
        out_root,
        _sidecar(
            slug="kw-fail",
            drift={"fabrication": "pass", "content_loss": "pass", "keyword_stuffing": "fail"},
        ),
    )
    # clean pass → must NOT count
    _write(out_root, _sidecar(slug="clean"))

    body = TestClient(create_app()).get("/api/stats").json()
    assert body["drift_catches_total"] == 1  # only the fabrication fail


def test_get_stats_drift_catches_total_zero_when_no_sidecars(
    tmp_path, monkeypatch,
) -> None:
    """Empty out/ returns drift_catches_total == 0 (not absent, not error)."""
    _stage_out_root(tmp_path, monkeypatch)
    body = TestClient(create_app()).get("/api/stats").json()
    assert "drift_catches_total" in body
    assert body["drift_catches_total"] == 0
