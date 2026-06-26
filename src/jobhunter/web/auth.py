"""Auth helpers for machine-facing endpoints (DECISIONS.md §6).

Extracted from api.py so scan.py can import require_ingest_token without
creating a circular import (api.py imports the scan router).
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from jobhunter.runtime_config import load_ingest_token

# DECISIONS.md §6 — the FastAPI app binds to 127.0.0.1, so browser-origin
# requests are already gated by the loopback bind and bypass the token check.
# `testclient` is FastAPI's in-process TestClient default and is functionally
# loopback (no real network); it is treated as loopback so existing browser-
# path tests continue to exercise the route without a token.
_LOOPBACK_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _is_loopback_request(request: Request) -> bool:
    client = request.client
    return client is not None and client.host in _LOOPBACK_CLIENT_HOSTS


def require_ingest_token(request: Request) -> None:
    if _is_loopback_request(request):
        return

    expected = load_ingest_token()
    if not expected:
        raise HTTPException(
            status_code=401,
            detail="ingest_token_not_configured_on_server",
        )

    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(status_code=401, detail="missing_ingest_token")

    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="invalid_ingest_token")
