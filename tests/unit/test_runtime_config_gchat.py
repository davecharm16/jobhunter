"""Story 6.1 AC1: GCHAT_WEBHOOK_URL is loaded as an optional runtime field.

Mirrors the `INGEST_TOKEN` loader semantics from Story 1.6: empty / unset
value resolves to `None` (notifications disabled), no
`ConfigurationError` raised. The webhook URL is never required for the
pipeline to run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jobhunter.config import PROJECT_ROOT
from jobhunter.runtime_config import RuntimeConfig, load_runtime_config


def test_runtime_config_defaults_gchat_webhook_url_to_none(
    monkeypatch, tmp_path: Path
) -> None:
    """AC1: with no env value set, `gchat_webhook_url` is None."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)

    config = load_runtime_config(tmp_path / ".env")

    assert config.gchat_webhook_url is None


def test_runtime_config_reads_gchat_webhook_url_from_env(
    monkeypatch, tmp_path: Path
) -> None:
    """AC1: GCHAT_WEBHOOK_URL from env is surfaced on the runtime config."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv(
        "GCHAT_WEBHOOK_URL", "https://chat.googleapis.com/v1/spaces/test/messages"
    )

    config = load_runtime_config(tmp_path / ".env")

    assert (
        config.gchat_webhook_url
        == "https://chat.googleapis.com/v1/spaces/test/messages"
    )


def test_runtime_config_reads_gchat_webhook_url_from_dotenv(
    monkeypatch, tmp_path: Path
) -> None:
    """AC1: GCHAT_WEBHOOK_URL is also readable from a `.env` file."""
    pytest.importorskip("dotenv")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)
    monkeypatch.delenv("GCHAT_WEBHOOK_URL", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=k\n"
        "MONTHLY_SPEND_CAP_USD=25.00\n"
        "GCHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/abc/messages\n",
        encoding="utf-8",
    )

    config = load_runtime_config(env_path)

    assert (
        config.gchat_webhook_url
        == "https://chat.googleapis.com/v1/spaces/abc/messages"
    )


def test_runtime_config_empty_gchat_webhook_url_resolves_to_none(
    monkeypatch, tmp_path: Path
) -> None:
    """AC1: explicit empty string disables notifications without erroring."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setenv("GCHAT_WEBHOOK_URL", "   ")

    config = load_runtime_config(tmp_path / ".env")

    assert config.gchat_webhook_url is None


def test_runtime_config_is_frozen_dataclass() -> None:
    """Story-6.1 invariant: RuntimeConfig stays an immutable dataclass."""
    config = RuntimeConfig(
        llm_api_key="k",
        monthly_spend_cap_usd=__import__("decimal").Decimal("25.00"),
    )
    with pytest.raises(Exception):  # FrozenInstanceError subclass of AttributeError
        config.gchat_webhook_url = "https://example.com"  # type: ignore[misc]


def test_env_example_contains_gchat_webhook_placeholder() -> None:
    """AC1: `.env.example` documents the optional GCHAT_WEBHOOK_URL line."""
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "GCHAT_WEBHOOK_URL=" in env_example
    assert "chat.googleapis.com" in env_example


def test_gitignore_pins_dotenv_so_real_url_is_never_committed() -> None:
    """AC1: `.env` (where the real URL lives) is git-ignored.

    Smoke check on `.gitignore` contents — the integration-suite-wide
    `test_gitignore_excludes_dotenv_files_but_allows_example` already pins
    this contract, but Story 6.1 AC1 explicitly calls out `git check-ignore
    .env` so we keep a Story-6.1-owned assertion against the same file.
    """
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "!.env.example" in gitignore


def test_git_check_ignore_dotenv_returns_zero() -> None:
    """AC1: `git check-ignore .env` exits 0, confirming `.env` is ignored.

    Skipped gracefully when `git` is not available on PATH or the project
    is not inside a git checkout (defensive — local sandboxes vary).
    """
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", ".env"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        pytest.skip("git not available on PATH")
    # `git check-ignore -q` exits 0 when the path is ignored, 1 when not.
    # Exit code 128 means "not a git repo" — skip in that case.
    if completed.returncode == 128:
        pytest.skip("PROJECT_ROOT is not inside a git checkout")
    assert completed.returncode == 0, (
        f".env is not git-ignored (exit={completed.returncode}, "
        f"stderr={completed.stderr!r})"
    )
