"""Per-application metadata sidecar (Story 2.10).

Every tailored package writes `./out/<slug>/metadata.json` capturing the
JD source, parsed-JD placeholders, drift-verdict placeholders, prompt-template
versions, the override flag, and a complete cost breakdown (total + per-call).
This is the substrate that `GET /api/stats` (Story 2.12) aggregates over.

Costs are kept as `Decimal` in memory and serialized as quoted strings via
`format(value, "f")` so trailing zeros survive the JSON round-trip — same
idiom as the Epic 1 spend ledger.

Write strategy mirrors the artifact write in `tailoring.py`: build into a
`.metadata.tmp` sibling and `os.replace()` it onto the final path. POSIX
guarantees `os.replace()` is atomic on the same filesystem, so a crash mid
write cannot leave a half-written `metadata.json` on disk (AC5).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


__all__ = [
    "CallLog",
    "CostBreakdown",
    "DEFAULT_DRIFT_VERDICTS",
    "PER_APP_COST_TARGET_USD",
    "PackageMetadata",
    "build_metadata",
    "format_cost",
    "now_iso8601_utc",
    "write_sidecar",
]


PER_APP_COST_TARGET_USD: Decimal = Decimal("0.25")
DEFAULT_DRIFT_VERDICTS: dict[str, str] = {
    "fabrication": "pending",
    "content_loss": "pending",
    "keyword_stuffing": "pending",
}
_COST_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True)
class CallLog:
    """Per-LLM-call record appended to `cost.calls[]`."""

    model: str
    input_tokens: int
    output_tokens: int
    usd_cost: str
    purpose: str


@dataclass(frozen=True)
class CostBreakdown:
    """Total + per-app target + per-call breakdown."""

    total_usd: str
    per_app_target_usd: str
    exceeded_per_app_target: bool
    calls: list[CallLog]


@dataclass(frozen=True)
class PackageMetadata:
    """The full metadata sidecar payload (AC1 field list, verbatim)."""

    slug: str
    jd_source: str
    artifacts_produced: list[str]
    cost: CostBreakdown
    created_at: str
    source_board: str = "unknown"
    parsed_jd: dict = field(default_factory=dict)
    red_flags: list[dict] = field(default_factory=list)
    prompt_templates: dict[str, str] = field(default_factory=dict)
    drift_verdicts: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_DRIFT_VERDICTS)
    )
    override: dict = field(
        default_factory=lambda: {"applied": False, "reason": None}
    )
    error: str | None = None


def format_cost(value: Decimal) -> str:
    """Serialize *value* to a fixed-point string preserving trailing zeros."""
    return format(value.quantize(_COST_QUANTUM), "f")


def now_iso8601_utc(now: datetime | None = None) -> str:
    """Return *now* (UTC) as an ISO 8601 string with a `Z` suffix."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_metadata(
    *,
    slug: str,
    jd_source: str,
    artifacts_produced: list[str],
    calls: list[CallLog],
    now: datetime | None = None,
    source_board: str = "unknown",
    parsed_jd: dict | None = None,
    red_flags: list[dict] | None = None,
    prompt_templates: dict[str, str] | None = None,
    drift_verdicts: dict[str, str] | None = None,
    override: dict | None = None,
    per_app_target_usd: Decimal = PER_APP_COST_TARGET_USD,
    error: str | None = None,
) -> PackageMetadata:
    """Assemble a `PackageMetadata` with the cost totals computed from *calls*.

    The total is summed over `calls[*].usd_cost` (Decimal arithmetic, never
    float). `exceeded_per_app_target` is a strict `>` comparison against
    *per_app_target_usd* so a run that lands exactly at the target is not
    marked as a breach.
    """
    total = sum((Decimal(call.usd_cost) for call in calls), Decimal("0"))
    cost = CostBreakdown(
        total_usd=format_cost(total),
        per_app_target_usd=format_cost(per_app_target_usd),
        exceeded_per_app_target=total > per_app_target_usd,
        calls=list(calls),
    )
    return PackageMetadata(
        slug=slug,
        jd_source=jd_source,
        artifacts_produced=list(artifacts_produced),
        cost=cost,
        created_at=now_iso8601_utc(now),
        source_board=source_board,
        parsed_jd=dict(parsed_jd) if parsed_jd is not None else {},
        red_flags=list(red_flags) if red_flags is not None else [],
        prompt_templates=(
            dict(prompt_templates) if prompt_templates is not None else {}
        ),
        drift_verdicts=(
            dict(drift_verdicts)
            if drift_verdicts is not None
            else dict(DEFAULT_DRIFT_VERDICTS)
        ),
        override=(
            dict(override)
            if override is not None
            else {"applied": False, "reason": None}
        ),
        error=error,
    )


def write_sidecar(out_dir: Path, metadata: PackageMetadata) -> Path:
    """Write `metadata.json` into *out_dir* atomically and return its path."""
    target = out_dir / "metadata.json"
    tmp_path = out_dir / ".metadata.tmp"
    payload = asdict(metadata)
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, target)
    return target
