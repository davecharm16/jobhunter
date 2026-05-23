"""Integration tests for the `jobhunter` launcher (web-only architecture)."""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest


def _jobhunter_bin() -> str:
    candidate = shutil.which("jobhunter")
    if candidate is None:
        fallback = f"{sys.prefix}/bin/jobhunter"
        if shutil.which(fallback) or shutil.os.path.exists(fallback):
            candidate = fallback
    assert candidate is not None, (
        "jobhunter console script not on PATH — did `pip install -e .[web,dev]` run?"
    )
    return candidate


def test_jobhunter_help_documents_only_launcher_flags() -> None:
    result = subprocess.run(
        [_jobhunter_bin(), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "--port" in help_text
    assert "--no-browser" in help_text


@pytest.mark.parametrize("subcommand", ["paste", "status", "override", "stats"])
def test_jobhunter_does_not_accept_legacy_subcommands(subcommand: str) -> None:
    """DECISIONS.md §6: the launcher has no subcommand surface."""
    result = subprocess.run(
        [_jobhunter_bin(), subcommand],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0, (
        f"`jobhunter {subcommand}` should not be a parseable subcommand "
        f"(got rc={result.returncode}, stdout={result.stdout!r})"
    )


def test_jobhunter_help_does_not_advertise_legacy_subcommands() -> None:
    """Subcommand names must not appear as parseable commands in --help."""
    result = subprocess.run(
        [_jobhunter_bin(), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    text = result.stdout

    assert "subcommands" not in text.lower()
    assert "{paste" not in text
    assert "positional arguments" not in text.lower()


def test_python_dash_m_module_entry_help_works() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "jobhunter.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "--port" in result.stdout
    assert "--no-browser" in result.stdout


def test_ensure_loopback_rejects_non_loopback_host() -> None:
    from jobhunter.cli import NonLoopbackBindError, ensure_loopback

    with pytest.raises(NonLoopbackBindError):
        ensure_loopback("0.0.0.0")

    with pytest.raises(NonLoopbackBindError):
        ensure_loopback("192.168.1.10")


def test_ensure_loopback_accepts_loopback_hosts() -> None:
    from jobhunter.cli import ensure_loopback

    for host in ("127.0.0.1", "localhost", "::1"):
        ensure_loopback(host)


def test_resolve_port_prefers_cli_over_env(monkeypatch) -> None:
    from jobhunter.cli import DEFAULT_PORT, resolve_port

    monkeypatch.setenv("JOBHUNTER_WEB_PORT", "9001")
    assert resolve_port(7777) == 7777
    monkeypatch.delenv("JOBHUNTER_WEB_PORT", raising=False)
    assert resolve_port(None) == DEFAULT_PORT
    monkeypatch.setenv("JOBHUNTER_WEB_PORT", "9001")
    assert resolve_port(None) == 9001
