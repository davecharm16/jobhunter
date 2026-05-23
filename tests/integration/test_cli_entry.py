"""Integration tests for the `jobhunter` CLI entrypoint."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from jobhunter.config import PROJECT_ROOT
from tests.integration._cli_helpers import (
    FAKE_COVER_LETTER_MARKDOWN,
    FAKE_CV_MARKDOWN,
    _cli_env,
    _isolated_cli_env,
    _isolated_cli_env_with_fake_llm,
    _pythonpath_with_src,
    _run_module_cli,
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
    assert "onlinejobs" in help_text
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


def test_paste_subprocess_valid_env_stdin_writes_tailored_package(
    tmp_path,
) -> None:
    """Story 1.5 AC1 happy path (subprocess, stdin): writes ./out/<slug>/ files."""
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role at Acme. Must have FastAPI.\n",
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0, (
        f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"
    )
    assert result.stdout == ""
    assert "Tailored package written to" in result.stderr
    assert "/out/" in result.stderr
    assert "$0." in result.stderr
    assert "Story 1.4" not in result.stderr

    # Both artifact files exist with the stub's content.
    assert output_dir.is_dir()
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    assert (slug_dir / "cv.md").read_text(encoding="utf-8") == FAKE_CV_MARKDOWN
    assert (
        (slug_dir / "cover-letter.md").read_text(encoding="utf-8")
        == FAKE_COVER_LETTER_MARKDOWN
    )


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


def test_cli_paste_writes_tailored_package_in_process_with_stdin(
    monkeypatch, capsys, tmp_canonical_cv, tmp_path
) -> None:
    """Story 1.5 AC1 happy path (in-process, stdin) via the llm_tailor= seam."""
    import io
    from decimal import Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.cli import main
    from jobhunter.llm_client import TailoringResult

    fake_result = TailoringResult(
        cv_markdown="# In-process tailored CV\n",
        cover_letter_markdown="Dear team,\n\nIn-process cover letter.\n",
        cost_usd=Decimal("0.0042"),
        input_tokens=100,
        output_tokens=50,
    )

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return fake_result

    out_root = tmp_path / "out"
    ledger_path = tmp_path / ".cost-ledger.json"

    original_run = tailoring_module.run_tailoring

    def patched_run(canonical_cv, jd_text, *, config, now=None, llm_tailor=None,
                    out_root=None, ledger_path=None):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now,
            llm_tailor=fake_tailor,
            out_root=out_root or (tmp_path / "out"),
            ledger_path=ledger_path or (tmp_path / ".cost-ledger.json"),
        )

    monkeypatch.setattr(cli_module, "run_tailoring", patched_run)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setattr(sys, "stdin", io.StringIO("JD text from a fixture"))

    assert main(["paste"]) == 0
    captured = capsys.readouterr()
    assert "Tailored package written to" in captured.err
    assert "/out/" in captured.err
    assert "stdin" in captured.err
    assert "Story 1.4" not in captured.err
    assert captured.out == ""
    assert out_root.is_dir()
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    assert (slug_dirs[0] / "cv.md").read_text(encoding="utf-8") == fake_result.cv_markdown
    assert (
        (slug_dirs[0] / "cover-letter.md").read_text(encoding="utf-8")
        == fake_result.cover_letter_markdown
    )
    assert ledger_path.exists()


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


# --- Story 1.4: JD ingest paths ---------------------------------------------


def test_paste_subprocess_with_file_writes_tailored_package(
    tmp_path,
) -> None:
    """Story 1.5 AC1 happy path (subprocess, --file branch)."""
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(
        "Senior Python role at Acme. Must have FastAPI.\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        # No stdin piped — exercising the --file path alone.
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert result.stdout == ""
    assert "Tailored package written to" in result.stderr
    assert "--file" in result.stderr
    assert "Story 1.4" not in result.stderr
    assert output_dir.is_dir()
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1


def test_paste_subprocess_file_precedence_over_stdin(tmp_path) -> None:
    """AC3: `--file` wins over piped stdin (Story 1.5 happy path version)."""
    jd_path = tmp_path / "from-file.txt"
    jd_path.write_text("FROM FILE: senior python role.\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        input_text="FROM STDIN: should be ignored.\n",
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert "Tailored package written to" in result.stderr
    assert "--file" in result.stderr
    # The success message names the file as the source, not stdin.
    assert "from stdin" not in result.stderr
    assert output_dir.is_dir()


def test_paste_subprocess_missing_file_exits_two_with_path_in_stderr(
    tmp_path,
) -> None:
    missing = tmp_path / "does-not-exist.txt"
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(missing),
        cwd=tmp_path,
        input_text="must not be consumed\n",
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert str(missing) in result.stderr
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_empty_stdin_exits_two(tmp_path) -> None:
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="",
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "empty" in result.stderr.lower()
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_whitespace_only_stdin_exits_two(tmp_path) -> None:
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="   \n\t  \n",
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "empty" in result.stderr.lower()
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_file_pointing_at_directory_exits_two(
    tmp_path,
) -> None:
    # Make a subdirectory so `--file <dir>` is unambiguously a directory path.
    target_dir = tmp_path / "not-a-file"
    target_dir.mkdir()

    result = _run_module_cli(
        "paste",
        "--file",
        str(target_dir),
        cwd=tmp_path,
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert str(target_dir) in result.stderr
    assert "Story 1.5" not in result.stderr


def _install_in_process_fake_llm(monkeypatch, tmp_path):
    """Wire `cli.run_tailoring` to a fake-LLM-backed run inside tmp_path."""
    from decimal import Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.llm_client import TailoringResult

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# in-process tailored\n",
            cover_letter_markdown="cover\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    original_run = tailoring_module.run_tailoring

    def patched_run(canonical_cv, jd_text, *, config, now=None, llm_tailor=None,
                    out_root=None, ledger_path=None):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now,
            llm_tailor=fake_tailor,
            out_root=out_root or (tmp_path / "out"),
            ledger_path=ledger_path or (tmp_path / ".cost-ledger.json"),
        )

    monkeypatch.setattr(cli_module, "run_tailoring", patched_run)


def test_cli_paste_with_file_in_process_writes_tailored_package(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """Story 1.5 AC1 happy path (in-process, --file branch)."""
    from jobhunter.cli import main

    _install_in_process_fake_llm(monkeypatch, tmp_path)

    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("In-process JD content", encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(jd_path)]) == 0
    captured = capsys.readouterr()
    assert "Tailored package written to" in captured.err
    assert "--file" in captured.err
    assert captured.out == ""
    assert (tmp_path / "out").is_dir()


def test_cli_paste_with_stdin_in_process_writes_tailored_package(
    monkeypatch, capsys, tmp_canonical_cv, tmp_path
) -> None:
    """Story 1.5 AC1 happy path (in-process, stdin branch)."""
    import io

    from jobhunter.cli import main

    _install_in_process_fake_llm(monkeypatch, tmp_path)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setattr(sys, "stdin", io.StringIO("JD content via stdin"))

    assert main(["paste"]) == 0
    captured = capsys.readouterr()
    assert "Tailored package written to" in captured.err
    assert "stdin" in captured.err
    assert captured.out == ""
    assert (tmp_path / "out").is_dir()


def test_cli_paste_no_input_tty_exits_two_without_blocking(
    monkeypatch, capsys, tmp_canonical_cv
) -> None:
    """AC4: TTY stdin with no --file must NOT call stdin.read()."""
    from types import SimpleNamespace

    import pytest

    from jobhunter.cli import main

    def _must_not_read() -> str:
        pytest.fail("stdin.read() must not be called in TTY mode")

    stub_stdin = SimpleNamespace(isatty=lambda: True, read=_must_not_read)
    monkeypatch.setattr(sys, "stdin", stub_stdin)

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste"]) == 2
    captured = capsys.readouterr()
    assert "Provide a JD" in captured.err or "stdin" in captured.err
    assert "Story 1.5" not in captured.err
    assert captured.out == ""


def test_cli_paste_missing_file_in_process_exits_two(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    from jobhunter.cli import main

    missing = tmp_path / "nope.txt"

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(missing)]) == 2
    captured = capsys.readouterr()
    assert str(missing) in captured.err
    assert "Story 1.5" not in captured.err
    assert captured.out == ""


def test_cli_paste_writes_only_artifact_files_into_slug_dir(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """Story 1.5 inversion of the Story 1.4 'no disk write' guard:

    Story 1.5 persists the tailored CV + cover letter under ./out/<slug>/, and
    nothing else — no JD copy, no transient artifact. This test asserts the
    slug dir contains exactly those two files.
    """
    from decimal import Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.cli import main
    from jobhunter.llm_client import TailoringResult

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        return TailoringResult(
            cv_markdown="# tailored\n",
            cover_letter_markdown="cover\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

    original_run = tailoring_module.run_tailoring

    def patched_run(canonical_cv, jd_text, *, config, now=None, llm_tailor=None,
                    out_root=None, ledger_path=None):
        return original_run(
            canonical_cv,
            jd_text,
            config=config,
            now=now,
            llm_tailor=fake_tailor,
            out_root=out_root or (tmp_path / "out"),
            ledger_path=ledger_path or (tmp_path / ".cost-ledger.json"),
        )

    monkeypatch.setattr(cli_module, "run_tailoring", patched_run)

    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("disk-write guard JD", encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(jd_path)]) == 0

    out_root = tmp_path / "out"
    slug_dirs = [p for p in out_root.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    # Exactly two files — cv.md + cover-letter.md — and no JD copy.
    artifact_names = {p.name for p in slug_dir.iterdir()}
    assert artifact_names == {"cv.md", "cover-letter.md"}


def test_paste_help_documents_file_flag_and_stdin_contract(
    capsys,
) -> None:
    from jobhunter.cli import main

    # main() catches argparse's SystemExit and returns the exit code.
    assert main(["paste", "--help"]) == 0
    captured = capsys.readouterr()
    help_text = captured.out
    assert "--file" in help_text
    assert "stdin" in help_text
    # Precedence rule must be visible in --help (AC3).
    assert "wins" in help_text.lower() or "precedence" in help_text.lower()
