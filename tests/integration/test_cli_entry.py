"""Integration tests for the `jobhunter` CLI entrypoint."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from jobhunter.config import PROJECT_ROOT


def _pythonpath_with_src(
    env: dict[str, str],
    src_path: Path | None = None,
) -> dict[str, str]:
    src_path_text = str(PROJECT_ROOT / "src" if src_path is None else src_path)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        src_path_text
        if not existing_pythonpath
        else os.pathsep.join([src_path_text, existing_pythonpath])
    )
    return env


def _cli_env(src_path: Path | None = None, **overrides: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"LLM_API_KEY", "MONTHLY_SPEND_CAP_USD"}
    }
    env.update(overrides)
    return _pythonpath_with_src(env, src_path)


def _isolated_cli_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    src_path = tmp_path / "src"
    shutil.copytree(
        PROJECT_ROOT / "src" / "jobhunter",
        src_path / "jobhunter",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    return _cli_env(src_path, **overrides)


def _run_module_cli(
    *args: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jobhunter.cli", *args],
        capture_output=True,
        text=True,
        env=_cli_env() if env is None else env,
        cwd=PROJECT_ROOT if cwd is None else cwd,
        input=input_text,
        timeout=5,
    )


def test_jobhunter_console_script_exits_two_with_usage_listing_paste() -> None:
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
        f"expected exit 2 usage error, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert result.stdout == ""
    assert "jobhunter" in result.stderr.lower()
    assert "usage" in result.stderr.lower()
    assert "paste" in result.stderr.lower()


def test_jobhunter_help_documents_no_auto_submit_boundary() -> None:
    jobhunter_bin = shutil.which("jobhunter")
    if jobhunter_bin is None:
        from pathlib import Path

        candidate = Path(sys.executable).parent / "jobhunter"
        if candidate.exists():
            jobhunter_bin = str(candidate)

    assert jobhunter_bin is not None, (
        "jobhunter console script not on PATH - did `pip install -e .` run?"
    )

    result = subprocess.run(
        [jobhunter_bin, "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    help_text = result.stdout.lower()
    assert "paste" in help_text
    assert "only writes local files" in help_text
    assert "never submits" in help_text
    assert "upwork" in help_text
    assert "linkedin" in help_text
    assert "onlinejobs.ph" in help_text
    assert "job board" in help_text


def test_python_dash_m_module_entry_exits_two() -> None:
    """Running the module directly should also follow the CLI usage contract."""
    result = _run_module_cli()
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
    assert "paste" in result.stderr.lower()


def test_paste_subprocess_missing_llm_key_fails_before_reading_stdin(
    tmp_path,
) -> None:
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=_isolated_cli_env(tmp_path, MONTHLY_SPEND_CAP_USD="25.00"),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "LLM_API_KEY" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_missing_monthly_cap_fails_before_pipeline_work(
    tmp_path,
) -> None:
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=_isolated_cli_env(tmp_path, LLM_API_KEY="test-key"),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "MONTHLY_SPEND_CAP_USD" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_invalid_monthly_cap_fails_before_pipeline_work(
    tmp_path,
) -> None:
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="0",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "MONTHLY_SPEND_CAP_USD" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_valid_env_stops_at_story_1_4_boundary(tmp_path) -> None:
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Story 1.4" in result.stderr
    assert not output_dir.exists()


def test_cli_main_no_args_returns_int_two(capsys) -> None:
    """Pure unit-level check of no-argument usage behavior."""
    from jobhunter.cli import main

    assert main([]) == 2
    captured = capsys.readouterr()
    assert "usage" in captured.err.lower()
    assert "paste" in captured.err.lower()


def test_cli_paste_fails_before_pipeline_work_when_env_missing(monkeypatch, capsys) -> None:
    from jobhunter.cli import main

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MONTHLY_SPEND_CAP_USD", raising=False)

    assert main(["paste"]) != 0
    captured = capsys.readouterr()
    assert "LLM_API_KEY" in captured.err
    assert captured.out == ""


def test_cli_paste_reaches_story_1_4_boundary_with_valid_env(monkeypatch, capsys) -> None:
    from jobhunter.cli import main

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) != 0
    captured = capsys.readouterr()
    assert "Story 1.4" in captured.err
    assert captured.out == ""
