"""Structural matcher for the fabrication drift check (Story 3.2).

Consumes the Story-3.1 `claims.json` and the canonical CV, and emits a
`FabricationCheck` verdict whose every sourced claim carries a trace back to
the canonical-CV entry that sourced it. The matcher is purely structural —
exact and substring matching against canonical-CV text fields — and hands any
remaining unmatched claims to a `semantic_step` callable that Story 3.3 will
replace. The default `semantic_step` returns `None` (no match) so v1 is
deterministic and LLM-free.

The drift report is a top-level dict so future drift checks (Epic 4
content-loss, Epic 5 keyword-stuffing) can write sibling keys without
disturbing the fabrication block. Atomic write idiom (tmp + os.replace)
mirrors the Story 2.10 / 3.1 sidecar pattern.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from jobhunter.claim_extractor import Claim


__all__ = [
    "CanonicalEntry",
    "FabricationCheck",
    "SemanticStep",
    "Trace",
    "UnsourcedClaim",
    "iter_canonical_entries",
    "run_matcher",
    "write_drift_report",
]


# AC5: the universe of sourceable entries the matcher walks. Each entry is a
# (section, index, text) triple; the canonical-entry id is a stable hash so
# re-runs produce diffable drift files.
@dataclass(frozen=True)
class CanonicalEntry:
    """One sourceable text fragment from the canonical CV (AC5)."""

    entry_id: str
    section: str
    text: str


@dataclass(frozen=True)
class Trace:
    """Per-claim link from the tailored artifact back to the canonical CV."""

    claim_id: str
    claim_text: str
    matched_canonical_entry_id: str
    match_method: Literal["exact_string", "substring", "semantic"]
    match_score: float
    # D2: canonical CV original text the claim was matched against.
    # None only for fabricated/unsourced claims (which never produce a Trace).
    source_text: str | None = None


@dataclass(frozen=True)
class UnsourcedClaim:
    """A claim no method could source against the canonical CV (FR24)."""

    claim_id: str
    claim_text: str
    source_artifact: str
    line_number: int
    reason: str
    # D2: always null for unsourced/fabricated claims (no canonical match).
    source_text: None = None


@dataclass(frozen=True)
class FabricationCheck:
    """Top-level verdict + per-claim traces / unsourced detail (AC1)."""

    verdict: Literal["pass", "fail"]
    claims_total: int
    claims_sourced: int
    claims_unsourced: int
    traces: list[Trace] = field(default_factory=list)
    unsourced_claims: list[UnsourcedClaim] = field(default_factory=list)


# A `SemanticStep` consumes (claim, candidates) and returns either a `Trace`
# (match) or `None` (no match). Story 3.3 will replace the default no-match
# stub with an embedding-cosine / rule-based implementation.
SemanticStep = Callable[[Claim, list[CanonicalEntry]], Trace | None]


def _no_match_semantic_step(
    claim: Claim, candidates: list[CanonicalEntry]
) -> Trace | None:
    """Default semantic step for v1: always no-match (Story 3.3 replaces)."""
    return None


def _entry_id(section: str, text: str) -> str:
    """Deterministic canonical-entry id (AC5: stable across runs)."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{section}:{digest}"


