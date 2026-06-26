"""Runtime secret and spend-cap loading for LLM-capable commands."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from jobhunter.config import PROJECT_ROOT

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:
    _load_dotenv = None


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


DEFAULT_LLM_CALL_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class RuntimeConfig:
    llm_api_key: str
    monthly_spend_cap_usd: Decimal
    llm_call_timeout_seconds: float = DEFAULT_LLM_CALL_TIMEOUT_SECONDS
    ingest_token: str | None = None
    # Story 6.1: optional Google Chat webhook URL for pass-only notifications.
    # Missing / empty value disables notifications without raising.
    gchat_webhook_url: str | None = None
    # Job Scan: optional n8n trigger webhook the "Run scan now" button pings to
    # kick off an external scan. Missing / empty disables manual triggering.
    n8n_scan_trigger_url: str | None = None


def load_runtime_config(env_path: Path | None = None) -> RuntimeConfig:
    dotenv_path = PROJECT_ROOT / ".env" if env_path is None else env_path
    if _load_dotenv is None:
        if dotenv_path.is_file():
            raise ConfigurationError("python-dotenv is required to load .env files")
    else:
        _load_dotenv(dotenv_path=dotenv_path, override=False)

    llm_api_key = _required_env("LLM_API_KEY")
    monthly_spend_cap_usd = _required_decimal("MONTHLY_SPEND_CAP_USD")
    llm_call_timeout_seconds = _optional_positive_float(
        "LLM_CALL_TIMEOUT_SECONDS",
        default=DEFAULT_LLM_CALL_TIMEOUT_SECONDS,
    )
    ingest_token = _optional_token("INGEST_TOKEN")
    gchat_webhook_url = _optional_token("GCHAT_WEBHOOK_URL")
    n8n_scan_trigger_url = _optional_token("N8N_SCAN_TRIGGER_URL")

    return RuntimeConfig(
        llm_api_key=llm_api_key,
        monthly_spend_cap_usd=monthly_spend_cap_usd,
        llm_call_timeout_seconds=llm_call_timeout_seconds,
        ingest_token=ingest_token,
        gchat_webhook_url=gchat_webhook_url,
        n8n_scan_trigger_url=n8n_scan_trigger_url,
    )


def load_ingest_token(env_path: Path | None = None) -> str | None:
    """Read INGEST_TOKEN from env/.env without requiring LLM env vars.

    The paste-auth dependency runs before any pipeline work, so it must not
    require LLM_API_KEY / MONTHLY_SPEND_CAP_USD to be set.
    """
    dotenv_path = PROJECT_ROOT / ".env" if env_path is None else env_path
    if _load_dotenv is not None:
        _load_dotenv(dotenv_path=dotenv_path, override=False)
    return _optional_token("INGEST_TOKEN")


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"{name} is required and must be non-empty")
    return value.strip()


def _required_decimal(name: str) -> Decimal:
    raw_value = _required_env(name)
    try:
        value = Decimal(raw_value)
    except InvalidOperation as exc:
        raise ConfigurationError(f"{name} must be a finite positive number") from exc

    if not value.is_finite() or value <= 0:
        raise ConfigurationError(f"{name} must be a finite positive number")

    return value


def _optional_token(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _optional_positive_float(name: str, *, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a finite positive number") from exc
    # Reject NaN, +/-inf, zero, and negatives in one finite-positive guard so
    # the float branch matches `_required_decimal`'s `is_finite()` behavior.
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be a finite positive number")
    return value
