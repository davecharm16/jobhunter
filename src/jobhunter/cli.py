"""CLI entry stub. Story 1.2 wires real subcommands."""

import sys


def main() -> int:
    sys.stderr.write(
        "jobhunter: CLI not implemented yet (Story 1.2 will wire subcommands).\n"
        "usage: jobhunter <subcommand> [args]\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
