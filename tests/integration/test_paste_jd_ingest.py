"""Gap-closure tests for `jobhunter paste` JD ingest.

Story 1.5 updates: tests that used to assert exit `1` + `"Story 1.5"` stderr
boundary message have been rewritten or replaced because Story 1.5 produces
the actual tailored artifacts on the happy path. The rejection-path tests
that short-circuit before the LLM client are unchanged.

These tests target ACs that the Story 1.4 dev pass already covered at a high
level, but that left specific contract details untested. Each test is annotated
with the AC and the specific gap it closes.

Conventions inherited from `tests/integration/test_cli_entry.py`:
- Subprocess tests use the `_isolated_cli_env(tmp_path, ...)` helper so the
  developer's real `.env` cannot pollute the run, and so the committed
  `canonical-cv.json` is mirrored into the isolated tree.
- In-process tests use the `tmp_canonical_cv` fixture (from `tests/conftest.py`)
  to bind a valid CV without touching the real one.
- Substring assertions anchor on contract substrings (`"Story 1.5"`,
  `"--file"`, `"stdin"`, the JD path, the word `"empty"`) so copywriting can
  evolve without rewriting tests.
"""

from __future__ import annotations

import io
import sys

from jobhunter.config import PROJECT_ROOT
from tests.integration._cli_helpers import (
    FAKE_COVER_LETTER_MARKDOWN,
    FAKE_CV_MARKDOWN,
    _isolated_cli_env,
    _isolated_cli_env_with_fake_llm,
    _run_module_cli,
)


# --- Gap 1: AC11 forbidden-imports static guardrail --------------------------


def test_cli_module_does_not_import_forbidden_runtime_deps() -> None:
    """AC11 (Story 1.5): the chosen LLM SDK (`anthropic`) is allowed in
    `llm_client.py` only — every other `src/jobhunter/` source file remains
    stdlib-only with respect to HTTP clients, CLI frameworks, and a second
    LLM SDK.
    """
    jobhunter_src_root = PROJECT_ROOT / "src" / "jobhunter"
    forbidden = [
        "import click",
        "from click",
        "import typer",
        "from typer",
        "import rich",
        "from rich",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
        "import urllib.request",
        "from urllib.request",
        "import openai",
        "from openai",
    ]

    for py_path in sorted(jobhunter_src_root.glob("*.py")):
        src = py_path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in src, (
                f"{py_path.name} must not contain `{needle}` — Story 1.5 "
                "AC11 forbids HTTP clients, CLI frameworks, and a second LLM "
                "SDK from any module in src/jobhunter/."
            )

        if py_path.name == "llm_client.py":
            # The single permitted SDK home.
            continue
        for needle in ("import anthropic", "from anthropic"):
            assert needle not in src, (
                f"{py_path.name} must not contain `{needle}` — the LLM SDK "
                "is permitted only in llm_client.py (Story 1.5 AC11)."
            )


def test_pyproject_runtime_dependencies_match_story_1_5_pinning() -> None:
    """AC11 (Story 1.5): pyproject.toml grew by exactly one new runtime entry
    (`anthropic>=0.40.0`). Other forbidden HTTP/CLI/LLM clients stay out.
    """
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # The Story 1.1 + 1.2 pins, plus the single new Story 1.5 entry.
    assert 'jsonschema>=4.21' in pyproject
    assert 'python-dotenv>=1.2.2' in pyproject
    assert 'anthropic>=0.40.0' in pyproject
    # No other HTTP / LLM / CLI-framework client was added.
    for forbidden in (
        '"requests',
        '"httpx',
        '"openai',
        '"click',
        '"typer',
        '"rich',
    ):
        assert forbidden not in pyproject, (
            f"pyproject.toml grew an unexpected runtime dependency containing "
            f"`{forbidden}` — Story 1.5 must add only `anthropic`."
        )


def test_no_job_board_hostnames_in_jobhunter_source() -> None:
    """AC8 (FR44/FR11): no job-board hostname appears in any jobhunter source.

    String-grep guard — catches an accidental URL even before it could
    plausibly be wired into a runtime call.
    """
    jobhunter_src_root = PROJECT_ROOT / "src" / "jobhunter"
    forbidden_hosts = ("upwork.com", "linkedin.com", "onlinejobs.ph")

    for py_path in sorted(jobhunter_src_root.glob("*.py")):
        src = py_path.read_text(encoding="utf-8").lower()
        for host in forbidden_hosts:
            assert host not in src, (
                f"{py_path.name} contains forbidden job-board hostname "
                f"`{host}` — Story 1.5 AC8 (FR44/FR11) forbids any job-board "
                "URL in source."
            )


