"""Unit tests for `jobhunter.held_package` (Story 3.4 AC1 + AC3).

Mirrors the Story 3.2 unit-test patterns: pure-function assertions, frozen
dataclasses, no LLM call, deterministic timestamps via injected `now`. The
held-package module itself has no LLM call so there is no test seam to stub
beyond the optional `now` and `retention_days` arguments.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobhunter.fabrication_matcher import UnsourcedClaim
from jobhunter.held_package import (
    AUDIT_LOG_NAME,
    HELD_SIDECAR_NAME,
    HeldPackageRecord,
    compose_held_record,
    sweep_expired,
    write_held_sidecar,
)

FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=UTC)
EXPECTED_HELD_AT = "2026-05-24T03:15:30Z"
EXPECTED_EXPIRES_AT_7D = "2026-05-31T03:15:30Z"


def _claim(
    text: str,
    *,
    line: int = 1,
    source: str = "cv",
    reason: str = "no_canonical_match",
) -> UnsourcedClaim:
    return UnsourcedClaim(
        claim_id=f"{source}:{line}:abcd1234",
        claim_text=text,
        source_artifact=source,
        line_number=line,
        reason=reason,
    )


# ---- AC1: compose_held_record shape --------------------------------------


def test_compose_held_record_populates_all_fields(tmp_path: Path) -> None:
    (tmp_path / "cv.md").write_text("# CV\n- pytest\n", encoding="utf-8")
    record = compose_held_record(
        [_claim("pytest", line=2)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    assert isinstance(record, HeldPackageRecord)
    assert record.held_at == EXPECTED_HELD_AT
    assert record.held_by_check == "fabrication"
    assert record.retention_expires_at == EXPECTED_EXPIRES_AT_7D
    assert record.recoverable is True
    assert len(record.failed_claims) == 1


def test_compose_held_record_with_empty_unsourced_yields_no_failed_claims(
    tmp_path: Path,
) -> None:
    record = compose_held_record([], tmp_path, now=FIXED_NOW, retention_days=7)
    assert record.failed_claims == []


def test_compose_held_record_carries_documented_failed_claim_fields(
    tmp_path: Path,
) -> None:
    (tmp_path / "cv.md").write_text("# CV\n- pytest\n", encoding="utf-8")
    record = compose_held_record(
        [_claim("pytest", line=2)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    failed = record.failed_claims[0]
    assert failed.claim_id == "cv:2:abcd1234"
    assert failed.claim_text == "pytest"
    assert failed.source_artifact == "cv"
    assert failed.line_number == 2
    assert failed.reason == "no_canonical_match"
    assert failed.artifact_path == str(tmp_path / "cv.md")


def test_failed_claim_column_offsets_pin_first_occurrence_on_line(
    tmp_path: Path,
) -> None:
    # Line 2 is "- pytest". The first occurrence of "pytest" starts at
    # column 2 (0-indexed) and ends at column 8 (exclusive).
    (tmp_path / "cv.md").write_text("# CV\n- pytest\n", encoding="utf-8")
    record = compose_held_record(
        [_claim("pytest", line=2)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    failed = record.failed_claims[0]
    assert failed.column_start == 2
    assert failed.column_end == 8


def test_failed_claim_columns_fall_back_when_artifact_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    # No cv.md on disk -> column offsets degrade to (0, len(claim_text))
    # and a WARNING is logged.
    caplog.set_level(logging.WARNING, logger="jobhunter.held_package")
    record = compose_held_record(
        [_claim("pytest", line=1)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    failed = record.failed_claims[0]
    assert failed.column_start == 0
    assert failed.column_end == len("pytest")
    assert any(
        "could not read" in r.message for r in caplog.records
    )


def test_failed_claim_columns_fall_back_when_claim_text_absent_on_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "cv.md").write_text("# Heading only\n", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="jobhunter.held_package")
    record = compose_held_record(
        [_claim("pytest", line=1)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    failed = record.failed_claims[0]
    assert failed.column_start == 0
    assert failed.column_end == len("pytest")
    assert any("not found on line" in r.message for r in caplog.records)


def test_failed_claim_columns_fall_back_when_line_out_of_range(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    (tmp_path / "cv.md").write_text("only one line\n", encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="jobhunter.held_package")
    record = compose_held_record(
        [_claim("pytest", line=99)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    failed = record.failed_claims[0]
    assert failed.column_start == 0
    assert failed.column_end == len("pytest")
    assert any("out of range" in r.message for r in caplog.records)


def test_compose_held_record_artifact_path_maps_source_artifact(
    tmp_path: Path,
) -> None:
    """`source_artifact` keys translate to the right on-disk filenames."""
    (tmp_path / "cover-letter.md").write_text("Hello pytest\n", encoding="utf-8")
    (tmp_path / "upwork-proposal.md").write_text("I use pytest\n", encoding="utf-8")
    record = compose_held_record(
        [
            _claim("pytest", line=1, source="cover_letter"),
            _claim("pytest", line=1, source="upwork_proposal"),
        ],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    paths = {fc.source_artifact: fc.artifact_path for fc in record.failed_claims}
    assert paths["cover_letter"] == str(tmp_path / "cover-letter.md")
    assert paths["upwork_proposal"] == str(tmp_path / "upwork-proposal.md")


def test_compose_held_record_retention_window_scales_with_retention_days(
    tmp_path: Path,
) -> None:
    record_3 = compose_held_record(
        [], tmp_path, now=FIXED_NOW, retention_days=3
    )
    record_30 = compose_held_record(
        [], tmp_path, now=FIXED_NOW, retention_days=30
    )
    assert record_3.retention_expires_at == "2026-05-27T03:15:30Z"
    assert record_30.retention_expires_at == "2026-06-23T03:15:30Z"


# ---- AC1: write_held_sidecar atomic JSON write ---------------------------


def test_write_held_sidecar_emits_package_held_json(tmp_path: Path) -> None:
    record = compose_held_record(
        [], tmp_path, now=FIXED_NOW, retention_days=7
    )
    target = write_held_sidecar(tmp_path, record)
    assert target == tmp_path / HELD_SIDECAR_NAME
    assert target.exists()


def test_write_held_sidecar_payload_parses_as_json(tmp_path: Path) -> None:
    (tmp_path / "cv.md").write_text("- pytest\n", encoding="utf-8")
    record = compose_held_record(
        [_claim("pytest", line=1)],
        tmp_path,
        now=FIXED_NOW,
        retention_days=7,
    )
    write_held_sidecar(tmp_path, record)
    data = json.loads((tmp_path / HELD_SIDECAR_NAME).read_text(encoding="utf-8"))
    assert data["held_at"] == EXPECTED_HELD_AT
    assert data["held_by_check"] == "fabrication"
    assert data["retention_expires_at"] == EXPECTED_EXPIRES_AT_7D
    assert data["recoverable"] is True
    assert isinstance(data["failed_claims"], list)
    fc = data["failed_claims"][0]
    assert set(fc.keys()) == {
        "claim_id",
        "claim_text",
        "source_artifact",
        "line_number",
        "reason",
        "artifact_path",
        "column_start",
        "column_end",
    }


def test_write_held_sidecar_atomic_tmp_does_not_remain(tmp_path: Path) -> None:
    record = compose_held_record(
        [], tmp_path, now=FIXED_NOW, retention_days=7
    )
    write_held_sidecar(tmp_path, record)
    files = {p.name for p in tmp_path.iterdir()}
    assert HELD_SIDECAR_NAME in files
    assert ".package.held.tmp" not in files


# ---- AC3: sweep_expired -------------------------------------------------


def _write_held_fixture(
    out_root: Path,
    slug: str,
    *,
    held_at: datetime,
    expires_at: datetime,
    failed_claims_count: int = 1,
) -> Path:
    """Write a synthetic held package under `out_root/slug/` with set timestamps."""
    pkg = out_root / slug
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "cv.md").write_text("- pytest\n", encoding="utf-8")
    (pkg / "package.held.json").write_text(
        json.dumps(
            {
                "held_at": held_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "held_by_check": "fabrication",
                "failed_claims": [{"x": i} for i in range(failed_claims_count)],
                "retention_expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "recoverable": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return pkg


def test_sweep_expired_returns_empty_when_out_root_missing(tmp_path: Path) -> None:
    assert sweep_expired(tmp_path / "out", now=FIXED_NOW, retention_days=7) == []


def test_sweep_expired_returns_empty_when_no_held_packages(tmp_path: Path) -> None:
    out_root = tmp_path / "out"
    out_root.mkdir()
    (out_root / "20260524t000000z-foo").mkdir()
    (out_root / "20260524t000000z-foo" / "cv.md").write_text("hi\n", encoding="utf-8")
    assert sweep_expired(out_root, now=FIXED_NOW, retention_days=7) == []


def test_sweep_expired_discards_packages_past_retention(tmp_path: Path) -> None:
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)  # 3 days in the past
    pkg = _write_held_fixture(
        out_root, "stale-slug", held_at=held_at, expires_at=expires_at
    )
    assert pkg.exists()
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == ["stale-slug"]
    assert not pkg.exists()


def test_sweep_expired_preserves_packages_inside_retention(tmp_path: Path) -> None:
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=2)
    expires_at = held_at + timedelta(days=7)  # 5 days in the future
    pkg = _write_held_fixture(
        out_root, "fresh-slug", held_at=held_at, expires_at=expires_at
    )
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == []
    assert pkg.exists()


def test_sweep_expired_writes_audit_log_entry_per_discard(tmp_path: Path) -> None:
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    _write_held_fixture(
        out_root,
        "stale-slug",
        held_at=held_at,
        expires_at=expires_at,
        failed_claims_count=3,
    )
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)

    audit_path = out_root / AUDIT_LOG_NAME
    assert audit_path.is_file()
    lines = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["slug"] == "stale-slug"
    assert entry["held_at"] == held_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert entry["discarded_at"] == EXPECTED_HELD_AT
    assert entry["failed_claims_count"] == 3


def test_sweep_expired_audit_log_accumulates_across_invocations(
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    _write_held_fixture(out_root, "stale-a", held_at=held_at, expires_at=expires_at)
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    _write_held_fixture(out_root, "stale-b", held_at=held_at, expires_at=expires_at)
    sweep_expired(out_root, now=FIXED_NOW, retention_days=7)

    lines = [
        json.loads(line)
        for line in (out_root / AUDIT_LOG_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    slugs = [entry["slug"] for entry in lines]
    assert slugs == ["stale-a", "stale-b"]


def test_sweep_expired_skips_malformed_sidecar_and_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    out_root = tmp_path / "out"
    held_at = FIXED_NOW - timedelta(days=10)
    expires_at = held_at + timedelta(days=7)
    # One malformed sidecar (invalid JSON), one good expired one.
    bad = out_root / "bad-slug"
    bad.mkdir(parents=True)
    (bad / "package.held.json").write_text("not json", encoding="utf-8")
    good = _write_held_fixture(
        out_root, "good-slug", held_at=held_at, expires_at=expires_at
    )

    caplog.set_level(logging.WARNING, logger="jobhunter.held_package")
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == ["good-slug"]
    assert bad.exists()  # malformed sidecar is not destroyed
    assert not good.exists()


def test_sweep_expired_skips_sidecar_missing_retention_expires_at(
    tmp_path: Path, caplog: pytest.LogCaptureFixture,
) -> None:
    out_root = tmp_path / "out"
    pkg = out_root / "broken-slug"
    pkg.mkdir(parents=True)
    (pkg / "package.held.json").write_text(
        json.dumps({"held_at": EXPECTED_HELD_AT, "held_by_check": "fabrication"})
        + "\n",
        encoding="utf-8",
    )
    caplog.set_level(logging.WARNING, logger="jobhunter.held_package")
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == []
    assert pkg.exists()


def test_sweep_expired_at_exact_retention_expiry_is_discarded(
    tmp_path: Path,
) -> None:
    """`retention_expires_at == now` is treated as expired (boundary at `>`)."""
    out_root = tmp_path / "out"
    _write_held_fixture(
        out_root,
        "boundary-slug",
        held_at=FIXED_NOW - timedelta(days=7),
        expires_at=FIXED_NOW,
    )
    discarded = sweep_expired(out_root, now=FIXED_NOW, retention_days=7)
    assert discarded == ["boundary-slug"]


# ---- AC2 (structural): no notification module is imported ----------------


def test_held_package_module_does_not_import_any_notification_module() -> None:
    """AC2 structural contract: the held branch never touches a notify module.

    Walks the held_package module's AST and asserts no Import / ImportFrom
    node names a notification surface (`notify`, `gchat`, `google_chat`,
    `webhook`). Holding the contract structurally — rather than at runtime
    — guarantees no held-state code path can ever fire a notification, even
    by accident.
    """
    import ast

    import jobhunter.held_package as held_package_module

    source = Path(held_package_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = ("notify", "gchat", "google_chat", "webhook")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                lowered = alias.name.lower()
                for needle in forbidden:
                    assert needle not in lowered, (
                        f"held_package.py imports forbidden module: {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module_name = (node.module or "").lower()
            for needle in forbidden:
                assert needle not in module_name, (
                    f"held_package.py imports from forbidden module: {node.module}"
                )
