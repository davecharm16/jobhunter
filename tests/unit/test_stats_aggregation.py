"""Unit tests for `jobhunter.stats` aggregation (Story 2.12).

Covers AC1 (full response shape over a synthetic sidecar set), AC2 (since/board
filters), AC3 (cost_regression_window flag against the NFR4 $0.25 target), AC4
(rolling-30 interview-conversion window), and AC5 (never reads markdown — only
metadata.json sidecars).
"""

from __future__ import annotations

import builtins
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from jobhunter import stats as stats_module
from jobhunter.stats import (
    INSUFFICIENT_DATA,
    InvalidSinceFilter,
    aggregate_stats,
    load_metadata_sidecars,
)


# --- helpers --------------------------------------------------------------


def _make_sidecar(
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
            "exceeded_per_app_target": Decimal(cost_total) > Decimal("0.25"),
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
        "override": {"applied": override_applied, "reason": None if not override_applied else "ok"},
        "error": None,
    }
    if interview_reached is not None:
        body["interview_reached"] = interview_reached
    return body


def _write_sidecar(out_root: Path, payload: dict[str, Any]) -> Path:
    slug_dir = out_root / payload["slug"]
    slug_dir.mkdir(parents=True, exist_ok=True)
    path = slug_dir / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- load_metadata_sidecars ----------------------------------------------


def test_load_metadata_sidecars_returns_empty_when_out_root_missing(tmp_path) -> None:
    assert load_metadata_sidecars(tmp_path / "out") == []


def test_load_metadata_sidecars_reads_every_sidecar(tmp_path) -> None:
    out_root = tmp_path / "out"
    _write_sidecar(out_root, _make_sidecar(slug="one"))
    _write_sidecar(out_root, _make_sidecar(slug="two", cost_total="0.020000"))

    sidecars = load_metadata_sidecars(out_root)
    slugs = sorted(md["slug"] for md in sidecars)
    assert slugs == ["one", "two"]


def test_load_metadata_sidecars_skips_slug_dirs_without_metadata(tmp_path) -> None:
    out_root = tmp_path / "out"
    _write_sidecar(out_root, _make_sidecar(slug="ok"))
    (out_root / "empty").mkdir()

    sidecars = load_metadata_sidecars(out_root)
    assert [md["slug"] for md in sidecars] == ["ok"]


def test_load_metadata_sidecars_skips_malformed_json(tmp_path) -> None:
    out_root = tmp_path / "out"
    _write_sidecar(out_root, _make_sidecar(slug="ok"))
    bad_dir = out_root / "bad"
    bad_dir.mkdir()
    (bad_dir / "metadata.json").write_text("{not json", encoding="utf-8")

    sidecars = load_metadata_sidecars(out_root)
    assert [md["slug"] for md in sidecars] == ["ok"]


# --- AC5: never reads markdown -------------------------------------------


def test_load_metadata_sidecars_never_opens_markdown_artifacts(
    tmp_path, monkeypatch,
) -> None:
    out_root = tmp_path / "out"
    slug_dir = out_root / "20260520t000000z-acme"
    slug_dir.mkdir(parents=True)
    (slug_dir / "metadata.json").write_text(
        json.dumps(_make_sidecar(slug="20260520t000000z-acme")), encoding="utf-8"
    )
    # Stage markdown artifacts that MUST never be opened by the stats path.
    (slug_dir / "cv.md").write_text("# tailored cv\n", encoding="utf-8")
    (slug_dir / "cover-letter.md").write_text("Dear hiring manager\n", encoding="utf-8")

    opened_paths: list[str] = []
    real_open = builtins.open

    def tracking_open(file, *args, **kwargs):
        opened_paths.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracking_open)

    sidecars = load_metadata_sidecars(out_root)
    aggregate_stats(sidecars)

    md_opens = [p for p in opened_paths if p.endswith(".md")]
    assert md_opens == [], f"stats path opened markdown files: {md_opens}"


# --- AC1: aggregate response shape ---------------------------------------


