"""Content-loss drift matcher (Story 4.1).

Pure, rule-based verifier that every high-impact canonical-CV entry relevant
to the parsed JD's `must_haves` / `nice_to_haves` either appears (substring
match against the tailored markdown artifacts) or carries an explicit logged
omission rationale in `tailoring.trace.json`. The check is the second drift
dimension after Epic 3's fabrication matcher; Story 4.2 will persist the
verdict to `package.drift.json`, Story 4.3 will wire configurable thresholds,
Story 4.4 will render the UI.

Story 4.1 ships the matcher logic only — no disk writes from this module, no
LLM calls (AC5). The orchestrator in `tailoring.py` is responsible for:

1. Writing `tailoring.trace.json` (with an initially empty `dropped_entries`).
2. Calling `iter_high_impact_relevant(canonical_cv, parsed_jd_dict)` to build
   the must-appear set.
3. Calling `run_check(entries, artifact_paths, dropped_trace)` to get the
   verdict, then folding it into `drift_verdicts["content_loss"]`.

Defaults are conservative (high recall) per Story 4.1 notes: `tag_overlap_min=1`
flags any single-tag overlap as relevant, and `presence_matcher="substring"`
requires concrete textual presence. Story 4.3 will move these to `config.yaml`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal


if TYPE_CHECKING:
    from jobhunter.yaml_config import ContentLossConfig


__all__ = [
    "EmbeddingMatcherUnavailable",
    "VALID_DROP_REASONS",
    "ContentLossCheck",
    "DroppedEntry",
    "HighImpactEntry",
    "PreservedEntry",
    "iter_high_impact_relevant",
    "run_check",
]


class EmbeddingMatcherUnavailable(ValueError):
    """Raised when embedding_distance / semantic mode is selected but no embeddings client is wired (Story 4.3 AC2)."""

    # TODO(embedding-cap-check): when an embeddings client lands in a future
    # story (voyageai / openai / local sentence-transformers), the per-call
    # cost-cap check (NFR15, FR43) MUST run BEFORE the embeddings call is
    # attempted. The v1 raise sits before any client is constructed, so
    # cost-cap is moot today; this comment exists so future-Dave doesn't
    # silently bypass NFR15 when wiring the real path.


# Enumerated set of drop-reason codes recognised as logged-rationale drops
# (AC3). Hard-coded for Story 4.1; Story 4.3 will move this to `config.yaml`
# under `drift.content_loss.reason_codes` so new codes can be added without
# a code change.
VALID_DROP_REASONS: frozenset[str] = frozenset({"irrelevant_to_jd"})


# Conservative high-recall default per AC1 notes: a single overlapping tag
# is enough to flag an entry as relevant. Story 4.3 will move this to yaml.
_TAG_OVERLAP_MIN: int = 1

# Section walk order matches `canonical_cv.high_impact_entries` (FR3) so the
# index portion of each entry_id is stable across the two projections.
_HIGH_IMPACT_SECTIONS: tuple[str, ...] = ("work", "projects", "skills")


@dataclass(frozen=True)
class HighImpactEntry:
    """One high-impact canonical-CV entry projected for the content-loss check."""

    entry_id: str
    section: str
    primary_text: str
    tags: list[str] = field(default_factory=list)
    jd_requirements_matched: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreservedEntry:
    """A must-appear entry confirmed present in at least one tailored artifact."""

    entry_id: str
    section: str
    matched_in: list[str]
    match_type: Literal["substring", "semantic"]


@dataclass(frozen=True)
class DroppedEntry:
    """A must-appear entry that is absent from every tailored artifact."""

    entry_id: str
    section: str
    primary_text: str
    jd_requirements_addressed: list[str]
    reason: Literal["irrelevant_to_jd", "silently_lost"]


@dataclass(frozen=True)
class ContentLossCheck:
    """Top-level verdict + preserved / dropped detail for one pipeline run."""

    verdict: Literal["pass", "fail"]
    preserved_entries: list[PreservedEntry] = field(default_factory=list)
    dropped_entries: list[DroppedEntry] = field(default_factory=list)


# ---- public projection ----------------------------------------------------


def iter_high_impact_relevant(
    canonical_cv: dict[str, Any],
    parsed_jd: dict[str, Any],
    config: "ContentLossConfig | None" = None,
) -> list[HighImpactEntry]:
    """Project high-impact entries relevant to the JD's must-haves / nice-to-haves (AC1).

    Walks `work`, `projects`, `skills` in the order `high_impact_entries`
    walks them (FR3) so each entry_id's index portion is stable. Relevance
    dispatch is config-driven (Story 4.3): default `tag_overlap` uses an
    integer-count threshold; `keyword_overlap` falls back to a Jaccard-ish
    token overlap on the primary text; `embedding_distance` raises
    `EmbeddingMatcherUnavailable` since v1 has no embeddings client.
    No LLM call when default (AC5).
    """
    relevance_matcher = config.relevance_matcher if config is not None else "tag_overlap"
    tag_overlap_min = config.tag_overlap_min if config is not None else _TAG_OVERLAP_MIN
    keyword_overlap_pct = (
        config.keyword_overlap_pct if config is not None else 0.20
    )

    if relevance_matcher == "embedding_distance":
        raise EmbeddingMatcherUnavailable(
            "embedding matcher selected but no embeddings client configured"
        )

    jd_requirements_lower = _normalize_requirements(parsed_jd)
    jd_keyword_set = (
        _tokenize(" ".join(jd_requirements_lower))
        if relevance_matcher == "keyword_overlap"
        else None
    )
    relevant: list[HighImpactEntry] = []

    for section in _HIGH_IMPACT_SECTIONS:
        for index, entry in enumerate(canonical_cv.get(section, []) or []):
            if not isinstance(entry, dict):
                continue
            if entry.get("highImpact") is not True:
                continue
            tags = _coerce_string_list(entry.get("tags"))
            overlap = _tag_overlap(tags, jd_requirements_lower)

            primary_text = _build_primary_text(section, entry)
            if not primary_text:
                continue

            if relevance_matcher == "tag_overlap":
                if len(overlap) < tag_overlap_min:
                    continue
            else:  # keyword_overlap
                entry_tokens = _tokenize(primary_text)
                if not entry_tokens or not jd_keyword_set:
                    continue
                shared = entry_tokens & jd_keyword_set
                ratio = len(shared) / max(len(entry_tokens), 1)
                if ratio < keyword_overlap_pct:
                    continue

            relevant.append(
                HighImpactEntry(
                    entry_id=_entry_id(section, index, primary_text),
                    section=section,
                    primary_text=primary_text,
                    tags=list(tags),
                    jd_requirements_matched=overlap,
                )
            )
    return relevant


def _tokenize(text: str) -> set[str]:
    """Lower-cased alphanumeric word set used by the keyword_overlap matcher."""
    return {tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if len(tok) > 1}


# ---- public check ---------------------------------------------------------


def run_check(
    high_impact_entries: list[HighImpactEntry],
    artifact_paths: dict[str, Path],
    dropped_trace: list[dict[str, Any]],
    config: "ContentLossConfig | None" = None,
) -> ContentLossCheck:
    """Verify every must-appear entry is preserved or has a logged drop rationale.

    *artifact_paths* maps artifact name (e.g. `cv.md`, `cover-letter.md`,
    `upwork-proposal.md`) to its on-disk path. *dropped_trace* is the parsed
    `tailoring.trace.json` `dropped_entries[]` list (may be empty or absent —
    callers pass `[]` when the file is missing). The check is purely
    rule-based — no LLM call (AC5).

    Presence-matcher dispatch (Story 4.3): default `substring` is unchanged
    from Story 4.1; `semantic` raises `EmbeddingMatcherUnavailable` (no
    embeddings client in v1).
    """
    presence_matcher = config.presence_matcher if config is not None else "substring"
    if presence_matcher == "semantic":
        raise EmbeddingMatcherUnavailable(
            "embedding matcher selected but no embeddings client configured"
        )

    artifact_texts = _read_artifact_texts(artifact_paths)
    trace_reasons = _index_trace_reasons(dropped_trace)

    preserved: list[PreservedEntry] = []
    dropped: list[DroppedEntry] = []

    for entry in high_impact_entries:
        matched_in = _find_matched_artifacts(entry, artifact_texts)
        if matched_in:
            preserved.append(
                PreservedEntry(
                    entry_id=entry.entry_id,
                    section=entry.section,
                    matched_in=matched_in,
                    match_type="substring",
                )
            )
            continue
        # Absent from every artifact — fall through to the trace check.
        reason_code = trace_reasons.get(entry.entry_id)
        reason: Literal["irrelevant_to_jd", "silently_lost"]
        if reason_code in VALID_DROP_REASONS:
            # AC3: an explicit, recognised rationale spares the entry from
            # contributing to a fail. The mypy-narrow is safe because the
            # membership test above guarantees `reason_code` is in the set.
            reason = "irrelevant_to_jd"  # type: ignore[assignment]
        else:
            # Includes: trace entry missing, `reason` key missing, unknown
            # reason string (AC3 "unknown reason codes" path).
            reason = "silently_lost"
        dropped.append(
            DroppedEntry(
                entry_id=entry.entry_id,
                section=entry.section,
                primary_text=entry.primary_text,
                jd_requirements_addressed=list(entry.jd_requirements_matched),
                reason=reason,
            )
        )

    has_silent_loss = any(d.reason == "silently_lost" for d in dropped)
    verdict: Literal["pass", "fail"] = "fail" if has_silent_loss else "pass"
    return ContentLossCheck(
        verdict=verdict,
        preserved_entries=preserved,
        dropped_entries=dropped,
    )


# ---- internal helpers -----------------------------------------------------


def _entry_id(section: str, index: int, primary_text: str) -> str:
    """Deterministic high-impact-entry id (matches Story 3.2's canonical-entry id idiom)."""
    digest = hashlib.sha1(primary_text.encode("utf-8")).hexdigest()[:8]
    return f"{section}[{index}]:{digest}"


def _normalize_requirements(parsed_jd: dict[str, Any]) -> list[str]:
    """Concatenate must_haves + nice_to_haves and lower-strip every token."""
    must_haves = _coerce_string_list(parsed_jd.get("must_haves"))
    nice_to_haves = _coerce_string_list(parsed_jd.get("nice_to_haves"))
    return [item.strip().lower() for item in must_haves + nice_to_haves if item.strip()]


def _coerce_string_list(value: Any) -> list[str]:
    """Best-effort coercion to a list of strings; non-strings are dropped."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _tag_overlap(tags: list[str], jd_requirements_lower: list[str]) -> list[str]:
    """Return the JD requirement strings (original casing) that overlap *tags*.

    Comparison is lower/strip-normalised on both sides; the returned list
    carries the JD-side string (so `jd_requirements_addressed` in the drift
    report matches the JD parser's `must_haves` / `nice_to_haves` arrays
    verbatim — see Story 4.2 AC3).
    """
    if not tags or not jd_requirements_lower:
        return []
    tag_set = {tag.strip().lower() for tag in tags if tag.strip()}
    return [requirement for requirement in jd_requirements_lower if requirement in tag_set]


def _build_primary_text(section: str, entry: dict[str, Any]) -> str:
    """Project a single primary-text string per section per AC2.

    * `work` -> `position + " at " + name` + joined highlights.
    * `projects` -> `name` + joined highlights.
    * `skills` -> `name` + joined keywords.

    The primary text is the substrate for the AC2 substring presence scan; it
    is NOT used for tag-overlap relevance (which reads `entry.tags` directly).
    """
    if section == "work":
        return _project_work(entry)
    if section == "projects":
        return _project_project(entry)
    if section == "skills":
        return _project_skill(entry)
    return ""


def _project_work(entry: dict[str, Any]) -> str:
    position = _coerce_string(entry.get("position"))
    name = _coerce_string(entry.get("name"))
    highlights = [h for h in _coerce_string_list(entry.get("highlights")) if h.strip()]
    if position and name:
        prefix = f"{position} at {name}"
    elif position:
        prefix = position
    elif name:
        prefix = name
    else:
        prefix = ""
    if highlights:
        joined = " | ".join(highlights)
        return f"{prefix} | {joined}" if prefix else joined
    return prefix


def _project_project(entry: dict[str, Any]) -> str:
    name = _coerce_string(entry.get("name"))
    highlights = [h for h in _coerce_string_list(entry.get("highlights")) if h.strip()]
    if highlights:
        joined = " | ".join(highlights)
        return f"{name} | {joined}" if name else joined
    return name


def _project_skill(entry: dict[str, Any]) -> str:
    name = _coerce_string(entry.get("name"))
    keywords = [k for k in _coerce_string_list(entry.get("keywords")) if k.strip()]
    if keywords:
        joined = " | ".join(keywords)
        return f"{name} | {joined}" if name else joined
    return name


def _coerce_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _entry_match_chunks(entry: HighImpactEntry) -> list[str]:
    """Split a high-impact entry's primary_text into substring-match chunks.

    A chunk-match against any artifact counts as presence (AC2). Splitting on
    the ` | ` separator that `_build_primary_text` introduces gives the
    matcher per-highlight / per-keyword granularity. Single-token chunks
    shorter than 3 characters (e.g. "n8n") are still allowed because skill
    keywords intentionally include short identifiers.
    """
    chunks = [chunk.strip() for chunk in entry.primary_text.split("|") if chunk.strip()]
    # Drop chunks that are empty after stripping; preserve case-sensitive
    # original text — the comparison itself lower-cases both sides.
    return [chunk for chunk in chunks if chunk]


def _find_matched_artifacts(
    entry: HighImpactEntry, artifact_texts: dict[str, str]
) -> list[str]:
    """Return artifact names where any chunk of *entry.primary_text* substring-matches.

    Case-insensitive matching. The returned list preserves the dict iteration
    order so the on-disk drift report is diff-stable across runs (Python 3.7+
    dict ordering is insertion-stable; callers feed `artifact_paths` in a
    fixed cv -> cover-letter -> upwork-proposal order).
    """
    chunks_lower = [chunk.lower() for chunk in _entry_match_chunks(entry)]
    if not chunks_lower:
        return []
    matched: list[str] = []
    for artifact_name, text in artifact_texts.items():
        haystack = text.lower()
        if not haystack:
            continue
        if any(chunk in haystack for chunk in chunks_lower):
            matched.append(artifact_name)
    return matched


def _read_artifact_texts(artifact_paths: dict[str, Path]) -> dict[str, str]:
    """Read each artifact file once; missing files are silently dropped.

    The matcher tolerates a missing file (e.g. `upwork-proposal.md` absent
    when the source-board is not Upwork) — only the artifacts actually
    present can be scanned, so the dict shrinks accordingly.
    """
    texts: dict[str, str] = {}
    for artifact_name, path in artifact_paths.items():
        try:
            texts[artifact_name] = path.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            # AC2 tolerates missing artifacts; the entry simply has fewer
            # places to look. Verdict pivots on what IS found, not what's
            # missing in the artifact set.
            continue
    return texts


def _index_trace_reasons(dropped_trace: list[dict[str, Any]]) -> dict[str, str]:
    """Index `tailoring.trace.json`'s `dropped_entries[]` by entry_id (AC3).

    Trace entries missing the `entry_id` key are skipped (AC3 "unknown reason
    codes are treated as silent drops" — a missing entry_id is functionally
    the same: the matcher has no way to associate the rationale with a
    specific high-impact entry, so the entry stays in the silent-loss bucket).
    Trace entries with a missing or non-string `reason` value are recorded as
    the empty string so `run_check`'s membership test against
    `VALID_DROP_REASONS` fails closed and the entry remains a silent loss.
    """
    reasons: dict[str, str] = {}
    if not isinstance(dropped_trace, list):
        return reasons
    for item in dropped_trace:
        if not isinstance(item, dict):
            continue
        entry_id = item.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        reason = item.get("reason")
        reasons[entry_id] = reason if isinstance(reason, str) else ""
    return reasons
