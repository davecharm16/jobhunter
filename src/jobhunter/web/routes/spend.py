"""Read-only spend/usage endpoint (Story 02-7).

`GET /api/spend` returns the current-month LLM spend, the configured monthly
cap, and the current month key — all read-only. The cap is env-only
(MONTHLY_SPEND_CAP_USD); it cannot be changed via this API.

Response shape:
    {
        "current_month_usd": "0.012345",
        "cap_usd": "25.00",
        "month": "2026-06"
    }
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException

from jobhunter import spend_tracker
from jobhunter.config import PROJECT_ROOT
from jobhunter.spend_tracker import current_month_key, current_month_total_usd, read_ledger

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:
    _load_dotenv = None


router = APIRouter()


def _load_cap_usd() -> Decimal:
    """Read MONTHLY_SPEND_CAP_USD from the environment (not via load_runtime_config).

    The full `load_runtime_config()` also requires LLM_API_KEY which is not
    needed here. We only need the cap, so we read it directly from env to keep
    the spend endpoint usable even when the LLM key is not in scope. We still
    load `.env` first (override=False) — same as `load_ingest_token` — so the
    cap is visible on a fresh app boot before any other config load runs.
    """
    if _load_dotenv is not None:
        _load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
    raw = os.environ.get("MONTHLY_SPEND_CAP_USD", "").strip()
    if not raw:
        raise HTTPException(
            status_code=503,
            detail="MONTHLY_SPEND_CAP_USD is not configured; set it in .env to enable spend tracking.",
        )
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MONTHLY_SPEND_CAP_USD is not a valid number: {raw!r}",
        ) from exc
    if not value.is_finite() or value <= 0:
        raise HTTPException(
            status_code=503,
            detail=f"MONTHLY_SPEND_CAP_USD must be a finite positive number, got {raw!r}",
        )
    return value


@router.get("/api/spend")
def get_spend() -> dict[str, str]:
    """Return current-month LLM spend vs the configured monthly cap."""
    cap_usd = _load_cap_usd()

    ledger = read_ledger(spend_tracker.LEDGER_PATH)
    month = current_month_key()
    current = current_month_total_usd(ledger, month)

    return {
        "current_month_usd": format(current, "f"),
        "cap_usd": format(cap_usd, "f"),
        "month": month,
    }
