"""AC8 static import guardrail for `jobhunter.keyword_stuffing_matcher` (Story 5.1).

The keyword-stuffing density check must use ONLY tokenization + dict
lookups + arithmetic — no LLM client, no HTTP client, no embeddings.
This test reads the source file of `keyword_stuffing_matcher.py` and
asserts that none of the forbidden modules are imported there.

Counterpart to `test_jd_parser_imports.py` (Story 2.3 / FR11) and the
analogous Story 4.1 expectation that the content-loss matcher does not
reach for an LLM.
"""

from __future__ import annotations

from jobhunter.config import PROJECT_ROOT

KEYWORD_STUFFING_MATCHER_PATH = (
    PROJECT_ROOT / "src" / "jobhunter" / "keyword_stuffing_matcher.py"
)


def test_source_file_exists() -> None:
    assert KEYWORD_STUFFING_MATCHER_PATH.is_file(), (
        f"expected matcher at {KEYWORD_STUFFING_MATCHER_PATH}; "
        "did Story 5.1 land?"
    )


def test_does_not_import_llm_client() -> None:
    src = KEYWORD_STUFFING_MATCHER_PATH.read_text(encoding="utf-8")
    forbidden = [
        "import jobhunter.llm_client",
        "from jobhunter.llm_client",
        "from jobhunter import llm_client",
        "import anthropic",
        "from anthropic",
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"keyword_stuffing_matcher.py contains forbidden LLM import "
            f"`{needle}` (AC8: no LLM call from the density check)."
        )


def test_does_not_import_http_clients() -> None:
    src = KEYWORD_STUFFING_MATCHER_PATH.read_text(encoding="utf-8")
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
            f"keyword_stuffing_matcher.py contains forbidden HTTP-client "
            f"import `{needle}` (AC8)."
        )


def test_does_not_import_embeddings_libraries() -> None:
    """Story 5.3 may add per-channel overrides; v1 must stay embedding-free."""
    src = KEYWORD_STUFFING_MATCHER_PATH.read_text(encoding="utf-8")
    forbidden = [
        "import voyageai",
        "from voyageai",
        "import openai",
        "from openai",
        "import sentence_transformers",
        "from sentence_transformers",
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"keyword_stuffing_matcher.py contains forbidden embeddings "
            f"import `{needle}` (AC8)."
        )
