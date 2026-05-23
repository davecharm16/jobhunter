"""Launcher for the Job Hunter web app (DECISIONS.md §6).

The `jobhunter` console script takes no subcommands; it boots a FastAPI
server on `127.0.0.1:8765` and (best-effort) opens the default browser.
Use `--port` or `JOBHUNTER_WEB_PORT` to override; `--no-browser` skips the
browser launch.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import webbrowser

import uvicorn


DEFAULT_PORT = 8765
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class NonLoopbackBindError(RuntimeError):
    """Raised before the socket opens when a non-loopback host is requested."""


def ensure_loopback(host: str) -> None:
    if host not in LOOPBACK_HOSTS:
        raise NonLoopbackBindError(
            f"refusing to bind to non-loopback host {host!r}; "
            f"only {sorted(LOOPBACK_HOSTS)} are allowed"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobhunter",
        description=(
            "Boot the Job Hunter local web app on 127.0.0.1. "
            "Single-user, localhost-only; no auth, no outbound submission."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            f"Port to bind on 127.0.0.1 (default {DEFAULT_PORT}, "
            "overridable via JOBHUNTER_WEB_PORT)."
        ),
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not attempt to open the default browser.",
    )
    return parser


def resolve_port(cli_port: int | None) -> int:
    if cli_port is not None:
        return cli_port
    env_port = os.environ.get("JOBHUNTER_WEB_PORT")
    if env_port is None or not env_port.strip():
        return DEFAULT_PORT
    return int(env_port.strip())


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    parser = build_parser()

    try:
        namespace = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0

    host = "127.0.0.1"
    ensure_loopback(host)
    port = resolve_port(namespace.port)
    url = f"http://{host}:{port}/"

    print(f"jobhunter web app listening on {url}", file=sys.stderr)

    if not namespace.no_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001 — browser launch is best-effort
            print(f"jobhunter: could not open browser ({exc})", file=sys.stderr)

    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        uvicorn.run(
            "jobhunter.web.api:app",
            host=host,
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