def iter_canonical_entries(canonical_cv: dict[str, Any]) -> list[CanonicalEntry]:
    """Enumerate every sourceable text fragment from the canonical CV (AC5).

    Walks `work[].highlights[]`, `skills[].keywords[]`, `projects[].highlights[]`,
    `education[]` (concatenated label), plus `work[].position + name`
    (role-claim pattern) and `projects[].name` (tool/skill-claim pattern).
    Entry IDs are deterministic so the drift report diffs cleanly across runs.
    """
    entries: list[CanonicalEntry] = []

    for w_idx, work in enumerate(canonical_cv.get("work", []) or []):
        if not isinstance(work, dict):
            continue
        position = work.get("position")
        name = work.get("name")
        if isinstance(position, str) and isinstance(name, str) and position and name:
            role_text = f"{position} at {name}"
            section = f"work[{w_idx}].position+name"
            entries.append(
                CanonicalEntry(
                    entry_id=_entry_id(section, role_text),
                    section=section,
                    text=role_text,
                )
            )
        for h_idx, highlight in enumerate(work.get("highlights", []) or []):
            if not isinstance(highlight, str) or not highlight:
                continue
            section = f"work[{w_idx}].highlights[{h_idx}]"
            entries.append(
                CanonicalEntry(
                    entry_id=_entry_id(section, highlight),
                    section=section,
                    text=highlight,
                )
            )

    for s_idx, skill in enumerate(canonical_cv.get("skills", []) or []):
        if not isinstance(skill, dict):
            continue
        for k_idx, keyword in enumerate(skill.get("keywords", []) or []):
            if not isinstance(keyword, str) or not keyword:
                continue
            section = f"skills[{s_idx}].keywords[{k_idx}]"
            entries.append(
                CanonicalEntry(
                    entry_id=_entry_id(section, keyword),
                    section=section,
                    text=keyword,
                )
            )

    for p_idx, project in enumerate(canonical_cv.get("projects", []) or []):
        if not isinstance(project, dict):
            continue
        project_name = project.get("name")
        if isinstance(project_name, str) and project_name:
            section = f"projects[{p_idx}].name"
            entries.append(
                CanonicalEntry(
                    entry_id=_entry_id(section, project_name),
                    section=section,
                    text=project_name,
                )
            )
        for h_idx, highlight in enumerate(project.get("highlights", []) or []):
            if not isinstance(highlight, str) or not highlight:
                continue
            section = f"projects[{p_idx}].highlights[{h_idx}]"
            entries.append(
                CanonicalEntry(
                    entry_id=_entry_id(section, highlight),
                    section=section,
                    text=highlight,
                )
            )

    for e_idx, edu in enumerate(canonical_cv.get("education", []) or []):
        if not isinstance(edu, dict):
            continue
        parts = [
            str(edu.get("studyType", "")).strip(),
            str(edu.get("area", "")).strip(),
            str(edu.get("institution", "")).strip(),
        ]
        label = " ".join(p for p in parts if p).strip()
        if not label:
            continue
        section = f"education[{e_idx}]"
        entries.append(
            CanonicalEntry(
                entry_id=_entry_id(section, label),
                section=section,
                text=label,
            )
        )

    return entries


def _try_exact(claim: Claim, entries: list[CanonicalEntry]) -> Trace | None:
    """Case-insensitive exact match against any canonical-entry text (AC2.1)."""
    needle = claim.claim_text.strip().lower()
    if not needle:
        return None
    for entry in entries:
        if entry.text.strip().lower() == needle:
            return Trace(
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                matched_canonical_entry_id=entry.entry_id,
                match_method="exact_string",
                match_score=1.0,
                source_text=entry.text,  # D2: canonical original
            )
    return None


def _try_substring(claim: Claim, entries: list[CanonicalEntry]) -> Trace | None:
    """Bidirectional case-insensitive substring match (AC2.2)."""
    needle = claim.claim_text.strip().lower()
    if not needle:
        return None
    for entry in entries:
        haystack = entry.text.strip().lower()
        if not haystack:
            continue
        if needle in haystack or haystack in needle:
            return Trace(
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                matched_canonical_entry_id=entry.entry_id,
                match_method="substring",
                match_score=1.0,
                source_text=entry.text,  # D2: canonical original
            )
    return None


def run_matcher(
    claims: list[Claim],
    canonical_cv: dict[str, Any],
    *,
    semantic_step: SemanticStep | None = None,
) -> FabricationCheck:
    """Match every *claim* against the canonical CV; return a `FabricationCheck`.

    Match order per AC2: exact_string -> substring -> semantic_step. The
    `semantic_step` is a test seam — Story 3.3 replaces the default no-match
    stub. A claim that none of the three methods sources becomes an
    `UnsourcedClaim(reason="no_canonical_match")`.
    """
    step = semantic_step or _no_match_semantic_step
    entries = iter_canonical_entries(canonical_cv)

    traces: list[Trace] = []
    unsourced: list[UnsourcedClaim] = []

    for claim in claims:
        trace = _try_exact(claim, entries) or _try_substring(claim, entries)
        if trace is None:
            trace = step(claim, entries)
        if trace is not None:
            traces.append(trace)
        else:
            unsourced.append(
                UnsourcedClaim(
                    claim_id=claim.claim_id,
                    claim_text=claim.claim_text,
                    source_artifact=claim.source_artifact,
                    line_number=claim.line_number,
                    reason="no_canonical_match",
                )
            )

    verdict: Literal["pass", "fail"] = "fail" if unsourced else "pass"
    return FabricationCheck(
        verdict=verdict,
        claims_total=len(claims),
        claims_sourced=len(traces),
        claims_unsourced=len(unsourced),
        traces=traces,
        unsourced_claims=unsourced,
    )


def write_drift_report(out_dir: Path, check: FabricationCheck) -> Path:
    """Write `package.drift.json` atomically under *out_dir*.

    The document is a top-level dict with a single `fabrication_check` key.
    Future stories (Epic 4 content-loss, Epic 5 keyword-stuffing) write
    sibling keys; the top-level shape leaves room for them.
    """
    target = out_dir / "package.drift.json"
    tmp_path = out_dir / ".package.drift.tmp"
    payload = {"fabrication_check": dataclasses.asdict(check)}
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")
    os.replace(tmp_path, target)
    return target