def test_gitignore_excludes_cost_ledger_and_out_directory() -> None:
    """AC12: `.gitignore` must list both `out/` and `.cost-ledger.json` so
    neither the per-application packages nor the cumulative spend ledger
    can be accidentally committed.

    These are load-bearing privacy + integrity guards: `.cost-ledger.json`
    contains running spend data, and `out/<slug>/` directories contain
    tailored CVs that include the candidate's full work history.
    """
    gitignore_path = PROJECT_ROOT / ".gitignore"
    assert gitignore_path.is_file(), ".gitignore must exist at repo root"

    content = gitignore_path.read_text(encoding="utf-8")
    lines = {line.strip() for line in content.splitlines() if line.strip()}

    assert ".cost-ledger.json" in lines, (
        "`.gitignore` must contain `.cost-ledger.json` on its own line "
        "(Story 1.5 AC12)."
    )
    assert "out/" in lines, (
        "`.gitignore` must contain `out/` on its own line so tailored "
        "artifacts are not committed (Story 1.5 AC12)."
    )


# --- Gap 2: UTF-8 encoding via --file ----------------------------------------


def test_paste_subprocess_file_with_utf8_unicode_content_succeeds(
    tmp_path,
) -> None:
    """`--file` reads with `encoding="utf-8"` — non-ASCII content must round-trip.

    Verifies the explicit `encoding="utf-8"` argument in `_read_jd()` is doing
    its job: a unicode JD reaches the (stubbed) LLM and emerges as an artifact
    file on disk without a UnicodeDecodeError.
    """
    jd_path = tmp_path / "jd-unicode.txt"
    jd_text = (
        "Senior Python role — “must have” FastAPI 🚀\n"
        "Compensation: €80k–€100k. Café-style team.\n"
    )
    jd_path.write_text(jd_text, encoding="utf-8")
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0, (
        f"unicode JD via --file should succeed; got rc={result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    assert "Tailored package written to" in result.stderr
    assert "--file" in result.stderr
    assert output_dir.is_dir()
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    assert (slug_dirs[0] / "cv.md").exists()
    assert (slug_dirs[0] / "cover-letter.md").exists()


# --- Gap 3: Empty --file (symmetric to AC5 empty stdin) ----------------------


def test_paste_subprocess_empty_file_exits_two(tmp_path) -> None:
    """AC5 spirit: empty `--file` content rejected just like empty stdin.

    `_read_jd()` applies `if not raw.strip()` to BOTH branches, but only the
    stdin branch was explicitly tested. This closes the symmetric file gap.
    """
    jd_path = tmp_path / "empty-jd.txt"
    jd_path.write_text("", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
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


def test_paste_subprocess_whitespace_only_file_exits_two(tmp_path) -> None:
    """AC5 spirit: whitespace-only `--file` content rejected just like stdin."""
    jd_path = tmp_path / "whitespace-jd.txt"
    jd_path.write_text("   \n\t  \n\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
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


# --- Gap 4: AC8 ordering: --file does not bypass env gate --------------------


def test_paste_subprocess_missing_llm_key_does_not_read_provided_file(
    tmp_path,
) -> None:
    """AC8: env gate fires BEFORE --file is opened.

    All existing AC8 regression guards pipe stdin and assert it isn't consumed.
    This is the symmetric guarantee for the `--file` branch: with a valid file
    path and a missing `LLM_API_KEY`, the env error must fire and the file
    must not even be touched. Strategy: point `--file` at a tmp path that
    exists as a JSON Resume sentinel that should NEVER appear in stderr,
    proving the file was not read.
    """
    output_dir = tmp_path / "out"
    jd_path = tmp_path / "jd-with-sentinel.txt"
    sentinel = "MUST_NOT_BE_READ_BEFORE_ENV_GATE"
    jd_path.write_text(sentinel + "\n", encoding="utf-8")

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=_isolated_cli_env(tmp_path, MONTHLY_SPEND_CAP_USD="25.00"),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "LLM_API_KEY" in result.stderr
    # File contents must NOT appear in stderr — the env gate short-circuited.
    assert sentinel not in result.stderr
    # And of course no Story-1.5 boundary message.
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_missing_cap_does_not_read_provided_file(
    tmp_path,
) -> None:
    """AC8: missing MONTHLY_SPEND_CAP_USD fires before --file is opened."""
    output_dir = tmp_path / "out"
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("Senior Python role\n", encoding="utf-8")

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=_isolated_cli_env(tmp_path, LLM_API_KEY="test-key"),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "MONTHLY_SPEND_CAP_USD" in result.stderr
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


# --- Gap 5: Boundary message contract (AC9 strict shape) ---------------------


def test_paste_subprocess_success_message_names_slug_path_cost_and_cap(
    tmp_path,
) -> None:
    """Story 1.5 AC1: success stderr names the out path, the per-call cost,
    and the monthly cap — file branch.
    """
    jd_path = tmp_path / "jd-contract.txt"
    jd_text = "Senior Python role with FastAPI experience required.\n"
    jd_path.write_text(jd_text, encoding="utf-8")

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}\nstderr: {result.stderr}"
    )
    assert "Tailored package written to" in result.stderr
    # Per-call cost (dollar) is visible.
    assert "$0." in result.stderr
    # The cap is named in the success summary.
    assert "$25.00" in result.stderr
    assert "--file" in result.stderr


def test_paste_subprocess_success_message_for_stdin_names_slug_and_cost(
    tmp_path,
) -> None:
    """Story 1.5 AC1: success stderr for the stdin branch carries the same
    contract — out path, cost, cap, and `stdin` as the JD source.
    """
    jd_text = "Senior Python role at Acme.\n"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text=jd_text,
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0
    assert "Tailored package written to" in result.stderr
    assert "$0." in result.stderr
    assert "$25.00" in result.stderr
    assert "stdin" in result.stderr


# --- Gap 6: AC10 success path: no ./out/ written via subprocess --------------


def test_paste_subprocess_success_creates_out_slug_directory_with_file(
    tmp_path,
) -> None:
    """Story 1.5 AC1 (subprocess, file branch): success creates ./out/<slug>/
    with both `cv.md` and `cover-letter.md`. This is the inversion of the
    Story 1.4 'no ./out/' guard — Story 1.5 is where artifacts land.
    """
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("Senior Python role.\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=env,
    )

    assert result.returncode == 0
    assert output_dir.is_dir(), "./out/ should exist after a successful run"
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    slug_dir = slug_dirs[0]
    assert (slug_dir / "cv.md").exists()
    assert (slug_dir / "cover-letter.md").exists()


def test_paste_subprocess_success_creates_out_slug_directory_with_stdin(
    tmp_path,
) -> None:
    """Story 1.5 AC1 (subprocess, stdin branch): success creates ./out/<slug>/."""
    output_dir = tmp_path / "out"

    env = _isolated_cli_env_with_fake_llm(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 0
    assert output_dir.is_dir()
    slug_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(slug_dirs) == 1
    assert (slug_dirs[0] / "cv.md").exists()
    assert (slug_dirs[0] / "cover-letter.md").exists()


# --- Gap 7: --file=PATH (equals syntax) -------------------------------------


def test_paste_subprocess_file_equals_syntax_works(tmp_path) -> None:
    """`argparse` accepts `--file=PATH` as well as `--file PATH`.

    Smoke test so that anyone scripting `jobhunter paste --file="/path/to/jd.txt"`
    (e.g. from a Makefile or shell alias) is not surprised.
    """
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("Senior Python role.\n", encoding="utf-8")

    result = _run_module_cli(
        f"paste",
        f"--file={jd_path}",
        cwd=tmp_path,
        env=_isolated_cli_env_with_fake_llm(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 0
    assert "Tailored package written to" in result.stderr
    assert "--file" in result.stderr


# --- Gap 8: In-process: --file with unicode + char count --------------------


def test_cli_paste_in_process_utf8_file_reaches_tailoring_with_unicode(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """Unicode JD via --file: file decodes as UTF-8 (no UnicodeDecodeError),
    reaches the tailoring step (here stubbed), and emerges as artifacts.

    Regression guard for the explicit `encoding="utf-8"` argument in
    `_read_jd()`.
    """
    from decimal import Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.cli import main
    from jobhunter.llm_client import TailoringResult

    captured_jd: dict[str, str] = {}

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        captured_jd["text"] = jd_text
        return TailoringResult(
            cv_markdown="# tailored\n",
            cover_letter_markdown="cover letter\n",
            cost_usd=Decimal("0.0042"),
            input_tokens=10,
            output_tokens=5,
        )

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

    jd_path = tmp_path / "jd-unicode.txt"
    jd_text = "Café résumé — 🚀 €100k\n"
    jd_path.write_text(jd_text, encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(jd_path)]) == 0
    captured = capsys.readouterr()
    assert "Tailored package written to" in captured.err
    # Tailoring received the full UTF-8-decoded text, not bytes or replaced chars.
    assert captured_jd["text"] == jd_text


# --- Gap 9: In-process: empty --file rejection ------------------------------


def test_cli_paste_in_process_empty_file_exits_two(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """AC5-symmetric in-process: empty file via --file → exit 2."""
    from jobhunter.cli import main

    jd_path = tmp_path / "empty.txt"
    jd_path.write_text("", encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(jd_path)]) == 2
    captured = capsys.readouterr()
    assert "empty" in captured.err.lower()
    assert "Story 1.5" not in captured.err
    assert captured.out == ""


# --- Gap 10: In-process: --file precedence over stdin (regression guard) ----


def test_cli_paste_in_process_file_precedence_over_stdin(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """AC3: --file beats stdin in-process too.

    Pipes a sentinel string via stdin, passes `--file` with different
    content, and asserts the tailoring step received the file's text,
    proving stdin was ignored.
    """
    from decimal import Decimal

    import jobhunter.cli as cli_module
    import jobhunter.tailoring as tailoring_module
    from jobhunter.cli import main
    from jobhunter.llm_client import TailoringResult

    captured_jd: dict[str, str] = {}

    def fake_tailor(canonical_cv, jd_text, *, api_key, timeout_seconds):
        captured_jd["text"] = jd_text
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

    jd_path = tmp_path / "from-file.txt"
    file_text = "FROM FILE content here.\n"
    jd_path.write_text(file_text, encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("FROM STDIN — should be ignored\n")
    )

    assert main(["paste", "--file", str(jd_path)]) == 0
    captured = capsys.readouterr()
    assert "Tailored package written to" in captured.err
    assert "--file" in captured.err
    # Tailoring received the file's content, NOT stdin's.
    assert captured_jd["text"] == file_text


# --- Gap 11: AC7 — non-UTF-8 / binary --file rejected cleanly ---------------


def test_paste_subprocess_non_utf8_file_exits_two_without_traceback(
    tmp_path,
) -> None:
    """AC7: a `--file` whose bytes are not valid UTF-8 must exit cleanly.

    AC7 says any path that "cannot be read as text" surfaces as a clean error,
    "not as an uncaught ... traceback". A latin-1 file with a high byte (e.g.
    `é` encoded as `0xe9`) is exactly that — `Path.read_text(encoding="utf-8")`
    raises `UnicodeDecodeError`, which is **not** a subclass of `OSError`, so
    the old handler (`IsADirectoryError | PermissionError | OSError`) let it
    propagate. This regression guard ensures the dedicated handler stays in
    place.
    """
    jd_path = tmp_path / "jd-latin1.txt"
    # Valid latin-1 byte that is invalid as a UTF-8 continuation byte.
    jd_path.write_bytes(b"Senior Python role with caf\xe9.\n")
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    # The path must appear in stderr so the user knows which file failed.
    assert str(jd_path) in result.stderr
    # A clean error, not a Python traceback.
    assert "Traceback" not in result.stderr
    assert "UnicodeDecodeError" not in result.stderr
    # The Story-1.5 boundary message must NOT appear.
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


def test_paste_subprocess_binary_file_exits_two_without_traceback(
    tmp_path,
) -> None:
    """AC7: a `--file` pointed at a binary file (e.g. someone passes a PDF by
    mistake) must exit 2 with a clean error, not crash with a traceback.
    """
    jd_path = tmp_path / "scan.bin"
    # PDF magic header + a byte sequence that's invalid UTF-8.
    jd_path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    output_dir = tmp_path / "out"

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert str(jd_path) in result.stderr
    assert "Traceback" not in result.stderr
    assert "Story 1.5" not in result.stderr
    assert not output_dir.exists()


def test_cli_paste_in_process_non_utf8_file_exits_two(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """AC7 in-process companion: UnicodeDecodeError → clean exit 2.

    Belt-and-braces: even if the subprocess path is masked by a future change
    to how Python reports tracebacks, the in-process assertion proves the
    handler returns 2 and writes a clean error to stderr.
    """
    from jobhunter.cli import main

    jd_path = tmp_path / "jd-binary.txt"
    jd_path.write_bytes(b"\xff\xfe\x00\x01\x02")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(jd_path)]) == 2
    captured = capsys.readouterr()
    assert str(jd_path) in captured.err
    assert "Story 1.5" not in captured.err
    assert captured.out == ""
