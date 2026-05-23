"""Structured JD parser (Story 2.3).

This module adds an LLM-driven pre-tailoring step that converts raw JD text
into a structured `ParsedJD` so every downstream check operates on stable,
inspectable data instead of re-prompting the LLM with raw text. The Anthropic
SDK call lives in `llm_client.parse_jd`; this module wraps it with the
typed `ParsedJD` dataclass and the parse-stage exceptions the orchestrator
catches (`ParsedJDInvalid`, `ParseTimedOut`).

Per FR11 the parser is text-in/struct-out — it never fetches the JD from any
job-board origin or platform-auth session. The only imports here are stdlib
plus the in-repo LLM client and prompt loader.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobhunter import llm_client
from jobhunter.llm_client import (
    DEFAULT_TIMEOUT_SECONDS,
    LLMCallTimedOut,
    LLMResponseInvalid,
    ParseResult,
)
from jobhunter.prompts import PromptTemplate


__all__ = [
    "ParseTimedOut",
    "ParsedJD",
    "ParsedJDInvalid",
    "parse_jd",
]


class ParsedJDInvalid(ValueError):
    """The LLM produced a response whose shape could not be coerced to `ParsedJD`."""


class ParseTimedOut(LLMCallTimedOut):
    """The parse-stage LLM call exceeded the per-call timeout."""


@dataclass(frozen=True)
class ParsedJD:
    must_haves: list[str]
    nice_to_haves: list[str]
    tone: str
    seniority: str
    red_flags: list[str]
    raw_text_length: int
    source_board: str = "unknown"
    signals: dict = field(default_factory=dict)


def parse_jd(
    jd_text: str,
    *,
    api_key: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    prompt: PromptTemplate,
    llm_parse: object = None,
) -> ParsedJD:
    """Parse *jd_text* into a `ParsedJD` via one LLM call.

    `llm_parse` is a test seam: a callable with the same signature as
    `llm_client.parse_jd`. In production it defaults to that function.
    """
    parser = llm_parse or llm_client.parse_jd
    try:
        result: ParseResult = parser(
            jd_text,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            prompt=prompt,
        )
    except LLMCallTimedOut as exc:
        raise ParseTimedOut(str(exc)) from exc
    except LLMResponseInvalid as exc:
        raise ParsedJDInvalid(str(exc)) from exc

    return ParsedJD(
        must_haves=list(result.must_haves),
        nice_to_haves=list(result.nice_to_haves),
        tone=result.tone,
        seniority=result.seniority,
        red_flags=list(result.red_flags),
        raw_text_length=len(jd_text),
    )
