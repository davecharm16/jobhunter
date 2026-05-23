"""Human-readable drift-report Markdown generator (Story 6.2 AC2).

When any drift verdict fails (fabrication, content-loss, or keyword-stuffing)
the orchestrator writes `./out/<slug>/drift-report.md` next to the existing
machine-readable `package.drift.json` so the author can read at a glance which
check failed and why. The Markdown is sourced verbatim from the drift JSON —
no second matcher run, no LLM call.

Two contracts live in this module:

1. `compose_drift_report_markdown` — pure function from the parsed
   `package.drift.json` dict to a deterministic Markdown string. Zero I/O.
2. `write_drift_report` — atomic write (tmp + os.replace) into `out_dir`,
   mirroring every other sidecar writer in the pipeline.

Architectural note: held packages live at `./out/<slug>/` (co-located with
passed packages, identified by `metadata.held=true` + `package.held.json`),
NOT under a separate `./out/_held/<slug>/` tree. Story 6.2 keeps that working
contract from Stories 3.4 / 4.2 / 5.3.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


__all__ = [
    "DRIFT_REPORT_NAME",
    "MAX_LIST_ENTRIES",
    "compose_drift_report_markdown",
    "write_drift_report",
]


DRIFT_REPORT_NAME = "drift-report.md"

# Cap on per-section bullets so a runaway fail doesn't blow up the rendered
# report. The "and N more" tail keeps the total count visible.
MAX_LIST_ENTRIES = 10

# Keyword-stuffing density violations are sorted by density_pct and capped at
# this many top entries (separate from MAX_LIST_ENTRIES so the keyword section
# stays scannable at a glance).
MAX_KEYWORD_STUFFING_TOP_VIOLATIONS = 5


def compose_drift_report_markdown(drift_doc: dict[str, Any]) -> str:
    """Render a deterministic Markdown summary of *drift_doc* (Story 6.2 AC2).

    *drift_doc* is the parsed `package.drift.json` content. Sections render
    in the fixed order Fabrication -> Content loss -> Keyword stuffing so
    on-disk reports diff cleanly across runs. Each section shows a pass/fail
    verdict, a count, and a bullet list capped at `MAX_LIST_ENTRIES`; the
    keyword-stuffing section's density violations are additionally sorted by
    descending density and capped at `MAX_KEYWORD_STUFFING_TOP_VIOLATIONS`.
    """
    lines: list[str] = ["# Drift report", ""]
    lines.extend(_render_fabrication(drift_doc.get("fabrication_check") or {}))
    lines.append("")
    lines.extend(_render_content_loss(drift_doc.get("content_loss") or {}))
    lines.append("")
    lines.extend(_render_keyword_stuffing(drift_doc.get("keyword_stuffing") or {}))
    return "\n".join(lines).rstrip() + "\n"


def write_drift_report(out_dir: Path, drift_doc: dict[str, Any]) -> Path:
    """Render *drift_doc* and atomically write `drift-report.md` into *out_dir*."""
    target = out_dir / DRIFT_REPORT_NAME
    tmp_path = out_dir / ".drift-report.tmp"
    body = compose_drift_report_markdown(drift_doc)
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    os.replace(tmp_path, target)
    return target


# ---- per-section renderers ----------------------------------------------


def _render_fabrication(block: dict[str, Any]) -> list[str]:
    verdict = _verdict_of(block)
    unsourced = block.get("unsourced_claims") or []
    if not isinstance(unsourced, list):
        unsourced = []
    count = len(unsourced)
    lines = [
        "## Fabrication",
        "",
        f"- Verdict: **{verdict}**",
        f"- Unsourced claims: {count}",
    ]
    if not unsourced:
        return lines
    lines.append("")
    for entry in unsourced[:MAX_LIST_ENTRIES]:
        claim_text = _str_field(entry, "claim_text")
        reason = _str_field(entry, "reason")
        lines.append(f"- `{claim_text}` — {reason}")
    if count > MAX_LIST_ENTRIES:
        lines.append(f"- … and {count - MAX_LIST_ENTRIES} more")
    return lines


def _render_content_loss(block: dict[str, Any]) -> list[str]:
    verdict = _verdict_of(block)
    dropped = block.get("dropped_entries") or []
    if not isinstance(dropped, list):
        dropped = []
    count = len(dropped)
    lines = [
        "## Content loss",
        "",
        f"- Verdict: **{verdict}**",
        f"- Dropped entries: {count}",
    ]
    if not dropped:
        return lines
    lines.append("")
    for entry in dropped[:MAX_LIST_ENTRIES]:
        primary_text = _str_field(entry, "primary_text")
        reason = _str_field(entry, "reason")
        lines.append(f"- `{primary_text}` — {reason}")
    if count > MAX_LIST_ENTRIES:
        lines.append(f"- … and {count - MAX_LIST_ENTRIES} more")
    return lines


def _render_keyword_stuffing(block: dict[str, Any]) -> list[str]:
    verdict = _verdict_of(block)
    density_violations = block.get("density_violations") or []
    placement_locations = block.get("dump_paragraph_locations") or []
    if not isinstance(density_violations, list):
        density_violations = []
    if not isinstance(placement_locations, list):
        placement_locations = []
    total = len(density_violations) + len(placement_locations)
    lines = [
        "## Keyword stuffing",
        "",
        f"- Verdict: **{verdict}**",
        f"- Violations: {total}",
    ]
    if total == 0:
        return lines
    sorted_density = sorted(
        density_violations,
        key=lambda v: _float_field(v, "density_pct"),
        reverse=True,
    )
    top_density = sorted_density[:MAX_KEYWORD_STUFFING_TOP_VIOLATIONS]
    if top_density:
        lines.append("")
        lines.append(
            f"### Top {len(top_density)} density violation(s) by density"
        )
        for violation in top_density:
            keyword = _str_field(violation, "keyword")
            artifact = _str_field(violation, "artifact")
            density_pct = _float_field(violation, "density_pct")
            occurrences = _int_field(violation, "occurrences")
            lines.append(
                f"- `{keyword}` in `{artifact}` — "
                f"{density_pct:.2f}% density, {occurrences} occurrence(s)"
            )
        skipped = len(sorted_density) - len(top_density)
        if skipped > 0:
            lines.append(f"- … and {skipped} more density violation(s)")
    if placement_locations:
        lines.append("")
        lines.append("### Placement violations")
        for location in placement_locations[:MAX_LIST_ENTRIES]:
            kind = _str_field(location, "kind") or "violation"
            artifact = _str_field(location, "artifact")
            excerpt = _str_field(location, "excerpt")
            lines.append(f"- `{kind}` in `{artifact}` — {excerpt}")
        if len(placement_locations) > MAX_LIST_ENTRIES:
            extra = len(placement_locations) - MAX_LIST_ENTRIES
            lines.append(f"- … and {extra} more placement violation(s)")
    return lines


# ---- field-coercion helpers ---------------------------------------------


def _verdict_of(block: dict[str, Any]) -> str:
    """Surface the block's `verdict` field as `pass` / `fail` / `unknown`."""
    raw = block.get("verdict")
    if raw in ("pass", "fail"):
        return raw
    return "unknown"


def _str_field(entry: Any, key: str) -> str:
    if not isinstance(entry, dict):
        return ""
    value = entry.get(key)
    if value is None:
        return ""
    return str(value)


def _int_field(entry: Any, key: str) -> int:
    if not isinstance(entry, dict):
        return 0
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _float_field(entry: Any, key: str) -> float:
    if not isinstance(entry, dict):
        return 0.0
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)
