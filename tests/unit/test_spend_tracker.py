"""Unit tests for `jobhunter.spend_tracker`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from jobhunter.spend_tracker import (
    SpendCapExceeded,
    SpendLedgerCorrupt,
    check_cap_or_raise,
    current_month_key,
    current_month_total_usd,
    read_ledger,
    record_call,
)

FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=UTC)
FIXED_MONTH_KEY = "2026-05"


def test_current_month_key_returns_yyyy_mm_for_utc_now() -> None:
    assert current_month_key(FIXED_NOW) == FIXED_MONTH_KEY


def test_read_ledger_returns_empty_dict_when_file_absent(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    assert read_ledger(ledger_path) == {}


def test_current_month_total_usd_zero_for_empty_ledger() -> None:
    assert current_month_total_usd({}, FIXED_MONTH_KEY) == Decimal("0")


def test_current_month_total_usd_returns_stored_value() -> None:
    ledger = {FIXED_MONTH_KEY: {"total_usd": "24.97", "calls": 3}}
    assert current_month_total_usd(ledger, FIXED_MONTH_KEY) == Decimal("24.97")


def test_check_cap_or_raise_returns_current_when_below_cap(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({FIXED_MONTH_KEY: {"total_usd": "10.00", "calls": 2}}),
        encoding="utf-8",
    )
    current = check_cap_or_raise(
        Decimal("25.00"), now=FIXED_NOW, ledger_path=ledger_path
    )
    assert current == Decimal("10.00")


def test_check_cap_or_raise_raises_at_cap(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({FIXED_MONTH_KEY: {"total_usd": "25.00", "calls": 10}}),
        encoding="utf-8",
    )
    with pytest.raises(SpendCapExceeded) as exc_info:
        check_cap_or_raise(
            Decimal("25.00"), now=FIXED_NOW, ledger_path=ledger_path
        )
    assert exc_info.value.current_usd == Decimal("25.00")
    assert exc_info.value.cap_usd == Decimal("25.00")


def test_check_cap_or_raise_raises_above_cap(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({FIXED_MONTH_KEY: {"total_usd": "25.99", "calls": 10}}),
        encoding="utf-8",
    )
    with pytest.raises(SpendCapExceeded):
        check_cap_or_raise(
            Decimal("25.00"), now=FIXED_NOW, ledger_path=ledger_path
        )


def test_check_cap_or_raise_other_months_dont_count(tmp_path) -> None:
    """Prior-month spending must not block this month's calls."""
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({"2026-04": {"total_usd": "25.00", "calls": 100}}),
        encoding="utf-8",
    )
    current = check_cap_or_raise(
        Decimal("25.00"), now=FIXED_NOW, ledger_path=ledger_path
    )
    assert current == Decimal("0")


