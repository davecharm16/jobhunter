"""Runtime secret and spend-cap loading for LLM-capable commands."""

from __future__ import annotations

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


@dataclass(frozen=True)
class RuntimeConfig:
    llm_api_key: str
    monthly_spend_cap_usd: Decimal


def load_runtime_config(env_path: Path | None = None) -> RuntimeConfig:
    dotenv_path = PROJECT_ROOT / ".env" if env_path is None else env_path
    if _load_dotenv is None:
        if dotenv_path.is_file():
            raise ConfigurationError("python-dotenv is required to load .env files")
    else:
        _load_dotenv(dotenv_path=dotenv_path, override=False)

    llm_api_key = _required_env("LLM_API_KEY")
    monthly_spend_cap_usd = _required_decimal("MONTHLY_SPEND_CAP_USD")

    return RuntimeConfig(
        llm_api_key=llm_api_key,
        monthly_spend_cap_usd=monthly_spend_cap_usd,
    )


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
