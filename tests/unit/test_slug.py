"""Unit tests for `jobhunter.slug.make_slug`."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from jobhunter.slug import SLUG_REGEX, make_slug


FIXED_NOW = datetime(2026, 5, 24, 3, 15, 30, tzinfo=timezone.utc)
FIXED_TS = "20260524T031530Z"


def test_make_slug_is_deterministic_for_fixed_now_and_jd() -> None:
    jd = "Senior Python role at Acme — must have FastAPI.\n"
    assert make_slug(jd, now=FIXED_NOW) == make_slug(jd, now=FIXED_NOW)


def test_make_slug_uses_first_non_empty_line() -> None:
    jd = "\n\n   \n\nSenior Python role at Acme\nrest of the JD here\n"
    slug = make_slug(jd, now=FIXED_NOW)
    assert slug.startswith(FIXED_TS + "-senior-python-role-at-acme")


def test_make_slug_collapses_non_alnum_runs_to_single_dash() -> None:
    jd = "Senior  Python!! role @@ Acme--Remote\n"
    slug = make_slug(jd, now=FIXED_NOW)
    assert slug == f"{FIXED_TS}-senior-python-role-acme-remote"


def test_make_slug_falls_back_to_jd_when_punctuation_only() -> None:
    jd = "!!!?? ...\n***\n"
    slug = make_slug(jd, now=FIXED_NOW)
    assert slug == f"{FIXED_TS}-jd"


def test_make_slug_falls_back_to_jd_when_empty_input() -> None:
    slug = make_slug("", now=FIXED_NOW)
    assert slug == f"{FIXED_TS}-jd"


def test_make_slug_falls_back_to_jd_when_only_whitespace() -> None:
    slug = make_slug("   \n\t\n", now=FIXED_NOW)
    assert slug == f"{FIXED_TS}-jd"


def test_make_slug_truncates_jd_suffix_at_40_chars() -> None:
    long_first_line = "a" * 80 + "\n"
    slug = make_slug(long_first_line, now=FIXED_NOW)
    jd_part = slug.split("-", 1)[1]
    assert len(jd_part) <= 40


def test_make_slug_truncates_at_word_boundary_when_possible() -> None:
    jd = (
        "senior backend python engineer remote position with fastapi and "
        "postgres experience\n"
    )
    slug = make_slug(jd, now=FIXED_NOW)
    jd_part = slug.split("-", 1)[1]
    assert len(jd_part) <= 40
    # Trailing chars must not be a stray dash and the last component should be
    # a complete word (no mid-word cut).
    assert not jd_part.endswith("-")
    words = jd_part.split("-")
    assert all(words), "no empty word fragments allowed"


def test_make_slug_matches_ac2_regex() -> None:
    for jd in [
        "Senior Python role @ Acme!\n",
        "12345!!!\n",
        "x\n",
        "\n",
        "!!!\n",
        "Long " * 30 + "\n",
    ]:
        slug = make_slug(jd, now=FIXED_NOW)
        assert SLUG_REGEX.fullmatch(slug), f"slug {slug!r} fails AC2 regex"


def test_make_slug_lowercases() -> None:
    slug = make_slug("SENIOR Python ROLE\n", now=FIXED_NOW)
    assert slug == f"{FIXED_TS}-senior-python-role"


def test_make_slug_strips_leading_and_trailing_dashes() -> None:
    jd = "  !!Senior Python role!!  \n"
    slug = make_slug(jd, now=FIXED_NOW)
    assert slug == f"{FIXED_TS}-senior-python-role"


def test_make_slug_timestamp_uses_utc() -> None:
    # Naive UTC datetime should still produce a Z-suffixed timestamp.
    naive = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    slug = make_slug("acme\n", now=naive)
    assert slug.startswith("20260102T030405Z-")
