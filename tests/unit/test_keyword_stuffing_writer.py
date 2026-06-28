"""Unit tests for `jobhunter.keyword_stuffing_writer` (Story 5.3 AC1, AC7).

Mirrors `tests/unit/test_content_loss_writer.py` (Story 4.2): pure-function
assertions, deterministic timestamps via injected `ran_at`, atomic-write
checks, sibling-key preservation across drift dimensions. No LLM stubs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jobhunter.keyword_stuffing_matcher import (
    DensityViolation,
    KeywordStuffingCheck,
)
from jobhunter.keyword_stuffing_writer import (
    DRIFT_REPORT_NAME,
    KEYWORD_STUFFING_KEY,
    write_keyword_stuffing_block,
)

FIXED_RAN_AT = datetime(2026, 5, 24, 3, 15, 30, tzinfo=UTC)
EXPECTED_RAN_AT_STR = "2026-05-24T03:15:30Z"

_DEFAULT_THRESHOLDS = {
    "max_density_pct": 1.5,
    "max_repetitions_per_artifact": 3,
    "dump_paragraph_min_tokens": 15,
    "dump_paragraph_max_keyword_ratio": 0.30,
    "comma_run_min_tokens": 4,
}


def _fabrication_block() -> dict:
    return {
        "verdict": "pass",
        "claims_total": 1,
        "claims_sourced": 1,
        "claims_unsourced": 0,
        "traces": [],
        "unsourced_claims": [],
    }


def _content_loss_block() -> dict:
    return {
        "verdict": "pass",
        "check_version": "v1",
        "ran_at": "2026-05-24T00:00:00Z",
        "preserved_entries": [],
        "dropped_entries": [],
    }


def _density_violation(keyword: str = "python") -> DensityViolation:
    return DensityViolation(
        keyword=keyword,
        artifact="cv.md",
        occurrences=10,
        total_tokens=50,
        density_pct=20.0,
        threshold_breached="max_density_pct",
    )


# ---- AC1: on-disk shape ---------------------------------------------------


def test_writer_creates_drift_json_with_keyword_stuffing_key(tmp_path: Path) -> None:
    """When `package.drift.json` does not exist, the writer creates it with
    `keyword_stuffing` as the sole top-level key (AC1 defensive branch)."""
    check = KeywordStuffingCheck(verdict="pass")
    target = write_keyword_stuffing_block(
        tmp_path,
        check,
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )

    assert target == tmp_path / DRIFT_REPORT_NAME
    assert target.exists()
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert set(doc.keys()) == {KEYWORD_STUFFING_KEY}


def test_writer_emits_documented_shape(tmp_path: Path) -> None:
    """AC1 shape: verdict / channel / ran_at / density_violations /
    dump_paragraph_locations / thresholds_applied."""
    check = KeywordStuffingCheck(
        verdict="fail",
        density_violations=[_density_violation()],
        dump_paragraph_locations=[
            {
                "artifact": "cv.md",
                "paragraph_index": 2,
                "kind": "keyword_dump_paragraph",
                "keyword_ratio": 0.5,
                "matched_keywords": ["python", "fastapi"],
                "excerpt": "Python fastapi sql redis",
            }
        ],
    )
    write_keyword_stuffing_block(
        tmp_path,
        check,
        channel="upwork",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))

    block = doc[KEYWORD_STUFFING_KEY]
    assert set(block.keys()) == {
        "verdict",
        "channel",
        "ran_at",
        "density_violations",
        "dump_paragraph_locations",
        "thresholds_applied",
    }
    assert block["verdict"] == "fail"
    assert block["channel"] == "upwork"
    assert block["ran_at"] == EXPECTED_RAN_AT_STR


def test_density_violation_carries_documented_six_field_shape(tmp_path: Path) -> None:
    """AC1: each density violation serializes to the Story 5.1 dataclass shape."""
    check = KeywordStuffingCheck(
        verdict="fail",
        density_violations=[_density_violation(keyword="fastapi")],
    )
    write_keyword_stuffing_block(
        tmp_path,
        check,
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    entry = doc[KEYWORD_STUFFING_KEY]["density_violations"][0]
    assert set(entry.keys()) == {
        "keyword",
        "artifact",
        "occurrences",
        "total_tokens",
        "density_pct",
        "threshold_breached",
    }
    assert entry["keyword"] == "fastapi"
    assert entry["threshold_breached"] == "max_density_pct"


def test_dump_paragraph_location_preserves_story_5_2_shape(tmp_path: Path) -> None:
    """AC1: dump-paragraph + comma-run dicts pass through unchanged."""
    check = KeywordStuffingCheck(
        verdict="fail",
        dump_paragraph_locations=[
            {
                "artifact": "cover-letter.md",
                "paragraph_index": 1,
                "kind": "comma_run_violation",
                "matched_keywords": ["python", "node", "redis", "postgres"],
                "excerpt": "Python, Node, Redis, Postgres",
            }
        ],
    )
    write_keyword_stuffing_block(
        tmp_path,
        check,
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    location = doc[KEYWORD_STUFFING_KEY]["dump_paragraph_locations"][0]
    assert location["kind"] == "comma_run_violation"
    assert location["artifact"] == "cover-letter.md"
    assert location["matched_keywords"] == ["python", "node", "redis", "postgres"]


def test_thresholds_applied_records_resolved_values(tmp_path: Path) -> None:
    """AC1 + AC3: `thresholds_applied` carries the per-run resolved threshold dict."""
    upwork_resolved = {
        "max_density_pct": 1.5,
        "max_repetitions_per_artifact": 5,  # Upwork override
        "dump_paragraph_min_tokens": 15,
        "dump_paragraph_max_keyword_ratio": 0.45,  # Upwork override
        "comma_run_min_tokens": 4,
    }
    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="upwork",
        thresholds_applied=upwork_resolved,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads((tmp_path / DRIFT_REPORT_NAME).read_text(encoding="utf-8"))
    assert doc[KEYWORD_STUFFING_KEY]["thresholds_applied"] == upwork_resolved


def test_writer_atomic_idiom_leaves_no_tmp_after_success(tmp_path: Path) -> None:
    """Atomic write idiom: no `.package.drift.tmp` left on disk."""
    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    files = {p.name for p in tmp_path.iterdir()}
    assert ".package.drift.tmp" not in files
    assert DRIFT_REPORT_NAME in files


# ---- AC7: idempotency + sibling-key preservation --------------------------


def test_writer_preserves_existing_fabrication_check_sibling(tmp_path: Path) -> None:
    """AC7: a pre-existing `fabrication_check` block survives the rewrite byte-for-byte."""
    target = tmp_path / DRIFT_REPORT_NAME
    fabrication = _fabrication_block()
    target.write_text(
        json.dumps({"fabrication_check": fabrication}) + "\n", encoding="utf-8"
    )

    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["fabrication_check"] == fabrication
    assert KEYWORD_STUFFING_KEY in doc


def test_writer_preserves_existing_content_loss_sibling(tmp_path: Path) -> None:
    """AC7: a pre-existing `content_loss` block (Story 4.2) survives unchanged."""
    target = tmp_path / DRIFT_REPORT_NAME
    content_loss = _content_loss_block()
    target.write_text(
        json.dumps({"content_loss": content_loss}) + "\n", encoding="utf-8"
    )

    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["content_loss"] == content_loss
    assert KEYWORD_STUFFING_KEY in doc


def test_writer_preserves_both_drift_siblings_simultaneously(tmp_path: Path) -> None:
    """AC1 + AC7: all three drift dimensions can coexist on one file."""
    target = tmp_path / DRIFT_REPORT_NAME
    fabrication = _fabrication_block()
    content_loss = _content_loss_block()
    target.write_text(
        json.dumps(
            {
                "fabrication_check": fabrication,
                "content_loss": content_loss,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="upwork",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["fabrication_check"] == fabrication
    assert doc["content_loss"] == content_loss
    assert set(doc.keys()) == {"fabrication_check", "content_loss", KEYWORD_STUFFING_KEY}


def test_writer_replaces_keyword_stuffing_block_wholesale_on_rerun(
    tmp_path: Path,
) -> None:
    """AC7: a previous `keyword_stuffing` block's violations do NOT bleed in."""
    target = tmp_path / DRIFT_REPORT_NAME
    target.write_text(
        json.dumps(
            {
                KEYWORD_STUFFING_KEY: {
                    "verdict": "fail",
                    "channel": "other",
                    "ran_at": "2026-01-01T00:00:00Z",
                    "density_violations": [
                        {
                            "keyword": "stale",
                            "artifact": "cv.md",
                            "occurrences": 99,
                            "total_tokens": 100,
                            "density_pct": 99.0,
                            "threshold_breached": "max_density_pct",
                        }
                    ],
                    "dump_paragraph_locations": [],
                    "thresholds_applied": {"max_density_pct": 0.5},
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="upwork",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    block = doc[KEYWORD_STUFFING_KEY]
    # Wholesale replacement — stale density violation is gone.
    assert block["verdict"] == "pass"
    assert block["density_violations"] == []
    assert block["channel"] == "upwork"
    assert block["thresholds_applied"]["max_density_pct"] == 1.5


def test_writer_tolerates_malformed_existing_drift_json(tmp_path: Path) -> None:
    """Defensive: a malformed pre-existing file does not crash the writer."""
    target = tmp_path / DRIFT_REPORT_NAME
    target.write_text("not json", encoding="utf-8")

    write_keyword_stuffing_block(
        tmp_path,
        KeywordStuffingCheck(verdict="pass"),
        channel="other",
        thresholds_applied=_DEFAULT_THRESHOLDS,
        ran_at=FIXED_RAN_AT,
    )
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert KEYWORD_STUFFING_KEY in doc
    assert doc[KEYWORD_STUFFING_KEY]["verdict"] == "pass"
