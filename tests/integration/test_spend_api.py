"""GET /api/spend integration tests (Story 02-7).

The spend endpoint surfaces current-month LLM spend vs the configured
monthly cap in a read-only response. The cap comes from MONTHLY_SPEND_CAP_USD
(env-only; never mutable via the API). Spend data is read from the on-disk
ledger via spend_tracker.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jobhunter.spend_tracker import current_month_key
from jobhunter.web.api import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stage_ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point LEDGER_PATH at a tmp file and return its path."""
    import jobhunter.spend_tracker as tracker_module

    ledger_path = tmp_path / ".cost-ledger.json"
    monkeypatch.setattr(tracker_module, "LEDGER_PATH", ledger_path)
    return ledger_path


def _write_ledger(ledger_path: Path, month_key: str, total: str, calls: int) -> None:
    ledger_path.write_text(
        json.dumps({month_key: {"total_usd": total, "calls": calls}}),
        encoding="utf-8",
    )


def _set_cap(monkeypatch: pytest.MonkeyPatch, cap: str) -> None:
    """Set MONTHLY_SPEND_CAP_USD via env so the route picks it up."""
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", cap)


# ---------------------------------------------------------------------------
# GET /api/spend
# ---------------------------------------------------------------------------


def test_get_spend_returns_required_keys(tmp_path, monkeypatch) -> None:
    ledger_path = _stage_ledger(tmp_path, monkeypatch)
    month = current_month_key()
    _write_ledger(ledger_path, month, "0.012345", 3)
    _set_cap(monkeypatch, "25.00")

    client = TestClient(create_app())
    response = client.get("/api/spend")

    assert response.status_code == 200
    body = response.json()
    assert "current_month_usd" in body
    assert "cap_usd" in body
    assert "month" in body


def test_get_spend_returns_current_month_spend(tmp_path, monkeypatch) -> None:
    ledger_path = _stage_ledger(tmp_path, monkeypatch)
    month = current_month_key()
    _write_ledger(ledger_path, month, "0.012345", 3)
    _set_cap(monkeypatch, "25.00")

    client = TestClient(create_app())
    body = client.get("/api/spend").json()

    assert body["current_month_usd"] == "0.012345"
    assert body["month"] == month


def test_get_spend_returns_cap_from_env(tmp_path, monkeypatch) -> None:
    ledger_path = _stage_ledger(tmp_path, monkeypatch)
    month = current_month_key()
    _write_ledger(ledger_path, month, "0.000000", 0)
    _set_cap(monkeypatch, "10.50")

    client = TestClient(create_app())
    body = client.get("/api/spend").json()

    assert body["cap_usd"] == "10.50"


def test_get_spend_zero_when_ledger_missing(tmp_path, monkeypatch) -> None:
    _stage_ledger(tmp_path, monkeypatch)  # ledger file not written → does not exist
    _set_cap(monkeypatch, "25.00")

    client = TestClient(create_app())
    response = client.get("/api/spend")

    assert response.status_code == 200
    body = response.json()
    assert body["current_month_usd"] == "0"


def test_get_spend_zero_when_month_not_in_ledger(tmp_path, monkeypatch) -> None:
    ledger_path = _stage_ledger(tmp_path, monkeypatch)
    _write_ledger(ledger_path, "2020-01", "9.999999", 99)  # wrong month
    _set_cap(monkeypatch, "25.00")

    client = TestClient(create_app())
    body = client.get("/api/spend").json()

    assert body["current_month_usd"] == "0"


def test_get_spend_no_cap_configured_returns_503(tmp_path, monkeypatch) -> None:
    """When MONTHLY_SPEND_CAP_USD is not set the endpoint must fail gracefully."""
    _stage_ledger(tmp_path, monkeypatch)
    # Ensure the env var is absent (it may be set in the shell).
    monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)

    client = TestClient(create_app())
    response = client.get("/api/spend")

    # Acceptable: 503 service unavailable or 500 — cap is env-only.
    assert response.status_code in (500, 503)
