"""Command-line interface for Job Hunter."""

from __future__ import annotations

import argparse
import sys

from jobhunter.runtime_config import ConfigurationError, load_runtime_config


NO_AUTO_SUBMIT_STATEMENT = (
    "Job Hunter only writes local files and never submits to Upwork, LinkedIn, "
    "OnlineJobs.ph, or any job board."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobhunter",
        description=NO_AUTO_SUBMIT_STATEMENT,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="{paste}")

    paste_parser = subparsers.add_parser(
        "paste",
        help="Validate runtime safety gates for future pasted job descriptions.",
        description=(
            "Validate runtime safety gates for paste mode. JD ingest lands in "
            "Story 1.4."
        ),
    )
    paste_parser.set_defaults(func=handle_paste)

    return parser


def handle_paste() -> int:
    try:
        load_runtime_config()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    print(
        "jobhunter paste is scaffolded; JD ingest lands in Story 1.4.",
        file=sys.stderr,
    )
    return 1


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

    command = getattr(namespace, "func", None)
    if command is None:
        parser.print_usage(sys.stderr)
        return 2

    return command()


if __name__ == "__main__":
    raise SystemExit(main())