def test_record_call_creates_ledger_when_absent(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    record_call(Decimal("0.0042"), now=FIXED_NOW, ledger_path=ledger_path)
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data == {FIXED_MONTH_KEY: {"total_usd": "0.0042", "calls": 1}}


def test_record_call_increments_existing_total_and_calls(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({FIXED_MONTH_KEY: {"total_usd": "10.00", "calls": 5}}),
        encoding="utf-8",
    )
    record_call(Decimal("0.50"), now=FIXED_NOW, ledger_path=ledger_path)
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert Decimal(data[FIXED_MONTH_KEY]["total_usd"]) == Decimal("10.50")
    assert data[FIXED_MONTH_KEY]["calls"] == 6


def test_record_call_stores_total_as_string_not_float(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    record_call(Decimal("24.97"), now=FIXED_NOW, ledger_path=ledger_path)
    raw = ledger_path.read_text(encoding="utf-8")
    # Quoted string in JSON, not a bare number, so Decimal round-trips.
    assert '"total_usd": "24.97"' in raw


def test_record_call_atomic_write_does_not_corrupt_on_crash(
    tmp_path, monkeypatch
) -> None:
    """Simulate an `os.replace` failure mid-write — the on-disk ledger must
    remain the previous valid JSON, not be left half-written.
    """
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(
        json.dumps({FIXED_MONTH_KEY: {"total_usd": "10.00", "calls": 5}}),
        encoding="utf-8",
    )
    pristine_contents = ledger_path.read_text(encoding="utf-8")

    def raise_on_replace(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError("simulated crash during rename")

    import jobhunter.spend_tracker as st

    monkeypatch.setattr(st.os, "replace", raise_on_replace)

    with pytest.raises(OSError, match="simulated crash"):
        record_call(Decimal("1.00"), now=FIXED_NOW, ledger_path=ledger_path)

    # The original ledger is intact byte-for-byte.
    assert ledger_path.read_text(encoding="utf-8") == pristine_contents


def test_read_ledger_raises_on_corrupt_json(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text("not { valid json", encoding="utf-8")
    with pytest.raises(SpendLedgerCorrupt):
        read_ledger(ledger_path)


@pytest.mark.parametrize(
    "payload",
    ['[]', '[1, 2, 3]', '"a string"', '123', 'null', 'true'],
)
def test_read_ledger_raises_when_top_level_is_not_dict(
    tmp_path, payload: str
) -> None:
    """Review pass: a hand-edited ledger with a non-object top-level value
    must raise `SpendLedgerCorrupt`, not crash later with `AttributeError`
    inside `current_month_total_usd`. The "corruption is a hard error"
    guarantee in AC4 must hold for any malformed shape, not only invalid JSON.
    """
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text(payload, encoding="utf-8")
    with pytest.raises(SpendLedgerCorrupt, match="top-level value"):
        read_ledger(ledger_path)


def test_check_cap_or_raise_surfaces_non_object_ledger(tmp_path) -> None:
    """End-to-end: non-object ledger surfaces as `SpendLedgerCorrupt` from
    `check_cap_or_raise`, never as an uncaught AttributeError.
    """
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SpendLedgerCorrupt):
        check_cap_or_raise(
            Decimal("25.00"), now=FIXED_NOW, ledger_path=ledger_path
        )


def test_check_cap_or_raise_surfaces_corrupt_ledger(tmp_path) -> None:
    """Corrupt ledger must abort the run — silent default-to-zero would
    allow a bug to drain the wallet.
    """
    ledger_path = tmp_path / ".cost-ledger.json"
    ledger_path.write_text("garbage", encoding="utf-8")
    with pytest.raises(SpendLedgerCorrupt):
        check_cap_or_raise(
            Decimal("25.00"), now=FIXED_NOW, ledger_path=ledger_path
        )


def test_ledger_path_env_override(monkeypatch, tmp_path) -> None:
    from jobhunter import spend_tracker
    target = tmp_path / "ledger" / ".cost-ledger.json"
    monkeypatch.setenv("JOBHUNTER_LEDGER_PATH", str(target))
    assert spend_tracker._resolve_ledger_path() == target


def test_ledger_path_defaults_without_env(monkeypatch) -> None:
    from jobhunter import spend_tracker
    from jobhunter.config import PROJECT_ROOT
    monkeypatch.delenv("JOBHUNTER_LEDGER_PATH", raising=False)
    assert spend_tracker._resolve_ledger_path() == PROJECT_ROOT / spend_tracker.LEDGER_FILENAME


def test_record_call_does_not_disturb_other_months(tmp_path) -> None:
    ledger_path = tmp_path / ".cost-ledger.json"
    prior = {"2026-04": {"total_usd": "1.50", "calls": 10}}
    ledger_path.write_text(json.dumps(prior), encoding="utf-8")
    record_call(Decimal("0.25"), now=FIXED_NOW, ledger_path=ledger_path)
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert data["2026-04"] == {"total_usd": "1.50", "calls": 10}
    assert data[FIXED_MONTH_KEY] == {"total_usd": "0.25", "calls": 1}
