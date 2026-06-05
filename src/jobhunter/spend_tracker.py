"""Per-month LLM-spend ledger with atomic writes and a hard cap check.

The ledger lives at `<PROJECT_ROOT>/.cost-ledger.json` and stores running totals
keyed by `YYYY-MM`. The schema is deliberately minimal for the walking
skeleton:

    {"2026-05": {"total_usd": "0.012345", "calls": 3}}

`total_usd` is serialized as a quoted string so `Decimal` round-trips cleanly.

Corruption is a hard error (`SpendLedgerCorrupt`): silently truncating real
spend history would defeat the cap. Writes go through a temp-sibling +
`os.replace()` rename so a crash mid-write cannot corrupt the ledger.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from jobhunter.config import PROJECT_ROOT


__all__ = [
    "LEDGER_FILENAME",
    "LEDGER_PATH",
    "SpendCapExceeded",
    "SpendLedgerCorrupt",
    "current_month_key",
    "current_month_total_usd",
    "check_cap_or_raise",
    "read_ledger",
    "record_call",
]


LEDGER_FILENAME = ".cost-ledger.json"


def _resolve_ledger_path() -> Path:
    """Ledger location, overridable via the JOBHUNTER_LEDGER_PATH env var.

    Container deployments point this at a file inside a mounted *directory*
    volume so the atomic temp-sibling + os.replace() write stays on one
    filesystem. A single-file bind mount would make os.replace a cross-device
    rename (EXDEV) — the write fails and spend data is lost. Defaults to
    <PROJECT_ROOT>/.cost-ledger.json for local (non-Docker) use.
    """
    override = os.environ.get("JOBHUNTER_LEDGER_PATH")
    if override and override.strip():
        return Path(override.strip())
    return PROJECT_ROOT / LEDGER_FILENAME


LEDGER_PATH: Path = _resolve_ledger_path()


class SpendLedgerCorrupt(RuntimeError):
    """Raised when the on-disk ledger exists but is not valid JSON.

    The CLI surfaces this as a clean error and refuses to run. Silently
    truncating the ledger would erase real spend history — exactly the failure
    mode the cap is supposed to prevent.
    """


class SpendCapExceeded(RuntimeError):
    """Raised when the current monthly spend has reached or exceeded the cap."""

    def __init__(self, current_usd: Decimal, cap_usd: Decimal) -> None:
        self.current_usd = current_usd
        self.cap_usd = cap_usd
        super().__init__(
            f"Monthly LLM spend cap reached: ${current_usd} of ${cap_usd}"
        )


def current_month_key(now: datetime | None = None) -> str:
    """Return the `YYYY-MM` ledger key for *now* (UTC)."""
    moment = now or datetime.now(timezone.utc)
    return moment.strftime("%Y-%m")


def read_ledger(ledger_path: Path | None = None) -> dict[str, dict[str, str | int]]:
    """Return the parsed ledger dict, or `{}` if the file does not exist.

    Raises `SpendLedgerCorrupt` when the file exists but is not valid JSON OR
    when its top-level JSON value is not an object. Without the type check, a
    hand-edited `[1, 2]` or `"foo"` would later crash with `AttributeError` on
    `ledger.get(...)`, defeating the "corruption is a hard error" guarantee.
    """
    path = ledger_path or LEDGER_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            parsed = json.load(fh)
    except json.JSONDecodeError as exc:
        raise SpendLedgerCorrupt(
            f"{path} is not valid JSON: {exc.msg}"
        ) from exc
    if not isinstance(parsed, dict):
        raise SpendLedgerCorrupt(
            f"{path} top-level value must be a JSON object, "
            f"got {type(parsed).__name__}"
        )
    return parsed


def current_month_total_usd(
    ledger: dict[str, dict[str, str | int]], month_key: str
) -> Decimal:
    """Return the recorded total for *month_key*, or `Decimal('0')` if absent."""
    entry = ledger.get(month_key, {})
    raw = entry.get("total_usd", "0")
    return Decimal(str(raw))


def check_cap_or_raise(
    cap_usd: Decimal,
    *,
    now: datetime | None = None,
    ledger_path: Path | None = None,
) -> Decimal:
    """Refuse to run if current monthly spend has reached the cap.

    Returns the current month's spend so the caller can include it in the
    success summary. Raises `SpendCapExceeded` if `current >= cap`.
    """
    ledger = read_ledger(ledger_path)
    month_key = current_month_key(now)
    current = current_month_total_usd(ledger, month_key)
    if current >= cap_usd:
        raise SpendCapExceeded(current_usd=current, cap_usd=cap_usd)
    return current


def record_call(
    cost_usd: Decimal,
    *,
    now: datetime | None = None,
    ledger_path: Path | None = None,
) -> None:
    """Append the cost of one successful call to the current month's totals.

    The write goes through a temp sibling + `os.replace()` so a crash mid-write
    cannot corrupt the ledger.
    """
    path = ledger_path or LEDGER_PATH
    ledger = read_ledger(path)
    month_key = current_month_key(now)
    entry = ledger.get(month_key, {})
    total = Decimal(str(entry.get("total_usd", "0"))) + Decimal(str(cost_usd))
    calls = int(entry.get("calls", 0)) + 1
    ledger[month_key] = {"total_usd": format(total, "f"), "calls": calls}

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_path, path)
