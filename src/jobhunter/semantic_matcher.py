"""Semantic-equivalence step for the fabrication drift check (Story 3.3).

Slot-in replacement for Story 3.2's no-match `semantic_step` stub. Tolerates
honest paraphrase ("led the team" -> "led the engineering team") while
rejecting embellishment ("led the team" -> "led a 3-person engineering
team") via a numeric-quantifier guard.

Two configurable similarity methods:
- `rule_based` (default in v1) - Jaccard over lowercased, stemmed tokens.
  Deterministic, dependency-free, observable scores. Default threshold 0.65.
- `embedding_cosine` - reserved for a future story; raises
  `NotImplementedError` in v1 because Anthropic's SDK does not currently
  expose an embeddings endpoint. The upgrade path is documented in
  `_bmad-output/decisions/llm-provider.md`.

Because `jobhunter.fabrication_matcher.run_matcher` is frozen for Story 3.3,
the rejection-with-reason signal (`semantic_below_threshold (...)`,
`quantifier_not_in_source (...)`) cannot be returned through the
`semantic_step` Trace | None contract. Instead the step records each
rejected claim's reason in a `rejection_reasons` dict the caller passes in;
the orchestrator (`tailoring._run_fabrication_matcher`) post-processes the
resulting `FabricationCheck` to upgrade the generic `no_canonical_match`
reason to the specific Story-3.3 reason.

# TODO(hybrid-fallback): PRD risk-mitigation calls out an LLM-as-judge
# fallback for skill/tool claims after exact + substring + semantic all fail.
# Not implemented in v1 (AC4) - the claim fails cleanly. Revisit if real-use
# false-positive rate on skill/tool claims exceeds ~5%.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from jobhunter.claim_extractor import Claim
from jobhunter.fabrication_matcher import CanonicalEntry, Trace


__all__ = [
    "SemanticMatch",
    "SemanticStepCallable",
    "detect_quantifier_mismatch",
    "embedding_cosine_similarity",
    "make_semantic_step",
    "rule_based_similarity",
]


# Suffixes stripped by the in-house stemmer. Order matters: longest first so
# "running" -> "runn" -> "runn" (not "runn" -> "runnin"). Deterministic and
# dependency-free per the style constraints.
_STEM_SUFFIXES: tuple[str, ...] = ("ing", "es", "ed", "ly", "s")

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9-]*")

# Tiny stopword set so generic determiners and articles do not inflate
# Jaccard scores between unrelated phrases. Mirrors the
# `_QUESTION_STOPWORDS` shape in `tailoring.py` (intentionally compact - the
# bigger the list, the more the matcher behaves like a hand-tuned model).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "of",
        "on", "or", "the", "to", "with",
    }
)


@dataclass(frozen=True)
class SemanticMatch:
    """Best-candidate semantic match for a single claim."""

    canonical_entry_id: str
    score: float


# Signature matches `fabrication_matcher.SemanticStep`.
SemanticStepCallable = Callable[[Claim, list[CanonicalEntry]], Trace | None]


def _stem(token: str) -> str:
    """Strip a single common English suffix from *token* (deterministic).

    The stemmer is intentionally lossy and dependency-free: it strips the
    first matching suffix in `_STEM_SUFFIXES` and stops. Tokens shorter
    than 4 chars are returned unchanged so "is" / "as" do not collapse.
    """
    lowered = token.lower()
    if len(lowered) < 4:
        return lowered
    for suffix in _STEM_SUFFIXES:
        if lowered.endswith(suffix) and len(lowered) - len(suffix) >= 3:
            return lowered[: -len(suffix)]
    return lowered


def _tokenize(text: str) -> set[str]:
    """Split *text* into stemmed, lowercased, stopword-filtered tokens."""
    raw = _TOKEN_PATTERN.findall(text)
    stems = {_stem(t) for t in raw if t.lower() not in _STOPWORDS}
    return {s for s in stems if s}


def rule_based_similarity(claim_text: str, canonical_entry_text: str) -> float:
    """Jaccard similarity over stemmed, lowercased tokens (AC1 rule_based)."""
    claim_tokens = _tokenize(claim_text)
    entry_tokens = _tokenize(canonical_entry_text)
    if not claim_tokens or not entry_tokens:
        return 0.0
    intersection = claim_tokens & entry_tokens
    union = claim_tokens | entry_tokens
    return len(intersection) / len(union)


def embedding_cosine_similarity(
    claim_text: str,
    canonical_entry_text: str,
    *,
    api_key: str | None = None,
) -> float:
    """Embedding-cosine similarity (AC1 `embedding_cosine`) - not in v1.

    Anthropic's Python SDK does not currently expose an embeddings endpoint
    (only message completions), so the locked-in LLM provider cannot back
    this method. Wiring it would require a separate embeddings provider
    dependency (voyageai / openai / local sentence-transformers) which the
    v1 dep budget does not include. See
    `_bmad-output/decisions/llm-provider.md` "Story 3.3: Semantic
    Equivalence" for the upgrade path.
    """
    raise NotImplementedError(
        "embedding_cosine requires a separate embeddings provider "
        "(voyageai/openai/local sentence-transformers); not wired in v1 - "
        "Story 3.3 ships rule_based as the v1 default. "
        "See _bmad-output/decisions/llm-provider.md for the upgrade path."
    )


# Quantifier regexes for the embellishment guard (AC3). Each pattern captures
# a tokenizable substring; the guard checks that every captured substring
# from `claim_text` appears verbatim (case-insensitive) in
# `matched_canonical_text`. Pattern order is irrelevant since we iterate all.
_QUANTIFIER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\$\d+(?:[,.]\d+)*[kKmMbB]?"),                # $250, $1,200, $5k, $2M
    re.compile(r"\d+(?:[,.]\d+)*\s*%"),                       # 99%, 12.5 %
    re.compile(r"\d+-person"),                                # 3-person
    re.compile(r"\d+-engineer"),                              # 5-engineer
    re.compile(r"\d+x"),                                      # 10x, 99x
    re.compile(r"\d+(?:[,.]\d+)?\s*years?"),                  # 5 years, 1 year
    re.compile(r"\d+\s*people"),                              # 47 people
    re.compile(r"\d+\s*engineers?"),                          # 5 engineers
    re.compile(r"\d+\s*reports?"),                            # 10 reports
    re.compile(r"\d+(?:[,.]\d+)*"),                           # bare numbers fallback
)


def detect_quantifier_mismatch(
    claim_text: str, matched_canonical_text: str
) -> str | None:
    """Return the first quantifier in *claim_text* not present in *matched_canonical_text* (AC3).

    Walks `_QUANTIFIER_PATTERNS` against the claim; for every match,
    verifies that the matched token (case-insensitive) appears in the
    canonical text. Returns the first offending token, or `None` if every
    quantifier in the claim is sourced.
    """
    if not claim_text:
        return None
    haystack = matched_canonical_text.lower()
    seen: set[str] = set()
    for pattern in _QUANTIFIER_PATTERNS:
        for raw in pattern.findall(claim_text):
            token = raw.strip()
            if not token:
                continue
            normalized = token.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            if normalized not in haystack:
                return token
    return None


def make_semantic_step(
    method: str,
    threshold: float,
    *,
    api_key: str | None = None,
    rejection_reasons: dict[str, str] | None = None,
) -> SemanticStepCallable:
    """Return a `SemanticStep` callable wired for `method` at `threshold` (AC1).

    The returned callable iterates every canonical entry, scores it under
    *method*, and returns a `Trace(match_method="semantic")` when the
    highest-scoring entry passes both the threshold (AC2) and the
    quantifier guard (AC3). On rejection it returns `None` and - if
    *rejection_reasons* is provided - records the specific reason keyed by
    `claim_id` so the orchestrator can upgrade the generic
    `no_canonical_match` reason emitted by `run_matcher`.
    """
    if method == "embedding_cosine":
        def _scorer(a: str, b: str) -> float:
            return embedding_cosine_similarity(a, b, api_key=api_key)
    elif method == "rule_based":
        def _scorer(a: str, b: str) -> float:
            return rule_based_similarity(a, b)
    else:
        raise ValueError(
            f"unknown semantic_method: {method!r} (expected 'rule_based' or "
            f"'embedding_cosine')"
        )

    def semantic_step(
        claim: Claim, candidates: list[CanonicalEntry]
    ) -> Trace | None:
        if not candidates:
            return None
        best: tuple[float, CanonicalEntry] | None = None
        for entry in candidates:
            score = _scorer(claim.claim_text, entry.text)
            if best is None or score > best[0]:
                best = (score, entry)
        assert best is not None
        best_score, best_entry = best

        if best_score < threshold:
            if rejection_reasons is not None:
                rejection_reasons[claim.claim_id] = (
                    f"semantic_below_threshold (score={_fmt_score(best_score)}, "
                    f"threshold={_fmt_score(threshold)})"
                )
            return None

        offending = detect_quantifier_mismatch(claim.claim_text, best_entry.text)
        if offending is not None:
            if rejection_reasons is not None:
                rejection_reasons[claim.claim_id] = (
                    f"quantifier_not_in_source (quantifier={offending})"
                )
            return None

        return Trace(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            matched_canonical_entry_id=best_entry.entry_id,
            match_method="semantic",
            match_score=round(best_score, 4),
            source_text=best_entry.text,  # D2: canonical original
        )

    return semantic_step


def _fmt_score(value: float) -> str:
    """Format a similarity score for inclusion in a reason string."""
    return f"{value:.4f}"
