"""AC4 static import guardrail for `jobhunter.jd_parser` (Story 2.3, FR11).

The parse step must never touch platform-auth HTTP clients. This test reads
the source file of `jd_parser.py` and asserts that none of the forbidden HTTP
or browser-automation libraries are imported there. The test inspects only
the parser module's own import sites — what `anthropic` transitively pulls
in (it uses `httpx` internally) is out of scope per the story spec.
"""

from __future__ import annotations

from jobhunter.config import PROJECT_ROOT

JD_PARSER_PATH = PROJECT_ROOT / "src" / "jobhunter" / "jd_parser.py"


def test_jd_parser_source_file_exists() -> None:
    assert JD_PARSER_PATH.is_file(), (
        f"expected jd_parser at {JD_PARSER_PATH}, did Story 2.3 land?"
    )


def test_jd_parser_does_not_import_http_clients() -> None:
    src = JD_PARSER_PATH.read_text(encoding="utf-8")
    forbidden = [
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "import urllib",
        "from urllib",
        "import http.client",
        "from http.client",
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"jd_parser.py contains forbidden HTTP-client import `{needle}` "
            f"(FR11: the parser is text-in/struct-out, never fetches a JD)."
        )


def test_jd_parser_does_not_import_browser_automation() -> None:
    src = JD_PARSER_PATH.read_text(encoding="utf-8")
    forbidden = [
        "import selenium",
        "from selenium",
        "import playwright",
        "from playwright",
        "import puppeteer",
        "from puppeteer",
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"jd_parser.py contains forbidden browser-automation import "
            f"`{needle}` (FR11)."
        )


def test_jd_parser_does_not_reference_job_board_hostnames() -> None:
    src = JD_PARSER_PATH.read_text(encoding="utf-8").lower()
    for host in ("upwork.com", "linkedin.com", "onlinejobs.ph"):
        assert host not in src, (
            f"jd_parser.py references forbidden hostname `{host}` (FR11)."
        )
