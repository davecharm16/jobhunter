"""Stats aggregation over per-application metadata sidecars (Story 2.12).

Reads `./out/<slug>/metadata.json` files directly from disk and computes the
KPIs surfaced by `GET /api/stats` — rolling cost-per-application, drift-catch
rate, override rate, and a 30-application interview-conversion window.

Per `DECISIONS.md` §6 ("no new persistence layer") and the story spec, this
module ONLY reads JSON sidecars — never markdown artifacts. The 30-application
interview-conversion window v1 note: `interview_reached` is not yet emitted by
any pipeline; a future story adds it via the Approve action's structured
metadata. Until then, the rate is always `insufficient_data` with the actual n.

All cost/percentage math uses `Decimal` (never float) — same idiom as the
Epic 1 spend ledger and the Story 2.10 metadata module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from jobhunter.metadata import PER_APP_COST_TARGET_USD, format_cost


__all__ = [
    "INSUFFICIENT_DATA",
    "InvalidSinceFilter",
    "StatsAggregate",
    "aggregate_stats",
    "load_metadata_sidecars",
]


INSUFFICIENT_DATA = "insufficient_data"
_INTERVIEW_WINDOW = 30
_RATE_QUANTUM = Decimal("0.001")


class InvalidSinceFilter(ValueError):
    """Raised when the `since` query parameter cannot be parsed as a date."""


@dataclass(frozen=True)
class StatsAggregate:
    """Computed aggregate over a filtered set of metadata sidecars."""

    applications_total: int
    cost_per_app_avg_usd: str
    cost_per_app_p95_usd: str
    monthly_spend_usd: str
    drift_catch_rate: str
    override_rate: str
    interview_conversion_rate_30app: str
    interview_window_n: int
    cost_regression_window: bool

    def to_response(self) -> dict[str, Any]:
        """Render the aggregate as the JSON-serializable response body."""
        body: dict[str, Any] = {
            "applications_total": self.applications_total,
            "cost_per_app_avg_usd": self.cost_per_app_avg_usd,
            "cost_per_app_p95_usd": self.cost_per_app_p95_usd,
            "monthly_spend_usd": self.monthly_spend_usd,
            "drift_catch_rate": self.drift_catch_rate,
            "override_rate": self.override_rate,
            "interview_conversion_rate_30app": self.interview_conversion_rate_30app,
            "cost_regression_window": self.cost_regression_window,
        }
        if self.interview_conversion_rate_30app == INSUFFICIENT_DATA:
            body["n"] = self.interview_window_n
        return body


def load_metadata_sidecars(out_root: Path) -> list[dict[str, Any]]:
    """Load every `./out/<slug>/metadata.json` under *out_root* as raw dicts.

    Slugs whose `metadata.json` is missing or malformed are silently skipped
    so a single corrupt sidecar does not block the dashboard from rendering.
    """
    if not out_root.is_dir():
        return []
    sidecars: list[dict[str, Any]] = []
    for slug_dir in sorted(out_root.iterdir()):
        if not slug_dir.is_dir():
            continue
        path = slug_dir / "metadata.json"
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                sidecars.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    return sidecars


def _parse_since(since: str) -> datetime:
    """Parse *since* (YYYY-MM-DD or ISO 8601) as a UTC-aware datetime."""
    try:
        if "T" in since:
            text = since.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
        else:
            dt = datetime.fromisoformat(since)
    except ValueError as exc:
        raise InvalidSinceFilter(f"invalid since filter: {since}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00") if isinstance(value, str) else value
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _filter_sidecars(
    sidecars: list[dict[str, Any]],
    *,
    since: str | None,
    board: str | None,
) -> list[dict[str, Any]]:
    since_dt = _parse_since(since) if since else None
    out: list[dict[str, Any]] = []
    for md in sidecars:
        if board is not None and md.get("source_board") != board:
            continue
        if since_dt is not None:
            created = _parse_created_at(md.get("created_at"))
            if created is None or created < since_dt:
                continue
        out.append(md)
    return out


def _percentile_95(values: list[Decimal]) -> Decimal:
    """Nearest-rank 95th percentile over *values* (Decimal arithmetic)."""
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    # Nearest-rank: index = ceil(0.95 * n) - 1, clamped to [0, n - 1].
    n = len(ordered)
    rank = -(-(95 * n) // 100) - 1  # ceil(0.95n) - 1, integer-only
    if rank < 0:
        rank = 0
    if rank >= n:
        rank = n - 1
    return ordered[rank]


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return INSUFFICIENT_DATA
    rate = (Decimal(numerator) / Decimal(denominator)).quantize(_RATE_QUANTUM)
    return format(rate, "f")


def _is_held(md: dict[str, Any]) -> bool:
    verdicts = md.get("drift_verdicts") or {}
    return any(v == "fail" for v in verdicts.values())


def _override_applied(md: dict[str, Any]) -> bool:
    override = md.get("override") or {}
    return bool(override.get("applied"))


def _decimal_cost(md: dict[str, Any]) -> Decimal:
    cost = md.get("cost") or {}
    raw = cost.get("total_usd")
    if raw is None:
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return Decimal("0")


def _is_in_current_month(created: datetime | None, now: datetime) -> bool:
    if created is None:
        return False
    return (
        created.year == now.year
        and created.month == now.month
    )


def aggregate_stats(
    sidecars: list[dict[str, Any]],
    *,
    since: str | None = None,
    board: str | None = None,
    now: datetime | None = None,
    per_app_cost_target: Decimal = PER_APP_COST_TARGET_USD,
) -> StatsAggregate:
    """Aggregate the filtered *sidecars* into a `StatsAggregate`.

    Filters apply before aggregation. Monthly spend is computed against the
    UTC calendar month of *now* (defaults to `datetime.now(timezone.utc)`).
    `cost_regression_window` is a strict `>` against *per_app_cost_target*
    (NFR4 — $0.25) over the filtered set, matching `metadata.build_metadata`'s
    breach semantics.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    filtered = _filter_sidecars(sidecars, since=since, board=board)
    total = len(filtered)

    costs = [_decimal_cost(md) for md in filtered]

    if total == 0:
        avg_cost = Decimal("0")
    else:
        avg_cost = sum(costs, Decimal("0")) / Decimal(total)

    p95_cost = _percentile_95(costs)

    monthly_total = sum(
        (
            _decimal_cost(md)
            for md in filtered
            if _is_in_current_month(_parse_created_at(md.get("created_at")), moment)
        ),
        Decimal("0"),
    )

    held = sum(1 for md in filtered if _is_held(md))
    overrides = sum(1 for md in filtered if _override_applied(md))

    # Interview-conversion: rolling-30 window by created_at (most recent 30).
    # v1: `interview_reached` is not yet emitted by any pipeline — until a
    # future story adds it, this returns insufficient_data when n < 30, and
    # otherwise the count of `interview_reached: true` over the window.
    with_created = [
        (md, _parse_created_at(md.get("created_at"))) for md in filtered
    ]
    with_created = [(md, dt) for md, dt in with_created if dt is not None]
    with_created.sort(key=lambda pair: pair[1], reverse=True)
    window = [md for md, _ in with_created[:_INTERVIEW_WINDOW]]
    window_n = len(window)

    if window_n < _INTERVIEW_WINDOW:
        interview_rate = INSUFFICIENT_DATA
    else:
        reached = sum(1 for md in window if bool(md.get("interview_reached")))
        interview_rate = _format_rate(reached, window_n)

    cost_regression = avg_cost > per_app_cost_target

    return StatsAggregate(
        applications_total=total,
        cost_per_app_avg_usd=format_cost(avg_cost),
        cost_per_app_p95_usd=format_cost(p95_cost),
        monthly_spend_usd=format_cost(monthly_total),
        drift_catch_rate=_format_rate(held, total),
        override_rate=_format_rate(overrides, held),
        interview_conversion_rate_30app=interview_rate,
        interview_window_n=window_n,
        cost_regression_window=cost_regression,
    )
