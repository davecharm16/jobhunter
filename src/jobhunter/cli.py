"""Command-line interface for Job Hunter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from jobhunter.canonical_cv import (
    CanonicalCVMissing,
    UnsupportedCanonicalCVFormat,
    read_canonical_cv,
)
from jobhunter.runtime_config import ConfigurationError, load_runtime_config


NO_AUTO_SUBMIT_STATEMENT = (
    "Job Hunter only writes local files and never submits to Upwork, LinkedIn, "
    "OnlineJobs.ph, or any job board."
)


PASTE_DESCRIPTION = (
    "Read a job description from stdin (pipe) or from --file PATH, then run "
    "the runtime safety gates. If both --file and a piped stdin are provided, "
    "--file wins (stdin is ignored). Tailoring lands in Story 1.5."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobhunter",
        description=NO_AUTO_SUBMIT_STATEMENT,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="{paste}")

    paste_parser = subparsers.add_parser(
        "paste",
        help="Ingest a JD from stdin or --file and run runtime safety gates.",
        description=PASTE_DESCRIPTION,
    )
    paste_parser.add_argument(
        "--file",
        dest="file",
        type=Path,
        default=None,
        help=(
            "Read JD from this file instead of stdin. If both --file and a "
            "piped stdin are provided, --file wins."
        ),
    )

    return parser


def handle_paste(jd_file: Path | None = None) -> int:
    try:
        load_runtime_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        read_canonical_cv()
    except (UnsupportedCanonicalCVFormat, CanonicalCVMissing) as exc:
        print(f"Canonical CV error: {exc}", file=sys.stderr)
        return 2

    jd_text, jd_source = _read_jd(jd_file)
    if jd_text is None:
        return 2

    print(
        f"jobhunter paste ingested JD ({len(jd_text)} chars from {jd_source}); "
        "tailoring lands in Story 1.5.",
        file=sys.stderr,
    )
    return 1


def _read_jd(jd_file: Path | None) -> tuple[str | None, str]:
    """Resolve JD text from --file or stdin.

    Returns (text, source) on success or (None, "") after writing an error to
    stderr. The TTY check guards against blocking on `stdin.read()` when the
    user invoked `jobhunter paste` interactively with no input piped in.
    """
    if jd_file is not None:
        try:
            raw = jd_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"JD file not found: {jd_file}", file=sys.stderr)
            return None, ""
        except UnicodeDecodeError as exc:
            # AC7: a binary file or non-UTF-8 text file is "a path that cannot
            # be read as text" — surface a clean error, not a traceback.
            print(
                f"JD file is not valid UTF-8 text ({jd_file}): {exc.reason}",
                file=sys.stderr,
            )
            return None, ""
        except OSError as exc:
            print(
                f"JD file not readable ({jd_file}): {exc}",
                file=sys.stderr,
            )
            return None, ""
        source = f"--file {jd_file}"
    elif sys.stdin.isatty():
        print(
            "Provide a JD via stdin (pipe input) or --file PATH.",
            file=sys.stderr,
        )
        return None, ""
    else:
        raw = sys.stdin.read()
        source = "stdin"

    if not raw.strip():
        print(
            "JD is empty; provide a non-empty JD via stdin or --file.",
            file=sys.stderr,
        )
        return None, ""

    return raw, source


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    parser = build_parser()

    if not args:
        parser.print_usage(sys.stderr)
        return 2

    try:
        namespace = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code)

    if namespace.command == "paste":
        return handle_paste(jd_file=namespace.file)

    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
