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
    # Mirror the committed canonical CV into the isolated tree so the Story 1.3
    # reader contract resolves cleanly when env-valid tests reach `read_canonical_cv()`.
    canonical_src = PROJECT_ROOT / "canonical-cv.json"
    if canonical_src.is_file():
        shutil.copyfile(canonical_src, tmp_path / "canonical-cv.json")
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


# --- Story 1.3: reader-driven rejection paths --------------------------------


def _isolated_cli_env_with_canonical_cv(
    tmp_path: Path,
    cv_filename: str,
    cv_contents: bytes = b"",
    **overrides: str,
) -> tuple[dict[str, str], Path]:
    """Build an isolated src copy whose `config.py` points at a per-test CV file.

    Returns (env, cv_path). The CV file is created inside the isolated tmp tree
    with the given contents (zero bytes by default, which forces the extension
    check to be the only thing that can succeed/fail).
    """
    src_path = tmp_path / "src"
    shutil.copytree(
        PROJECT_ROOT / "src" / "jobhunter",
        src_path / "jobhunter",
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    cv_path = tmp_path / cv_filename
    cv_path.write_bytes(cv_contents)

    # Rewrite config.py to bind CANONICAL_CV_PATH to our chosen file. The
    # tmp_path tree is the "project root" relative to the isolated `src/`
    # because `PROJECT_ROOT = parents[2]` from src/jobhunter/config.py.
    config_py = src_path / "jobhunter" / "config.py"
    config_text = config_py.read_text(encoding="utf-8")
    rewritten = config_text.replace(
        'CANONICAL_CV_PATH: Path = PROJECT_ROOT / "canonical-cv.json"',
        f'CANONICAL_CV_PATH: Path = PROJECT_ROOT / "{cv_filename}"',
    )
    assert rewritten != config_text, "config.py rewrite failed — line not found"
    config_py.write_text(rewritten, encoding="utf-8")

    env = _cli_env(src_path, **overrides)
    return env, cv_path


def test_paste_subprocess_rejects_pdf_canonical_cv_before_story_1_4(tmp_path) -> None:
    env, _ = _isolated_cli_env_with_canonical_cv(
        tmp_path,
        cv_filename="canonical-cv.pdf",
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=env,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "PDF" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_rejects_docx_canonical_cv_before_story_1_4(tmp_path) -> None:
    env, _ = _isolated_cli_env_with_canonical_cv(
        tmp_path,
        cv_filename="canonical-cv.docx",
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=env,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "docx" in result.stderr
    assert "Word" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_rejects_missing_canonical_cv_before_story_1_4(tmp_path) -> None:
    env, cv_path = _isolated_cli_env_with_canonical_cv(
        tmp_path,
        cv_filename="missing-canonical-cv.json",
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )
    # Remove the placeholder so the path no longer exists.
    cv_path.unlink()

    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=env,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert str(cv_path) in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_cli_paste_rejects_pdf_canonical_cv_in_process(
    monkeypatch, capsys, tmp_path
) -> None:
    """In-process variant so coverage does not depend on subprocess support."""
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    pdf_path = tmp_path / "canonical-cv.pdf"
    pdf_path.write_bytes(b"")
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", pdf_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", pdf_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) != 0
    captured = capsys.readouterr()
    assert "PDF" in captured.err
    assert "Story 1.4" not in captured.err
    assert captured.out == ""


def test_cli_paste_rejects_docx_canonical_cv_in_process(
    monkeypatch, capsys, tmp_path
) -> None:
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    docx_path = tmp_path / "canonical-cv.docx"
    docx_path.write_bytes(b"")
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", docx_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", docx_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) != 0
    captured = capsys.readouterr()
    assert "docx" in captured.err
    assert "Word" in captured.err
    assert "Story 1.4" not in captured.err
    assert captured.out == ""


def test_cli_paste_rejects_missing_canonical_cv_in_process(
    monkeypatch, capsys, tmp_path
) -> None:
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    missing_path = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", missing_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", missing_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) != 0
    captured = capsys.readouterr()
    assert str(missing_path) in captured.err
    assert "Story 1.4" not in captured.err
    assert captured.out == ""


# --- Story 1.3: case-insensitive rejection at CLI integration boundary -------


def test_paste_subprocess_rejects_pdf_uppercase_canonical_cv(tmp_path) -> None:
    """Case-insensitivity must hold at the CLI boundary, not just in the reader."""
    env, _ = _isolated_cli_env_with_canonical_cv(
        tmp_path,
        cv_filename="canonical-cv.PDF",
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=env,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "PDF" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_rejects_doc_canonical_cv_before_story_1_4(tmp_path) -> None:
    """`.doc` (legacy Word) rejection at CLI boundary — closes the .doc subprocess gap."""
    env, _ = _isolated_cli_env_with_canonical_cv(
        tmp_path,
        cv_filename="canonical-cv.doc",
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="this input must not be consumed\n",
        env=env,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "docx" in result.stderr
    assert "Word" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert not output_dir.exists()


def test_cli_paste_rejects_pdf_exits_with_code_two(
    monkeypatch, capsys, tmp_path
) -> None:
    """Task 3 contract: rejection paths exit with code 2 (matches config-error convention)."""
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    pdf_path = tmp_path / "canonical-cv.pdf"
    pdf_path.write_bytes(b"")
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", pdf_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", pdf_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) == 2


def test_cli_paste_rejects_docx_exits_with_code_two(
    monkeypatch, capsys, tmp_path
) -> None:
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    docx_path = tmp_path / "canonical-cv.docx"
    docx_path.write_bytes(b"")
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", docx_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", docx_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) == 2


def test_cli_paste_rejects_missing_canonical_cv_exits_with_code_two(
    monkeypatch, capsys, tmp_path
) -> None:
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    missing_path = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", missing_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", missing_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) == 2


def test_cli_paste_does_not_create_out_directory_on_rejection(
    monkeypatch, capsys, tmp_path
) -> None:
    """AC7 in-process guard: rejection path must NOT create `./out/`."""
    from jobhunter.cli import main
    import jobhunter.canonical_cv as reader_module
    import jobhunter.config as config_module

    pdf_path = tmp_path / "canonical-cv.pdf"
    pdf_path.write_bytes(b"")
    monkeypatch.setattr(config_module, "CANONICAL_CV_PATH", pdf_path)
    monkeypatch.setattr(reader_module, "CANONICAL_CV_PATH", pdf_path)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) == 2
    assert not (tmp_path / "out").exists()