def test_aggregate_stats_empty_set_returns_zero_totals_and_insufficient_data() -> None:
    aggregate = aggregate_stats([])
    body = aggregate.to_response()
    assert body["applications_total"] == 0
    assert body["cost_per_app_avg_usd"] == "0.000000"
    assert body["cost_per_app_p95_usd"] == "0.000000"
    assert body["monthly_spend_usd"] == "0.000000"
    assert body["drift_catch_rate"] == INSUFFICIENT_DATA
    assert body["override_rate"] == INSUFFICIENT_DATA
    assert body["interview_conversion_rate_30app"] == INSUFFICIENT_DATA
    assert body["n"] == 0
    assert body["cost_regression_window"] is False


def test_aggregate_stats_single_application_uses_decimal_arithmetic() -> None:
    sidecars = [_make_sidecar(cost_total="0.100000")]
    aggregate = aggregate_stats(
        sidecars,
        now=datetime(2026, 5, 23, tzinfo=timezone.utc),
    )
    body = aggregate.to_response()
    assert body["applications_total"] == 1
    assert body["cost_per_app_avg_usd"] == "0.100000"
    assert body["cost_per_app_p95_usd"] == "0.100000"
    assert body["monthly_spend_usd"] == "0.100000"


def test_aggregate_stats_drift_catch_and_override_rates() -> None:
    sidecars = [
        # 4 packages: 2 held (one with override applied, one without), 2 clean.
        _make_sidecar(
            slug="a",
            drift={"fabrication": "fail", "content_loss": "pass", "keyword_stuffing": "pass"},
            override_applied=True,
        ),
        _make_sidecar(
            slug="b",
            drift={"fabrication": "pass", "content_loss": "fail", "keyword_stuffing": "pass"},
        ),
        _make_sidecar(slug="c"),
        _make_sidecar(slug="d"),
    ]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["applications_total"] == 4
    assert body["drift_catch_rate"] == "0.500"  # 2/4
    assert body["override_rate"] == "0.500"     # 1/2 (over held only)


def test_aggregate_stats_override_rate_insufficient_when_no_held_packages() -> None:
    sidecars = [_make_sidecar(slug="a"), _make_sidecar(slug="b")]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["drift_catch_rate"] == "0.000"
    assert body["override_rate"] == INSUFFICIENT_DATA


def test_aggregate_stats_monthly_spend_filters_to_current_calendar_month() -> None:
    now = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)
    sidecars = [
        _make_sidecar(slug="prev", created_at="2026-04-30T23:59:59Z", cost_total="1.000000"),
        _make_sidecar(slug="early-may", created_at="2026-05-01T00:00:01Z", cost_total="0.500000"),
        _make_sidecar(slug="mid-may", created_at="2026-05-20T00:00:00Z", cost_total="0.250000"),
        _make_sidecar(slug="next", created_at="2026-06-01T00:00:00Z", cost_total="2.000000"),
    ]
    aggregate = aggregate_stats(sidecars, now=now)
    body = aggregate.to_response()
    # Only May 2026 (UTC) entries count toward monthly_spend.
    assert body["monthly_spend_usd"] == "0.750000"
    # applications_total counts every sidecar (no filter), avg over all 4.
    assert body["applications_total"] == 4


def test_aggregate_stats_p95_uses_nearest_rank_decimal() -> None:
    sidecars = [
        _make_sidecar(slug=f"s-{i}", cost_total=f"{i:.6f}")
        for i in range(1, 21)  # 1..20
    ]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    # Nearest-rank p95 over 20 values: index = ceil(0.95*20)-1 = 18 → value 19.
    assert body["cost_per_app_p95_usd"] == "19.000000"


# --- AC2: filters --------------------------------------------------------


def test_aggregate_stats_since_filter_excludes_earlier_applications() -> None:
    sidecars = [
        _make_sidecar(slug="old", created_at="2026-03-15T00:00:00Z"),
        _make_sidecar(slug="new", created_at="2026-04-10T00:00:00Z"),
    ]
    aggregate = aggregate_stats(sidecars, since="2026-04-01")
    body = aggregate.to_response()
    assert body["applications_total"] == 1


