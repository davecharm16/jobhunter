"""Static import guardrail for `jobhunter.web.routes.override` (Story 6.4, AC4).

The override handler must never POST anywhere — not to the GChat webhook
(`jobhunter.notifier`), not to a job board, not anywhere. This guard is
enforced two ways in v1:

1. Statically (this test): the override route module must not import the
   notifier or any HTTP-client library. If a future refactor accidentally
   pulls one of those in, this test flips red BEFORE any HTTP call happens.

2. Dynamically (integration test `test_override_does_not_call_notifier`):
   patches `jobhunter.notifier.notify` and asserts zero calls during a
   live override request.

The two together pin FR44 / FR51: the override surface stays a pure
filesystem operation — rename one directory, rewrite one JSON sidecar.

Counterpart to `test_jd_parser_imports.py` (Story 2.3) and
`test_keyword_stuffing_imports.py` (Story 5.1) — same idiom, different
forbidden surface.
"""

from __future__ import annotations

import ast

from jobhunter.config import PROJECT_ROOT


OVERRIDE_ROUTE_PATH = (
    PROJECT_ROOT / "src" / "jobhunter" / "web" / "routes" / "override.py"
)


def _collect_imports(source: str) -> set[str]:
    """Return the set of fully qualified module names imported by *source*.

    Walks the AST so this guard is robust against multi-line imports and
    aliasing — a plain substring search like `"import httpx"` would miss
    `from httpx import Client` or a conditional import inside a function.
    """
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # `from X import Y` -> record `X` (the source module).
            if node.module is not None:
                names.add(node.module)
    return names


def test_override_source_file_exists() -> None:
    assert OVERRIDE_ROUTE_PATH.is_file(), (
        f"expected override route at {OVERRIDE_ROUTE_PATH}; "
        "did Story 6.4 land?"
    )


def test_override_does_not_import_notifier() -> None:
    """AC4: no GChat webhook code path may reach this module."""
    imports = _collect_imports(OVERRIDE_ROUTE_PATH.read_text(encoding="utf-8"))
    for name in imports:
        assert "notifier" not in name, (
            f"override.py imports `{name}` — the notifier (Story 6.1) "
            "must never be reachable from the override handler (AC4)."
        )


def test_override_does_not_import_http_clients() -> None:
    """AC4: the override handler is filesystem-only — no transport surface."""
    imports = _collect_imports(OVERRIDE_ROUTE_PATH.read_text(encoding="utf-8"))
    forbidden_prefixes = (
        "httpx",
        "requests",
        "urllib",
        "urllib3",
        "http.client",
        "aiohttp",
    )
    for name in imports:
        for prefix in forbidden_prefixes:
            assert not (name == prefix or name.startswith(prefix + ".")), (
                f"override.py imports `{name}` — HTTP-client modules are "
                f"forbidden here (AC4: zero non-loopback POSTs)."
            )


def test_override_does_not_reference_job_board_hostnames() -> None:
    """AC4: structural guard against any job-board hostname appearing inline.

    Mirrors the repo-wide FR44/FR11 hostname check (no Upwork/LinkedIn/
    OnlineJobs.ph endpoint baked into source). The override route must
    not name them either, even in a comment that could be flipped into a
    code path by a future edit.
    """
    source = OVERRIDE_ROUTE_PATH.read_text(encoding="utf-8")
    forbidden_hosts = (
        "upwork.com",
        "linkedin.com",
        "onlinejobs.ph",
    )
    lower = source.lower()
    for host in forbidden_hosts:
        assert host not in lower, (
            f"override.py mentions `{host}` — job-board hostnames must "
            "never appear in the override handler (FR44 / FR51)."
        )


def test_override_imports_only_stdlib_and_jobhunter_and_fastapi() -> None:
    """Belt-and-braces: the import surface stays minimal and inspectable.

    Allows: stdlib modules, `jobhunter.*`, `fastapi`, `pydantic`. Anything
    else is suspicious enough to fail the static guard so a code-review
    catches it BEFORE the handler can do something unexpected on disk
    or on the network.
    """
    imports = _collect_imports(OVERRIDE_ROUTE_PATH.read_text(encoding="utf-8"))
    allowed_prefixes = (
        # Stdlib modules used by the handler.
        "__future__",
        "json",
        "os",
        "pathlib",
        "typing",
        "dataclasses",
        # First-party.
        "jobhunter",
        # Web framework + validation.
        "fastapi",
        "pydantic",
    )
    for name in imports:
        ok = any(
            name == prefix or name.startswith(prefix + ".")
            for prefix in allowed_prefixes
        )
        assert ok, (
            f"override.py imports `{name}` — not on the AC4 allow-list "
            f"({', '.join(allowed_prefixes)})."
        )
