"""Keyword-stuffing drift-report writer (Story 5.3).

Persists Stories 5.1/5.2's `KeywordStuffingCheck` verdict + per-violation
detail to `./out/<slug>/package.drift.json` under the top-level
`keyword_stuffing` key. Mirrors `content_loss_writer.py` (Story 4.2) — each
drift dimension owns its own sibling block; this module reads the existing
file (if any), updates ONLY the `keyword_stuffing` key, and writes back
atomically (tmp + os.replace). Sibling keys (`fabrication_check` from Story
3.2, `content_loss` from Story 4.2) are preserved byte-for-byte.

On-disk shape under `keyword_stuffing`:

```
{
  "verdict": "pass" | "fail",
  "channel": "upwork" | "linkedin" | "onlinejobs_ph" | "other",
  "ran_at": "<ISO-8601 UTC with Z suffix>",
  "density_violations": [
    {"keyword": "...", "artifact": "cv.md", "occurrences": N,
     "total_tokens": N, "density_pct": F,
     "threshold_breached": "max_density_pct" | "max_repetitions_per_artifact"}
  ],
  "dump_paragraph_locations": [
    {"artifact": "...", "paragraph_index": N, "kind": "...",
     "matched_keywords": [...], "excerpt": "...", "keyword_ratio"?: F}
  ],
  "thresholds_applied": {
    "max_density_pct": 1.5,
    "max_repetitions_per_artifact": 3,
    "dump_paragraph_min_tokens": 15,
    "dump_paragraph_max_keyword_ratio": 0.30,
    "comma_run_min_tokens": 4
  }
}
```

The `thresholds_applied` block is the shallow-merge output of
`yaml_config.resolve_keyword_stuffing_thresholds(config, channel)` — i.e. the
effective per-run thresholds — so historical drift logs stay correlatable
with config changes (mirrors Story 4.3's `content_loss.config_snapshot`).
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobhunter.keyword_stuffing_matcher import KeywordStuffingCheck
from jobhunter.metadata import now_iso8601_utc


__all__ = [
    "DRIFT_REPORT_NAME",
    "KEYWORD_STUFFING_KEY",
    "write_keyword_stuffing_block",
]


DRIFT_REPORT_NAME = "package.drift.json"
KEYWORD_STUFFING_KEY = "keyword_stuffing"


def write_keyword_stuffing_block(
    out_dir: Path,
    check: KeywordStuffingCheck,
    *,
    channel: str,
    thresholds_applied: dict[str, Any],
    ran_at: datetime | None = None,
) -> Path:
    """Write the `keyword_stuffing` block to `package.drift.json` atomically.

    Reads the existing drift report (if present), updates ONLY the
    `keyword_stuffing` top-level key with this run's results, writes back via
    tmp + os.replace. Sibling keys (`fabrication_check`, `content_loss`) are
    preserved byte-for-byte unchanged. AC7 idempotency: the `keyword_stuffing`
    block is replaced wholesale on re-run.
    """
    target = out_dir / DRIFT_REPORT_NAME
    document = _load_existing_document(target)
    document[KEYWORD_STUFFING_KEY] = _build_keyword_stuffing_payload(
        check,
        channel=channel,
        thresholds_applied=thresholds_applied,
        ran_at=ran_at,
    )
    _atomic_write_json(target, document)
    return target


# ---- internal helpers ----------------------------------------------------


def _load_existing_document(target: Path) -> dict[str, Any]:
    """Read *target* if it exists; tolerate a missing or malformed file.

    A defensively-empty dict is returned when the file is absent or cannot be
    parsed as a JSON object — mirrors `content_loss_writer._load_existing_document`
    so the same defensive behavior applies to all three drift dimensions.
    """
    if not target.is_file():
        return {}
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _build_keyword_stuffing_payload(
    check: KeywordStuffingCheck,
    *,
    channel: str,
    thresholds_applied: dict[str, Any],
    ran_at: datetime | None,
) -> dict[str, Any]:
    """Project a `KeywordStuffingCheck` into the documented on-disk shape (AC1)."""
    moment = ran_at if ran_at is not None else datetime.now(timezone.utc)
    return {
        "verdict": check.verdict,
        "channel": channel,
        "ran_at": now_iso8601_utc(moment),
        "density_violations": [
            dataclasses.asdict(violation)
            for violation in check.density_violations
        ],
        # `dump_paragraph_locations` is already a list[dict] (Story 5.2 shape)
        # so a shallow copy is enough — guarantees the on-disk list is not the
        # same Python object as the matcher result.
        "dump_paragraph_locations": [
            dict(location) for location in check.dump_paragraph_locations
        ],
        "thresholds_applied": dict(thresholds_applied),
    }


def _atomic_write_json(target: Path, document: dict[str, Any]) -> None:
    """Write *document* to *target* via tmp + os.replace (POSIX atomic)."""
    tmp_path = target.with_name(".package.drift.tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, target)
