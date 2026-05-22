"""Story 1.4 gap-closure tests for `jobhunter paste` JD ingest.

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
    _isolated_cli_env,
    _run_module_cli,
)


# --- Gap 1: AC11 forbidden-imports static guardrail --------------------------


def test_cli_module_does_not_import_forbidden_runtime_deps() -> None:
    """AC11: stdlib only — no LLM SDK, HTTP client, or CLI-framework imports.

    Story 1.4 explicitly forbids adding `click`, `typer`, `rich`, `requests`,
    `httpx`, `urllib.request`, an LLM SDK (`openai`, `anthropic`), or a
    job-board client. Catching this at the source level prevents an accidental
    `import` from sneaking through code review.
    """
    cli_src = (PROJECT_ROOT / "src" / "jobhunter" / "cli.py").read_text(
        encoding="utf-8"
    )
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
        "import anthropic",
        "from anthropic",
    ]
    for needle in forbidden:
        assert needle not in cli_src, (
            f"cli.py must not contain `{needle}` — AC11 forbids new runtime "
            f"dependencies and HTTP/LLM/job-board clients in Story 1.4."
        )


def test_pyproject_runtime_dependencies_did_not_grow_in_story_1_4() -> None:
    """AC11: `pyproject.toml` runtime deps must stay at Stories 1.1+1.2 pins.

    The Story 1.4 dev note is explicit: no addition to `dependencies = [...]`.
    Pinning the dep list verbatim is the cheapest possible guard against a
    future dev quietly adding `requests`, `httpx`, an LLM SDK, etc.
    """
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # The Story 1.1 + 1.2 pins. Story 1.4 must not extend this block.
    assert 'jsonschema>=4.21' in pyproject
    assert 'python-dotenv>=1.2.2' in pyproject
    # No HTTP/LLM client was added.
    for forbidden in (
        '"requests',
        '"httpx',
        '"openai',
        '"anthropic',
        '"click',
        '"typer',
        '"rich',
    ):
        assert forbidden not in pyproject, (
            f"pyproject.toml grew an unexpected runtime dependency containing "
            f"`{forbidden}` — Story 1.4 must add none."
        )


# --- Gap 2: UTF-8 encoding via --file ----------------------------------------


def test_paste_subprocess_file_with_utf8_unicode_content_succeeds(
    tmp_path,
) -> None:
    """`--file` reads with `encoding="utf-8"` — non-ASCII content must round-trip.

    Many real JDs contain en-dashes, curly quotes, accented characters, or
    emoji. Reading them with the wrong codec would either crash or corrupt
    the byte count in the boundary message. Verifies the explicit
    `encoding="utf-8"` argument in `_read_jd()` is doing its job.
    """
    jd_path = tmp_path / "jd-unicode.txt"
    jd_text = (
        "Senior Python role — “must have” FastAPI 🚀\n"
        "Compensation: €80k–€100k. Café-style team.\n"
    )
    jd_path.write_text(jd_text, encoding="utf-8")

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

    assert result.returncode == 1, (
        f"unicode JD via --file should succeed; got rc={result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    assert "Story 1.5" in result.stderr
    assert "--file" in result.stderr
    # Char-count in the boundary message should equal len(jd_text) — proves
    # the file was decoded as UTF-8, not bytes or latin-1.
    assert f"{len(jd_text)} chars" in result.stderr, (
        f"Boundary message must report {len(jd_text)} chars; got: "
        f"{result.stderr!r}"
    )


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


def test_paste_subprocess_boundary_message_includes_char_count_and_file_path(
    tmp_path,
) -> None:
    """AC9: boundary message names char count AND the actual file path.

    The Story 1.4 contract says the success message is
    `f"jobhunter paste ingested JD ({len(jd_text)} chars from {jd_source}); "
    "tailoring lands in Story 1.5."` — where `jd_source` is `f"--file {path}"`
    on the file branch. Existing tests only check that literal "--file"
    substring appears. This pins the full contract: byte count + actual path.
    """
    jd_path = tmp_path / "jd-contract.txt"
    jd_text = "Senior Python role with FastAPI experience required.\n"
    jd_path.write_text(jd_text, encoding="utf-8")

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

    assert result.returncode == 1
    assert "Story 1.5" in result.stderr
    # Char count appears verbatim.
    assert f"{len(jd_text)} chars" in result.stderr, (
        f"Expected '{len(jd_text)} chars' in stderr; got: {result.stderr!r}"
    )
    # The actual file path appears in the boundary message (provenance).
    assert str(jd_path) in result.stderr, (
        f"Expected file path '{jd_path}' in stderr; got: {result.stderr!r}"
    )


def test_paste_subprocess_boundary_message_for_stdin_includes_char_count(
    tmp_path,
) -> None:
    """AC9: stdin boundary message also names char count + 'stdin' source."""
    jd_text = "Senior Python role at Acme.\n"

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text=jd_text,
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 1
    assert "Story 1.5" in result.stderr
    assert f"{len(jd_text)} chars" in result.stderr
    assert "stdin" in result.stderr


# --- Gap 6: AC10 success path: no ./out/ written via subprocess --------------


def test_paste_subprocess_success_does_not_create_out_directory_with_file(
    tmp_path,
) -> None:
    """AC10: Story 1.4 success path must NOT create `./out/` — file branch.

    Existing rejection-path tests assert `not output_dir.exists()`, and one
    in-process test (`test_cli_paste_does_not_write_jd_to_disk`) checks the
    file branch, but no subprocess test asserts the success path leaves the
    cwd clean. This is the load-bearing guard for Story 1.5 (which is where
    the first `./out/<slug>/` write lands).
    """
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("Senior Python role.\n", encoding="utf-8")
    output_dir = tmp_path / "out"

    # Build the isolated env first (this mirrors canonical-cv.json + src/ into
    # tmp_path), THEN snapshot so we only flag entries the CLI itself wrote.
    env = _isolated_cli_env(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )
    before_paths = {p.name for p in tmp_path.iterdir()}

    result = _run_module_cli(
        "paste",
        "--file",
        str(jd_path),
        cwd=tmp_path,
        env=env,
    )

    assert result.returncode == 1
    assert not output_dir.exists(), (
        "Story 1.4 success path must not create ./out/ — that lands in 1.5."
    )

    after_paths = {p.name for p in tmp_path.iterdir()}
    assert after_paths == before_paths, (
        f"Story 1.4 success path wrote unexpected entries: "
        f"{after_paths - before_paths}"
    )


def test_paste_subprocess_success_does_not_create_out_directory_with_stdin(
    tmp_path,
) -> None:
    """AC10: stdin success path also leaves cwd clean (no `./out/`)."""
    output_dir = tmp_path / "out"

    env = _isolated_cli_env(
        tmp_path,
        LLM_API_KEY="test-key",
        MONTHLY_SPEND_CAP_USD="25.00",
    )
    before_paths = {p.name for p in tmp_path.iterdir()}

    result = _run_module_cli(
        "paste",
        cwd=tmp_path,
        input_text="Senior Python role.\n",
        env=env,
    )

    assert result.returncode == 1
    assert not output_dir.exists()

    after_paths = {p.name for p in tmp_path.iterdir()}
    assert after_paths == before_paths


# --- Gap 7: --file=PATH (equals syntax) -------------------------------------


def test_paste_subprocess_file_equals_syntax_works(tmp_path) -> None:
    """`argparse` accepts `--file=PATH` as well as `--file PATH`.

    `argparse` supports both syntaxes natively, but it's worth a smoke test
    so that anyone scripting `jobhunter paste --file="/path/to/jd.txt"`
    (e.g. from a Makefile or shell alias) is not surprised.
    """
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("Senior Python role.\n", encoding="utf-8")

    result = _run_module_cli(
        f"paste",
        f"--file={jd_path}",
        cwd=tmp_path,
        env=_isolated_cli_env(
            tmp_path,
            LLM_API_KEY="test-key",
            MONTHLY_SPEND_CAP_USD="25.00",
        ),
    )

    assert result.returncode == 1
    assert "Story 1.5" in result.stderr
    assert "--file" in result.stderr


# --- Gap 8: In-process: --file with unicode + char count --------------------


def test_cli_paste_in_process_utf8_file_char_count_reflects_unicode_length(
    monkeypatch, capsys, tmp_path, tmp_canonical_cv
) -> None:
    """Unicode JD via --file: the {n} chars count in the boundary message
    must equal `len(jd_text)` after UTF-8 decoding, not the byte length.

    A regression where someone replaces `Path.read_text(encoding="utf-8")`
    with `Path.read_bytes()` or omits the encoding would cause a byte-count
    or a `UnicodeDecodeError`. This test is the load-bearing assertion for
    the encoding contract.
    """
    from jobhunter.cli import main

    jd_path = tmp_path / "jd-unicode.txt"
    jd_text = "Café résumé — 🚀 €100k\n"
    jd_path.write_text(jd_text, encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")

    assert main(["paste", "--file", str(jd_path)]) == 1
    captured = capsys.readouterr()
    assert "Story 1.5" in captured.err
    assert f"{len(jd_text)} chars" in captured.err, (
        f"Char count must equal len(jd_text)={len(jd_text)} (after UTF-8 "
        f"decode), not the byte length. Got: {captured.err!r}"
    )


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

    The existing subprocess test for precedence (`test_paste_subprocess_
    file_precedence_over_stdin`) is good, but lacks an in-process companion.
    This one pipes a sentinel string via `io.StringIO`, passes `--file`
    with different content, and asserts the file content's char count
    appears in the boundary message — proving stdin was ignored.
    """
    from jobhunter.cli import main

    jd_path = tmp_path / "from-file.txt"
    file_text = "FROM FILE content here.\n"
    jd_path.write_text(file_text, encoding="utf-8")

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MONTHLY_SPEND_CAP_USD", "25.00")
    # Even with stdin piped, --file should win.
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("FROM STDIN — should be ignored\n")
    )

    assert main(["paste", "--file", str(jd_path)]) == 1
    captured = capsys.readouterr()
    assert "Story 1.5" in captured.err
    assert "--file" in captured.err
    # The character count must match the file's content, NOT stdin's.
    assert f"{len(file_text)} chars" in captured.err


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
