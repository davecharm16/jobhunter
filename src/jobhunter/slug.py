"""Deterministic-given-inputs slug for `./out/<slug>/` artifact directories.

The slug is `{UTC_TIMESTAMP}-{JD_FIRST_LINE_SLUG}` (Story 1.5 AC2). Two reasons
for putting the timestamp first: (a) `ls ./out/` sorts chronologically so the
author scrolls the most recent applications first, (b) same-second collisions
on identical first-line slugs are surfaced loudly by the slug-collision policy
in `tailoring.run_tailoring()`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


__all__ = ["SLUG_REGEX", "make_slug"]


SLUG_REGEX = re.compile(r"^[0-9]{8}T[0-9]{6}Z(-[a-z0-9-]+)?$")
_MAX_JD_SLUG_LEN = 40
_NON_SLUG_RUN = re.compile(r"[^a-z0-9]+")


def make_slug(jd_text: str, *, now: datetime | None = None) -> str:
    """Return a deterministic, filesystem-safe slug for the JD.

    The timestamp comes from *now* (UTC) — injectable for tests.
    """
    moment = now or datetime.now(timezone.utc)
    ts = moment.strftime("%Y%m%dT%H%M%SZ")

    first_line = next(
        (line.strip() for line in jd_text.splitlines() if line.strip()),
        "",
    )
    normalized = _NON_SLUG_RUN.sub("-", first_line.lower()).strip("-")
    truncated = _truncate(normalized, _MAX_JD_SLUG_LEN)
    jd_part = truncated or "jd"

    slug = f"{ts}-{jd_part}"

    if not SLUG_REGEX.fullmatch(slug):
        raise RuntimeError(
            f"internal slug error: produced non-conforming slug {slug!r}"
        )

    return slug


def _truncate(value: str, max_len: int) -> str:
    """Cut *value* at the last `-` boundary at or under *max_len*, else hard cut."""
    if len(value) <= max_len:
        return value
    head = value[:max_len]
    last_dash = head.rfind("-")
    if last_dash > 0:
        return head[:last_dash].rstrip("-")
    return head.rstrip("-")
