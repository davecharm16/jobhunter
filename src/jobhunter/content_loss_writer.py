"""Content-loss drift-report writer (Story 4.2).

Persists Story 4.1's `ContentLossCheck` verdict + per-entry detail to
`./out/<slug>/package.drift.json` under the top-level `content_loss` key. The
writer is intentionally split from `fabrication_matcher.write_drift_report`
(Story 3.2) so each drift dimension owns its own sibling block: this module
reads the existing file (if any), updates ONLY its `content_loss` key, and
writes back atomically. Sibling keys (`fabrication_check` from Story 3.2,
`keyword_stuffing` from Epic 5 when it lands) are preserved unchanged.

On-disk shape under `content_loss`:

```
{
  "verdict": "pass" | "fail",
  "check_version": "v1",
  "ran_at": "<ISO-8601 UTC with Z suffix>",
  "preserved_entries": [
    {"entry_id": "...", "section": "...", "matched_in": ["cv.md"],
     "match_type": "substring"}
  ],
  "dropped_entries": [
    {"entry_id": "...", "section": "...", "primary_text": "...",
     "jd_requirements_addressed": ["typescript"], "reason": "silently_lost"}
  ]
}
```

Reason codes are enumerated (`VALID_REASON_CODES`) and hard-coded in this
story; Story 4.3 will move them to `config.yaml`
(`drift.content_loss.reason_codes`). Atomic write idiom (tmp + os.replace)
mirrors `fabrication_matcher.write_drift_report` and the rest of the pipeline.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobhunter.content_loss_matcher import ContentLossCheck
from jobhunter.metadata import now_iso8601_utc


__all__ = [
    "CONTENT_LOSS_KEY",
    "DRIFT_REPORT_NAME",
    "VALID_REASON_CODES",
    "write_content_loss_block",
]


DRIFT_REPORT_NAME = "package.drift.json"
CONTENT_LOSS_KEY = "content_loss"

# AC2: enumerated, fail-discriminating reason codes for `dropped_entries[].reason`.
# `irrelevant_to_jd` -> drop is logged-rationale, does NOT contribute to fail.
# `silently_lost`    -> drop is JD-relevant and absent, contributes to fail.
# Hard-coded for Story 4.2; Story 4.3 future tunable lives at
# `drift.content_loss.reason_codes` in `config.yaml`.
VALID_REASON_CODES: tuple[str, ...] = ("irrelevant_to_jd", "silently_lost")


def write_content_loss_block(
    out_dir: Path,
    check: ContentLossCheck,
    *,
    ran_at: datetime | None = None,
    check_version: str = "v1",
) -> Path:
    """Write the `content_loss` block to `package.drift.json` atomically.

    Reads the existing drift report (if present), updates ONLY the
    `content_loss` top-level key with this run's results, writes back via
    tmp + os.replace. Sibling keys (e.g. `fabrication_check` from Story 3.2)
    are preserved byte-for-byte unchanged. AC4 idempotency: the `content_loss`
    block is replaced wholesale on re-run — preserved/dropped arrays from a
    previous run never bleed into this one.
    """
    target = out_dir / DRIFT_REPORT_NAME
    document = _load_existing_document(target)
    document[CONTENT_LOSS_KEY] = _build_content_loss_payload(
        check, ran_at=ran_at, check_version=check_version
    )
    _atomic_write_json(target, document)
    return target


# ---- internal helpers ----------------------------------------------------


def _load_existing_document(target: Path) -> dict[str, Any]:
    """Read *target* if it exists; tolerate a missing or malformed file.

    A defensively-empty dict is returned when the file is absent or cannot be
    parsed as a JSON object — this preserves the AC1 contract that the writer
    can create the file from scratch if no prior drift block exists. The
    "malformed" branch is not expected in normal pipeline flow (Story 3.2
    writes the file first) but is tolerated so a hand-edited drift report
    doesn't crash the next run.
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


def _build_content_loss_payload(
    check: ContentLossCheck,
    *,
    ran_at: datetime | None,
    check_version: str,
) -> dict[str, Any]:
    """Project a `ContentLossCheck` into the documented on-disk shape (AC1)."""
    moment = ran_at if ran_at is not None else datetime.now(timezone.utc)
    return {
        "verdict": check.verdict,
        "check_version": check_version,
        "ran_at": now_iso8601_utc(moment),
        "preserved_entries": [
            {
                "entry_id": entry.entry_id,
                "section": entry.section,
                "matched_in": list(entry.matched_in),
                "match_type": entry.match_type,
            }
            for entry in check.preserved_entries
        ],
        "dropped_entries": [
            {
                "entry_id": entry.entry_id,
                "section": entry.section,
                "primary_text": entry.primary_text,
                "jd_requirements_addressed": list(entry.jd_requirements_addressed),
                "reason": entry.reason,
            }
            for entry in check.dropped_entries
        ],
    }


def _atomic_write_json(target: Path, document: dict[str, Any]) -> None:
    """Write *document* to *target* via tmp + os.replace (POSIX atomic)."""
    tmp_path = target.with_name(".package.drift.tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, target)
