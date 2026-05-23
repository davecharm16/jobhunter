"""Atomic claim extractor (Story 3.1 AC2 + AC3 + AC4).

Wraps `llm_client.extract_claims` with the typed `Claim` dataclass, the
deterministic `claim_id` hash so re-runs produce diffable `claims.json`,
and the Story-3.1-specific exceptions the orchestrator catches
(`ClaimExtractionInvalid`, `ClaimExtractionTimedOut`).

`ClaimExtractionTimedOut` extends `LLMCallTimedOut` (not bare `RuntimeError`)
so it routes through the existing `web/api.py` 502 handler for `LLMCallFailed`
— same wiring the Story 2.3 `ParseTimedOut` uses. Story 2.3 set this
precedent; matching it keeps the FastAPI surface (frozen for this story)
untouched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from jobhunter import llm_client
from jobhunter.llm_client import (
    DEFAULT_TIMEOUT_SECONDS,
    ExtractClaimsResult as _LLMExtractResult,
    LLMCallTimedOut,
    LLMResponseInvalid,
)
from jobhunter.prompts import PromptTemplate


__all__ = [
    "ALLOWED_CLAIM_TYPES",
    "Claim",
    "ClaimExtractionInvalid",
    "ClaimExtractionResult",
    "ClaimExtractionTimedOut",
    "extract_claims_from_markdown",
]


ALLOWED_CLAIM_TYPES: frozenset[str] = frozenset(
    {"role", "metric", "skill", "tool", "responsibility", "accomplishment"}
)


class ClaimExtractionInvalid(ValueError):
    """The LLM produced a response whose shape could not be coerced to claims."""


class ClaimExtractionTimedOut(LLMCallTimedOut):
    """The extraction LLM call exceeded the per-call timeout (verdict: extraction_timeout)."""


@dataclass(frozen=True)
class Claim:
    """One atomic assertion extracted from a tailored artifact."""

    claim_id: str
    claim_type: str
    claim_text: str
    source_artifact: str
    line_number: int


@dataclass(frozen=True)
class ClaimExtractionResult:
    """Typed wrapper around the LLM call: claims + token/cost accounting."""

    claims: list[Claim]
    cost_usd: Any
    input_tokens: int
    output_tokens: int


def _make_claim_id(source_artifact: str, line_number: int, claim_text: str) -> str:
    """Deterministic per-claim id so re-runs produce diffable claims.json."""
    text_digest = hashlib.sha1(claim_text.encode("utf-8")).hexdigest()[:8]
    return f"{source_artifact}:{line_number}:{text_digest}"


def _coerce_claim(raw: Any, source_artifact: str) -> Claim:
    if not isinstance(raw, dict):
        raise ClaimExtractionInvalid(
            f"claim entry must be an object, got {type(raw).__name__}"
        )
    claim_type = raw.get("claim_type")
    claim_text = raw.get("claim_text")
    line_number = raw.get("line_number")
    if not isinstance(claim_type, str) or claim_type not in ALLOWED_CLAIM_TYPES:
        raise ClaimExtractionInvalid(
            f"claim_type {claim_type!r} not in allowed set {sorted(ALLOWED_CLAIM_TYPES)}"
        )
    if not isinstance(claim_text, str) or not claim_text.strip():
        raise ClaimExtractionInvalid("claim_text missing or empty")
    if isinstance(line_number, bool) or not isinstance(line_number, int):
        raise ClaimExtractionInvalid(
            f"line_number must be an integer, got {type(line_number).__name__}"
        )
    if line_number < 1:
        raise ClaimExtractionInvalid("line_number must be >= 1")
    return Claim(
        claim_id=_make_claim_id(source_artifact, line_number, claim_text),
        claim_type=claim_type,
        claim_text=claim_text,
        source_artifact=source_artifact,
        line_number=line_number,
    )


def extract_claims_from_markdown(
    markdown_text: str,
    source_artifact: str,
    *,
    api_key: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    prompt: PromptTemplate,
    llm_extract: Any = None,
) -> ClaimExtractionResult:
    """Extract atomic claims from *markdown_text* via one LLM call.

    `llm_extract` is a test seam: a callable with the same signature as
    `llm_client.extract_claims`. In production it defaults to that function.
    """
    extractor = llm_extract or llm_client.extract_claims
    try:
        result: _LLMExtractResult = extractor(
            markdown_text,
            source_artifact,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            prompt=prompt,
        )
    except LLMCallTimedOut as exc:
        raise ClaimExtractionTimedOut(str(exc)) from exc
    except LLMResponseInvalid as exc:
        raise ClaimExtractionInvalid(str(exc)) from exc

    claims = [_coerce_claim(raw, source_artifact) for raw in result.claims]
    return ClaimExtractionResult(
        claims=claims,
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
