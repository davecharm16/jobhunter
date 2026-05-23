"""Unit tests for runtime secret and spend-cap loading."""

from __future__ import annotations

from decimal import Decimal

import pytest

from jobhunter.runtime_config import ConfigurationError, load_runtime_config


def test_load_runtime_config_reads_dotenv_values(monkeypatch, tmp_path) -> None:
    pytest.importorskip("dotenv")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=dotenv-key\nMONTHLY_SPEND_CAP_USD=25.00\n",
        encoding="utf-8",
    )

    config = load_runtime_config(env_path)

    assert config.llm_api_key == "dotenv-key"
    assert config.monthly_spend_cap_usd == Decimal("25.00")


def test_load_runtime_config_exported_values_override_dotenv(monkeypatch, tmp_path) -> None:
    pytest.importorskip("dotenv")
    monkeypatch.setenv("LLM_API_KEY", "exported-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "42.50")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=dotenv-key\nMONTHLY_SPEND_CAP_USD=25.00\n",
        encoding="utf-8",
    )

    config = load_runtime_config(env_path)

    assert config.llm_api_key == "exported-key"
    assert config.monthly_spend_cap_usd == Decimal("42.50")


def test_load_runtime_config_reads_exported_values_without_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LLM_API_KEY", "exported-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "42.50")

    config = load_runtime_config(tmp_path / ".env")

    assert config.llm_api_key == "exported-key"
    assert config.monthly_spend_cap_usd == Decimal("42.50")


def test_load_runtime_config_requires_python_dotenv_for_dotenv_files(
    monkeypatch,
    tmp_path,
) -> None:
    import jobhunter.runtime_config as runtime_config

    monkeypatch.setattr(runtime_config, "_load_dotenv", None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=dotenv-key\nMONTHLY_SPEND_CAP_USD=25.00\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="python-dotenv"):
        load_runtime_config(env_path)


def test_load_runtime_config_missing_llm_api_key_names_variable(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        load_runtime_config(tmp_path / ".env")


def test_load_runtime_config_empty_llm_api_key_names_variable(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LLM_API_KEY", "   ")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        load_runtime_config(tmp_path / ".env")


@pytest.mark.parametrize(
    ("value", "expected_message"),
    [
        (None, "MONTHLY_SPEND_CAP_USD"),
        ("", "MONTHLY_SPEND_CAP_USD"),
        ("not-a-number", "MONTHLY_SPEND_CAP_USD"),
        ("NaN", "MONTHLY_SPEND_CAP_USD"),
        ("Infinity", "MONTHLY_SPEND_CAP_USD"),
        ("0", "MONTHLY_SPEND_CAP_USD"),
        ("-1", "MONTHLY_SPEND_CAP_USD"),
    ],
)
def test_load_runtime_config_rejects_invalid_monthly_cap(
    monkeypatch,
    tmp_path,
    value: str | None,
    expected_message: str,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    if value is None:
        monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)
    else:
        monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", value)

    with pytest.raises(ConfigurationError, match=expected_message):
        load_runtime_config(tmp_path / ".env")


# --- Story 1.5 AC7: LLM_CALL_TIMEOUT_SECONDS env loading + validation -------


def test_load_runtime_config_defaults_timeout_when_env_unset(
    monkeypatch, tmp_path
) -> None:
    """AC7: with the env var unset, `llm_call_timeout_seconds` is 60.0."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("LLM_CALL_TIMEOUT_SECONDS", raising=False)

    config = load_runtime_config(tmp_path / ".env")

    assert config.llm_call_timeout_seconds == 60.0


def test_load_runtime_config_reads_positive_timeout_override(
    monkeypatch, tmp_path
) -> None:
    """AC7: a positive numeric LLM_CALL_TIMEOUT_SECONDS overrides the default."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", "30")

    config = load_runtime_config(tmp_path / ".env")

    assert config.llm_call_timeout_seconds == 30.0


def test_load_runtime_config_reads_fractional_timeout(
    monkeypatch, tmp_path
) -> None:
    """AC7: float values like `0.5` are accepted (Decimal-style strings)."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", "0.5")

    config = load_runtime_config(tmp_path / ".env")

    assert config.llm_call_timeout_seconds == 0.5


@pytest.mark.parametrize(
    "value",
    ["abc", "not-a-number", "1.2.3", "12s"],
)
def test_load_runtime_config_rejects_non_numeric_timeout(
    monkeypatch, tmp_path, value: str
) -> None:
    """AC7: non-numeric LLM_CALL_TIMEOUT_SECONDS raises ConfigurationError."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", value)

    with pytest.raises(ConfigurationError, match="LLM_CALL_TIMEOUT_SECONDS"):
        load_runtime_config(tmp_path / ".env")


@pytest.mark.parametrize(
    "value",
    ["0", "-1", "-0.5"],
)
def test_load_runtime_config_rejects_non_positive_timeout(
    monkeypatch, tmp_path, value: str
) -> None:
    """AC7: zero or negative LLM_CALL_TIMEOUT_SECONDS raises ConfigurationError."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", value)

    with pytest.raises(ConfigurationError, match="LLM_CALL_TIMEOUT_SECONDS"):
        load_runtime_config(tmp_path / ".env")


@pytest.mark.parametrize(
    "value",
    ["inf", "-inf", "Infinity", "nan", "NaN"],
)
def test_load_runtime_config_rejects_non_finite_timeout(
    monkeypatch, tmp_path, value: str
) -> None:
    """AC7 (review): LLM_CALL_TIMEOUT_SECONDS must reject non-finite floats.

    Without an explicit `math.isfinite` guard, `float("inf")` would pass the
    `value > 0` check and silently disable the per-call timeout — defeating
    the NFR-Performance budget. Mirrors `_required_decimal`'s `is_finite()`.
    """
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("LLM_CALL_TIMEOUT_SECONDS", value)

    with pytest.raises(ConfigurationError, match="LLM_CALL_TIMEOUT_SECONDS"):
        load_runtime_config(tmp_path / ".env")
