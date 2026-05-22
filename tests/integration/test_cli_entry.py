"""Integration tests for the `jobhunter` CLI entry stub (AC #2).

Story 1.1 wires the entry point via `[project.scripts]` but leaves the
implementation as a stub that prints a usage hint and exits 2. Story 1.2 will
replace this with real subcommand parsing — but for now the contract is:

  - `jobhunter` (no args)  → exit code 2, stderr contains "usage" and "jobhunter"
  - `python -m jobhunter.cli` → same contract (in-package invocation)
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def test_jobhunter_console_script_exits_two_with_usage() -> None:
    jobhunter_bin = shutil.which("jobhunter")
    if jobhunter_bin is None:
        # Fall back to the venv-relative entry — running in CI without PATH set.
        import sys as _sys
        from pathlib import Path

        candidate = Path(_sys.executable).parent / "jobhunter"
        if candidate.exists():
            jobhunter_bin = str(candidate)

    assert jobhunter_bin is not None, (
        "jobhunter console script not on PATH — did `pip install -e .` run?"
    )

    result = subprocess.run(
        [jobhunter_bin],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2, (
        f"expected exit 2 stub, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "jobhunter" in result.stderr.lower()
    assert "usage" in result.stderr.lower()


def test_python_dash_m_module_entry_exits_two() -> None:
    """Running the module directly should also follow the stub contract."""
    result = subprocess.run(
        [sys.executable, "-m", "jobhunter.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()


def test_cli_main_returns_int_two() -> None:
    """Pure unit-level check of the stub function — no subprocess overhead."""
    from jobhunter.cli import main

    assert main() == 2