def test_aggregate_stats_board_filter_matches_source_board() -> None:
    sidecars = [
        _make_sidecar(slug="upwork", source_board="upwork"),
        _make_sidecar(slug="linkedin", source_board="linkedin"),
    ]
    aggregate = aggregate_stats(sidecars, board="upwork")
    body = aggregate.to_response()
    assert body["applications_total"] == 1


def test_aggregate_stats_board_filter_unknown_value_returns_empty_set() -> None:
    sidecars = [_make_sidecar(source_board="linkedin")]
    aggregate = aggregate_stats(sidecars, board="craigslist")
    body = aggregate.to_response()
    assert body["applications_total"] == 0


def test_aggregate_stats_filters_compose() -> None:
    sidecars = [
        _make_sidecar(slug="a", source_board="upwork", created_at="2026-04-10T00:00:00Z"),
        _make_sidecar(slug="b", source_board="upwork", created_at="2026-03-10T00:00:00Z"),
        _make_sidecar(slug="c", source_board="linkedin", created_at="2026-04-10T00:00:00Z"),
    ]
    aggregate = aggregate_stats(sidecars, since="2026-04-01", board="upwork")
    body = aggregate.to_response()
    assert body["applications_total"] == 1


def test_aggregate_stats_invalid_since_raises() -> None:
    with pytest.raises(InvalidSinceFilter):
        aggregate_stats([], since="not-a-date")


# --- AC3: cost_regression_window -----------------------------------------


def test_cost_regression_window_false_below_target() -> None:
    sidecars = [_make_sidecar(cost_total="0.100000")]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["cost_regression_window"] is False


def test_cost_regression_window_false_exactly_at_target() -> None:
    sidecars = [_make_sidecar(cost_total="0.250000")]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    # Strict > comparison — exactly at target is NOT a breach.
    assert body["cost_regression_window"] is False


def test_cost_regression_window_true_when_avg_exceeds_target() -> None:
    sidecars = [
        _make_sidecar(slug="a", cost_total="0.500000"),
        _make_sidecar(slug="b", cost_total="0.500000"),
    ]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["cost_regression_window"] is True


# --- AC4: rolling-30 interview-conversion -------------------------------


def test_interview_conversion_below_threshold_returns_insufficient_data() -> None:
    sidecars = [_make_sidecar(slug=f"s-{i}") for i in range(5)]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["interview_conversion_rate_30app"] == INSUFFICIENT_DATA
    assert body["n"] == 5


def test_interview_conversion_at_threshold_returns_rate_without_n_field() -> None:
    sidecars = [
        _make_sidecar(
            slug=f"s-{i:02d}",
            created_at=f"2026-05-{(i % 28) + 1:02d}T00:00:00Z",
            interview_reached=(i < 9),  # 9 of 30 reached interview
        )
        for i in range(30)
    ]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["interview_conversion_rate_30app"] == "0.300"
    assert "n" not in body


def test_interview_conversion_uses_most_recent_30_by_created_at() -> None:
    # Build 31 sidecars: the OLDEST one is the only `interview_reached: true`.
    # The rolling-30 window should drop it, so the rate is 0/30.
    sidecars = []
    for i in range(31):
        sidecars.append(
            _make_sidecar(
                slug=f"s-{i:02d}",
                created_at=f"2026-{((i // 28) + 1):02d}-{((i % 28) + 1):02d}T00:00:00Z",
                interview_reached=(i == 0),
            )
        )
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    # The oldest sidecar is dropped; remaining 30 have zero interviews.
    assert body["interview_conversion_rate_30app"] == "0.000"


def test_interview_conversion_treats_missing_field_as_false() -> None:
    # 30 sidecars, none have `interview_reached` set at all → rate is 0.
    sidecars = [
        _make_sidecar(
            slug=f"s-{i:02d}",
            created_at=f"2026-05-{(i % 28) + 1:02d}T00:00:00Z",
        )
        for i in range(30)
    ]
    aggregate = aggregate_stats(sidecars)
    body = aggregate.to_response()
    assert body["interview_conversion_rate_30app"] == "0.000"
