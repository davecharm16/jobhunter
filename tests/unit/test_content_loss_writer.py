"""Unit tests for `jobhunter.content_loss_writer` (Story 4.2 AC1, AC2, AC4).

Mirrors `test_fabrication_matcher.py`'s drift-report patterns: pure-function
assertions, deterministic timestamps via injected `ran_at`, atomic-write
checks. No LLM stubs (the writer is rule-based and consumes only the
`ContentLossCheck` produced by Story 4.1's matcher).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from jobhunter.content_loss_matcher import (
    ContentLossCheck,
    DroppedEntry,
    PreservedEntry,
)
from jobhunter.content_loss_writer import (
    CONTENT_LOSS_KEY,
    DRIFT_REPORT_NAME,
    VALID_REASON_CODES,
    write_content_loss_block,
)


FIXED_RAN_AT = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)
EXPECTED_RAN_AT_STR = "2026-05-24T03:15:30Z"


# ---- helpers --------------------------------------------------------------


def _preserved(entry_id: str, *, section: str = "work") -> PreservedEntry:
    return PreservedEntry(
        entry_id=entry_id,
        section=section,
        matched_in=["cv.md"],
        match_type="substring",
    )


def _dropped(
    entry_id: str,
    *,
    section: str = "work",
    primary_text: str = "Shipped TS service",
    jd_requirements: list[str] | None = None,
    reason: str = "silently_lost",
) -> DroppedEntry:
    return DroppedEntry(
        entry_id=entry_id,
        section=section,
        primary_text=primary_text,
        jd_requirements_addressed=list(jd_requirements or ["typescript"]),
        reason=reason,  # type: ignore[arg-type]
    )


def _fabrication_block() -> dict:
    """A synthetic Story 3.2 `fabrication_check` block for sibling-preservation tests."""
    return {
        "verdict": "pass",
        "claims_total": 1,
        "claims_sourced": 1,
        "claims_unsourced": 0,
        "traces": [
            {
                "claim_id": "cv:1:abcd",
                "claim_text": "Python",
                "matched_canonical_entry_id": "skills:abcdef01",
                "match_method": "exact_string",
                "match_score": 1.0,
            }
        ],
        "unsourced_claims": [],
    }


# ---- AC1: on-disk shape ---------------------------------------------------


def test_writer_creates_drift_json_with_content_loss_key(tmp_path: Path) -> None:
    """When `package.drift.json` does not exist, the writer creates it with
    `content_loss` as the sole top-level key (AC1 defensive branch)."""
    check = ContentLossCheck(verdict="pass")
    target = write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)

    assert target == tmp_path / DRIFT_REPORT_NAME
    assert target.exists()
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert set(doc.keys()) == {CONTENT_LOSS_KEY}


def test_writer_emits_documented_shape_under_content_loss_key(
    tmp_path: Path,
) -> None:
    """AC1 shape: verdict / check_version / ran_at / preserved / dropped."""
    check = ContentLossCheck(
        verdict="fail",
        preserved_entries=[_preserved("work[0]:12345678")],
        dropped_entries=[_dropped("work[1]:87654321")],
    )
    write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))

    block = doc[CONTENT_LOSS_KEY]
    assert set(block.keys()) == {
        "verdict",
        "check_version",
        "ran_at",
        "preserved_entries",
        "dropped_entries",
    }
    assert block["verdict"] == "fail"
    assert block["check_version"] == "v1"
    assert block["ran_at"] == EXPECTED_RAN_AT_STR


def test_preserved_entry_carries_documented_four_field_shape(
    tmp_path: Path,
) -> None:
    """AC1: each preserved entry serializes to `{entry_id, section, matched_in, match_type}`."""
    check = ContentLossCheck(
        verdict="pass",
        preserved_entries=[_preserved("work[0]:abc")],
    )
    write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    entry = doc[CONTENT_LOSS_KEY]["preserved_entries"][0]
    assert set(entry.keys()) == {
        "entry_id",
        "section",
        "matched_in",
        "match_type",
    }
    assert entry["matched_in"] == ["cv.md"]
    assert entry["match_type"] == "substring"


def test_dropped_entry_carries_documented_five_field_shape(
    tmp_path: Path,
) -> None:
    """AC1 + AC3: each dropped entry serializes to `{entry_id, section,
    primary_text, jd_requirements_addressed, reason}`."""
    check = ContentLossCheck(
        verdict="fail",
        dropped_entries=[
            _dropped(
                "work[0]:abc",
                primary_text="Shipped a TypeScript ingestion service",
                jd_requirements=["typescript", "node"],
            )
        ],
    )
    write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    entry = doc[CONTENT_LOSS_KEY]["dropped_entries"][0]
    assert set(entry.keys()) == {
        "entry_id",
        "section",
        "primary_text",
        "jd_requirements_addressed",
        "reason",
    }
    assert entry["jd_requirements_addressed"] == ["typescript", "node"]


def test_writer_atomic_idiom_leaves_no_tmp_after_success(tmp_path: Path) -> None:
    """Atomic write idiom: no `.package.drift.tmp` left on disk."""
    check = ContentLossCheck(verdict="pass")
    write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    files = {p.name for p in tmp_path.iterdir()}
    assert ".package.drift.tmp" not in files
    assert DRIFT_REPORT_NAME in files


# ---- AC2: reason codes ----------------------------------------------------


def test_valid_reason_codes_enumerate_irrelevant_and_silently_lost() -> None:
    """The enum is hard-coded for Story 4.2 (Story 4.3 moves to yaml)."""
    assert set(VALID_REASON_CODES) == {"irrelevant_to_jd", "silently_lost"}


def test_silently_lost_drop_serializes_with_canonical_reason_string(
    tmp_path: Path,
) -> None:
    check = ContentLossCheck(
        verdict="fail",
        dropped_entries=[_dropped("w[0]:abc", reason="silently_lost")],
    )
    write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    assert doc[CONTENT_LOSS_KEY]["dropped_entries"][0]["reason"] == "silently_lost"


def test_irrelevant_to_jd_drop_does_not_change_verdict_serialization(
    tmp_path: Path,
) -> None:
    """A `pass` verdict with `irrelevant_to_jd` drops is serialized as `pass`."""
    check = ContentLossCheck(
        verdict="pass",
        dropped_entries=[_dropped("w[0]:abc", reason="irrelevant_to_jd")],
    )
    write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    assert doc[CONTENT_LOSS_KEY]["verdict"] == "pass"
    assert doc[CONTENT_LOSS_KEY]["dropped_entries"][0]["reason"] == "irrelevant_to_jd"


# ---- AC4: idempotency + sibling-key preservation --------------------------


def test_writer_preserves_existing_fabrication_check_sibling(
    tmp_path: Path,
) -> None:
    """AC4: a pre-existing `fabrication_check` block survives the rewrite byte-for-byte."""
    target = tmp_path / DRIFT_REPORT_NAME
    existing = {"fabrication_check": _fabrication_block()}
    target.write_text(json.dumps(existing) + "\n", encoding="utf-8")

    write_content_loss_block(
        tmp_path,
        ContentLossCheck(verdict="pass"),
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["fabrication_check"] == _fabrication_block()
    assert CONTENT_LOSS_KEY in doc


def test_writer_replaces_existing_content_loss_block_wholesale(
    tmp_path: Path,
) -> None:
    """AC4: a previous `content_loss` block's preserved/dropped arrays do NOT
    bleed into the new run."""
    target = tmp_path / DRIFT_REPORT_NAME
    target.write_text(
        json.dumps(
            {
                "fabrication_check": _fabrication_block(),
                CONTENT_LOSS_KEY: {
                    "verdict": "fail",
                    "check_version": "v1",
                    "ran_at": "2026-05-23T12:00:00Z",
                    "preserved_entries": [],
                    "dropped_entries": [
                        {
                            "entry_id": "stale[0]:000000",
                            "section": "work",
                            "primary_text": "stale drop",
                            "jd_requirements_addressed": ["stale"],
                            "reason": "silently_lost",
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    write_content_loss_block(
        tmp_path,
        ContentLossCheck(
            verdict="pass",
            preserved_entries=[_preserved("work[0]:fresh1")],
        ),
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    # Fabrication sibling untouched (AC4 second clause).
    assert doc["fabrication_check"] == _fabrication_block()
    # Content_loss replaced wholesale: stale dropped entry is gone.
    block = doc[CONTENT_LOSS_KEY]
    assert block["verdict"] == "pass"
    assert block["dropped_entries"] == []
    assert len(block["preserved_entries"]) == 1
    assert block["preserved_entries"][0]["entry_id"] == "work[0]:fresh1"


def test_writer_re_run_with_different_check_replaces_content_loss(
    tmp_path: Path,
) -> None:
    """End-to-end AC4: write twice in succession, second wholly replaces first."""
    first = ContentLossCheck(
        verdict="fail",
        dropped_entries=[_dropped("work[0]:first1", primary_text="first run")],
    )
    write_content_loss_block(tmp_path, first, ran_at=FIXED_RAN_AT)

    second_moment = datetime(2026, 5, 25, 0, 0, 0, tzinfo=timezone.utc)
    second = ContentLossCheck(
        verdict="pass",
        preserved_entries=[_preserved("work[0]:secnd1")],
    )
    write_content_loss_block(tmp_path, second, ran_at=second_moment)

    doc = json.loads(
        (tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8")
    )
    block = doc[CONTENT_LOSS_KEY]
    assert block["verdict"] == "pass"
    assert block["ran_at"] == "2026-05-25T00:00:00Z"
    assert block["preserved_entries"][0]["entry_id"] == "work[0]:secnd1"
    assert block["dropped_entries"] == []


def test_writer_tolerates_malformed_existing_drift_json(tmp_path: Path) -> None:
    """Defensive AC1 path: a malformed pre-existing file does not crash the writer."""
    target = tmp_path / DRIFT_REPORT_NAME
    target.write_text("not json", encoding="utf-8")

    write_content_loss_block(
        tmp_path,
        ContentLossCheck(verdict="pass"),
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert CONTENT_LOSS_KEY in doc
    assert doc[CONTENT_LOSS_KEY]["verdict"] == "pass"


# ---- AC5: smoke — schema round-trips through json.loads --------------------


def test_drift_json_round_trips_through_json_loads_cleanly(tmp_path: Path) -> None:
    """AC5 smoke: the on-disk shape parses without error and the parsed dict
    carries the expected keys + types."""
    check = ContentLossCheck(
        verdict="fail",
        preserved_entries=[_preserved("work[0]:abc")],
        dropped_entries=[_dropped("work[1]:def")],
    )
    target = write_content_loss_block(tmp_path, check, ran_at=FIXED_RAN_AT)
    raw = target.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert isinstance(parsed[CONTENT_LOSS_KEY], dict)
    assert isinstance(parsed[CONTENT_LOSS_KEY]["preserved_entries"], list)
    assert isinstance(parsed[CONTENT_LOSS_KEY]["dropped_entries"], list)
    assert isinstance(parsed[CONTENT_LOSS_KEY]["verdict"], str)
    assert isinstance(parsed[CONTENT_LOSS_KEY]["check_version"], str)
    assert isinstance(parsed[CONTENT_LOSS_KEY]["ran_at"], str)
