"""Story 6.5 AC3: per-discard audit log entry shape.

Story 3.4 already wrote four fields (`slug`, `held_at`, `discarded_at`,
`failed_claims_count`). Story 6.5 extends the entry additively with three
fields read from the discarded slug's `metadata.json`:

- `source_board` — the JD's source board (`upwork`, `linkedin`, ...).
- `drift_fail_reason` — comma-joined sorted list of `drift_verdicts` keys
  whose value is `"fail"` (e.g. `"fabrication"`, `"content_loss,fabrication"`).
- `created_at` — the package's creation timestamp from metadata.

A missing or malformed `metadata.json` yields empty-string fields rather
than aborting the discard — the sweep is best-effort and must always tidy
the directory even if metadata cannot be read.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobhunter.held_package import AUDIT_LOG_NAME, HELD_SIDECAR_NAME, sweep_expired

FIXED_NOW = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)


def _write_held_with_metadata(
    out_root: Path,
    slug: str,
    *,
    held_at: datetime,
    expires_at: datetime,
    source_board: str | None = "upwork",
    created_at: str | None = "2026-05-13T12:00:00Z",
    drift_verdicts: dict[str, str] | None = None,
    write_metadata: bool = True,
    malformed_metadata: bool = False,
) -> Path:
    """Stage a held package with a co-located metadata.json (Story 6.5 AC3)."""
    pkg = out_root / slug
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "cv.md").write_text("- pytest\n", encoding="utf-8")
    (pkg / HELD_SIDECAR_NAME).write_text(
        json.dumps(
            {
                "held_at": held_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "held_by_check": "fabrication",
                "failed_claims": [{"x": i} for i in range(2)],
                "retention_expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "recoverable": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if malformed_metadata:
        (pkg / "metadata.json").write_text("not json", encoding="utf-8")
    elif write_metadata:
        verdicts = drift_verdicts or {
            "fabrication": "fail",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        }
        (pkg / "metadata.json").write_text(
            json.dumps(
                {
                    "slug": slug,
                    "source_board": source_board,
                    "created_at": created_at,
                    "drift_verdicts": verdicts,
                }
            )
            + "\n",
            encoding="utf-8",
        )
    return pkg


def _read_audit(out_root: Path) -> list[dict]:
    audit_path = out_root / AUDIT_LOG_NAME
    if not audit_path.is_file():
        return []
    return [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---- AC3: audit file is named `_discarded.log` --------------------------


def test_audit_log_filename_is_discarded_log() -> None:
    """Story 6.5 AC3 literal: the audit file is `_discarded.log`."""
    assert AUDIT_LOG_NAME == "_discarded.log"


# ---- AC3: extended audit entry shape ------------------------------------


def test_audit_entry_includes_source_board_drift_reason_created_at(
    tmp_path: Path,
) -> None:
    """A discard with full metadata writes all seven fields."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)  # 3 days past
    _write_held_with_metadata(
        out_root,
        "stale-slug",
        held_at=held_at,
        expires_at=expires_at,
        source_board="linkedin",
        created_at="2026-05-13T12:00:00Z",
        drift_verdicts={
            "fabrication": "fail",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
    )
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    entries = _read_audit(out_root)
    assert len(entries) == 1
    entry = entries[0]
    # Story 3.4 fields still present.
    assert entry["slug"] == "stale-slug"
    assert entry["failed_claims_count"] == 2
    assert entry["discarded_at"].endswith("Z")
    # Story 6.5 AC3 additive fields.
    assert entry["source_board"] == "linkedin"
    assert entry["drift_fail_reason"] == "fabrication"
    assert entry["created_at"] == "2026-05-13T12:00:00Z"


def test_audit_entry_drift_fail_reason_joins_multiple_failing_checks(
    tmp_path: Path,
) -> None:
    """When multiple checks fail, `drift_fail_reason` is the sorted comma-joined set."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    _write_held_with_metadata(
        out_root,
        "multi-fail",
        held_at=held_at,
        expires_at=expires_at,
        drift_verdicts={
            "fabrication": "fail",
            "content_loss": "fail",
            "keyword_stuffing": "pass",
        },
    )
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    entries = _read_audit(out_root)
    assert len(entries) == 1
    # Sorted alphabetically -> `content_loss,fabrication`.
    assert entries[0]["drift_fail_reason"] == "content_loss,fabrication"


def test_audit_entry_drift_fail_reason_empty_when_no_check_failed(
    tmp_path: Path,
) -> None:
    """A held sidecar whose metadata shows all-pass verdicts records an empty reason."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    _write_held_with_metadata(
        out_root,
        "weird-slug",
        held_at=held_at,
        expires_at=expires_at,
        drift_verdicts={
            "fabrication": "pass",
            "content_loss": "pass",
            "keyword_stuffing": "pass",
        },
    )
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    entries = _read_audit(out_root)
    assert len(entries) == 1
    assert entries[0]["drift_fail_reason"] == ""


def test_audit_entry_fields_empty_when_metadata_json_missing(
    tmp_path: Path,
) -> None:
    """A held package without metadata.json still discards; new fields are empty strings."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    pkg = _write_held_with_metadata(
        out_root,
        "no-meta",
        held_at=held_at,
        expires_at=expires_at,
        write_metadata=False,
    )
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == ["no-meta"]
    assert not pkg.exists()
    entries = _read_audit(out_root)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_board"] == ""
    assert entry["drift_fail_reason"] == ""
    assert entry["created_at"] == ""


def test_audit_entry_fields_empty_when_metadata_json_malformed(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A held package with malformed metadata.json still discards; warns + empty fields."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    pkg = _write_held_with_metadata(
        out_root,
        "bad-meta",
        held_at=held_at,
        expires_at=expires_at,
        malformed_metadata=True,
    )
    caplog.set_level(logging.WARNING, logger="jobhunter.held_package")
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == ["bad-meta"]
    assert not pkg.exists()
    entries = _read_audit(out_root)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source_board"] == ""
    assert entry["drift_fail_reason"] == ""
    assert entry["created_at"] == ""


# ---- AC3: per-discard ISO 8601 timestamp + grep-friendly NDJSON --------


def test_audit_log_is_grep_friendly_ndjson(tmp_path: Path) -> None:
    """One JSON object per line; each line parses cleanly with json.loads."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    for slug in ("slug-a", "slug-b", "slug-c"):
        _write_held_with_metadata(
            out_root, slug, held_at=held_at, expires_at=expires_at
        )
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    text = (out_root / AUDIT_LOG_NAME).read_text(encoding="utf-8")
    # Trailing newline; three lines; each independently parses.
    assert text.endswith("\n")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert "slug" in record
        assert "discarded_at" in record
        assert record["discarded_at"].endswith("Z")


# ---- AC2: idempotency + AC1: TTL=0 short-circuits -----------------------


def test_sweep_is_idempotent_running_twice_changes_nothing(tmp_path: Path) -> None:
    """Story 6.5 AC2: a second sweep immediately after the first is a no-op."""
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    _write_held_with_metadata(
        out_root, "stale-once", held_at=held_at, expires_at=expires_at
    )
    first = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert first == ["stale-once"]
    audit_after_first = (out_root / AUDIT_LOG_NAME).read_text(encoding="utf-8")
    # Second sweep with no new fixtures: nothing to do.
    second = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert second == []
    audit_after_second = (out_root / AUDIT_LOG_NAME).read_text(encoding="utf-8")
    # The audit log is unchanged across the second invocation.
    assert audit_after_first == audit_after_second


def test_sweep_with_retention_days_zero_is_a_no_op(tmp_path: Path) -> None:
    """Story 6.5 AC1: `retention_days=0` disables the sweep entirely.

    Even a package whose `retention_expires_at` is firmly in the past is
    NOT removed, and no audit entry is written. Mirrors the
    `held_package_ttl_days: 0` config-yaml contract.
    """
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=30)
    expires_at = held_at + timedelta(days=1)  # ~29 days in the past
    pkg = _write_held_with_metadata(
        out_root, "ancient", held_at=held_at, expires_at=expires_at
    )
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=0)
    assert discarded == []
    assert pkg.exists()
    # No audit log was created — the sweep short-circuited before any I/O.
    assert not (out_root / AUDIT_LOG_NAME).is_file()


def test_sweep_with_retention_days_zero_on_missing_root_is_a_no_op(
    tmp_path: Path,
) -> None:
    """The TTL=0 short-circuit applies even when out_root does not exist."""
    assert sweep_expired(
        tmp_path / "nonexistent", now=FIXED_NOW, retention_days=0
    ) == []
