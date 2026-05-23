"""Keyword-stuffing density matcher (Story 5.1).

Pure, rule-based check that every JD-derived must-have keyword stays under a
conservative per-keyword density / repetition ceiling on each tailored
artifact. The third drift dimension after Epic 3 (fabrication) and Epic 4
(content-loss); Story 5.2 will extend the matcher with placement detection
(dump paragraphs + comma runs), Story 5.3 will move thresholds to
`config.yaml` + persist the full verdict block to `package.drift.json`, and
Story 5.4 will render the UI.

Story 5.1 ships the matcher logic only — no disk writes from this module, no
LLM calls (AC8). The orchestrator in `tailoring.py` is responsible for:

1. Resolving the artifact-path dispatch table (cv.md / cover-letter.md /
   upwork-proposal.md, per Story 4.1 idiom).
2. Reading `parsed_jd_dict["must_haves"]` (a list of strings, may be empty).
3. Calling `run_density_check(artifact_paths, must_haves)` to get the
   verdict, then folding it into `drift_verdicts["keyword_stuffing"]`.

Defaults are conservative (high precision) per Story 5.1 notes: a 1.5%
per-keyword density ceiling and a 3-occurrence-per-artifact repetition
ceiling. Story 5.3 will move these to `config.yaml` under
`keyword_stuffing.*` and add per-channel overrides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


__all__ = [
    "DensityViolation",
    "KeywordStuffingCheck",
    "compute_density",
    "count_keyword_occurrences",
    "run_density_check",
    "tokenize_markdown",
]


# AC5: hard-coded conservative defaults shipped as function-signature
# defaults. Story 5.3 will wire these to `config.yaml` reads under the
# top-level `keyword_stuffing` block (with per-channel overrides).
_DEFAULT_MAX_DENSITY_PCT: float = 1.5
_DEFAULT_MAX_REPETITIONS_PER_ARTIFACT: int = 3


# A token starts with an alphanumeric and may contain internal `+`, `#`,
# `-`, `.` so identifiers like "c++", "c#", "node.js", "next-gen" survive
# tokenization as single tokens. Trailing `.` / `-` (sentence punctuation
# after a word) is excluded by requiring the token to END in an
# alphanumeric, `+`, or `#` — i.e. "acme." tokenizes to "acme", but
# "node.js" stays whole because it ends in `s`. Lower-casing happens after
# the regex match.
_TOKEN_PATTERN = re.compile(
    r"[a-z0-9](?:[a-z0-9+#.\-]*[a-z0-9+#])?", re.IGNORECASE
)

# Fenced code blocks (``` ... ``` or ~~~ ... ~~~) and YAML/TOML frontmatter
# (`--- ... ---` at the very top) are stripped before tokenization so a JD
# keyword echoed in a code sample or a frontmatter `tags: [...]` line does
# not pollute the density count.
_CODE_FENCE_PATTERN = re.compile(
    r"^(```|~~~).*?(^(```|~~~).*?$|\Z)", re.MULTILINE | re.DOTALL
)
_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class DensityViolation:
    """One per-keyword threshold breach on one artifact (AC2 / AC3)."""

    keyword: str
    artifact: str
    occurrences: int
    total_tokens: int
    density_pct: float
    threshold_breached: Literal[
        "max_density_pct", "max_repetitions_per_artifact"
    ]


@dataclass(frozen=True)
class KeywordStuffingCheck:
    """Top-level verdict + per-keyword violations (AC6 / AC7).

    `dump_paragraph_locations` is empty for Story 5.1; Story 5.2 will
    populate it with paragraph-placement violations. Pre-declaring the
    field shape here prevents downstream-story conflicts.
    """

    verdict: Literal["pass", "fail"]
    density_violations: list[DensityViolation] = field(default_factory=list)
    dump_paragraph_locations: list[dict] = field(default_factory=list)


# ---- public API -----------------------------------------------------------


def tokenize_markdown(text: str) -> list[str]:
    """Tokenize markdown into a flat lowercased token list (AC1).

    Strips YAML/TOML frontmatter, fenced code blocks, and markdown-heading
    lines (lines starting with `#`) before applying the token regex. The
    regex itself splits on whitespace and most punctuation but preserves
    internal `+`, `#`, `-`, `.` so multi-character identifiers ("c++",
    "node.js", "next-gen") survive as single tokens.
    """
    if not text:
        return []
    # Strip frontmatter first so a `# tags:` line inside it cannot be
    # mistaken for a markdown heading by the subsequent line-strip.
    stripped = _FRONTMATTER_PATTERN.sub("", text, count=1)
    # Fenced code blocks (```...``` / ~~~...~~~) are dropped wholesale; a
    # JD keyword echoed in a code sample is incidental, not stuffing.
    stripped = _CODE_FENCE_PATTERN.sub("", stripped)
    # Heading lines start with `#` followed by space (ATX-style headings).
    # We drop them whole; the keyword density check measures body prose,
    # not section labels (a "TypeScript" heading is not stuffing).
    cleaned_lines = [
        line for line in stripped.splitlines()
        if not line.lstrip().startswith("#")
    ]
    cleaned = "\n".join(cleaned_lines)
    return [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(cleaned)]


def count_keyword_occurrences(
    tokens: list[str], keywords: list[str]
) -> dict[str, int]:
    """Count whole-token occurrences of each keyword in *tokens* (AC1).

    Case-insensitive whole-token match: a keyword "node" does NOT match a
    token "node.js" (they are distinct tokens after tokenization). A
    multi-token keyword like "data engineer" is matched via a sliding
    window over *tokens*, so `["i", "am", "a", "data", "engineer"]` yields
    one occurrence for "data engineer".
    """
    if not keywords or not tokens:
        return {keyword: 0 for keyword in keywords}
    counts: dict[str, int] = {}
    for keyword in keywords:
        normalized = keyword.strip().lower()
        if not normalized:
            counts[keyword] = 0
            continue
        keyword_tokens = [
            match.group(0).lower()
            for match in _TOKEN_PATTERN.finditer(normalized)
        ]
        if not keyword_tokens:
            counts[keyword] = 0
            continue
        if len(keyword_tokens) == 1:
            target = keyword_tokens[0]
            counts[keyword] = sum(1 for tok in tokens if tok == target)
            continue
        # Multi-token keyword: sliding-window equality match.
        window = len(keyword_tokens)
        hits = 0
        for start in range(len(tokens) - window + 1):
            if tokens[start:start + window] == keyword_tokens:
                hits += 1
        counts[keyword] = hits
    return counts


def compute_density(
    occurrences: dict[str, int], total_tokens: int
) -> dict[str, float]:
    """Compute per-keyword density as `(occurrences / total_tokens) * 100`.

    Returned floats are rounded to four decimal places — enough precision
    for the 1.5%-default threshold to be unambiguous in the on-disk drift
    report Story 5.3 writes, without trailing 64-bit-float noise.
    `total_tokens == 0` yields `0.0` for every keyword (no division by
    zero) so an empty artifact cannot accidentally trigger a violation.
    """
    if total_tokens <= 0:
        return {keyword: 0.0 for keyword in occurrences}
    return {
        keyword: round((count / total_tokens) * 100, 4)
        for keyword, count in occurrences.items()
    }


def run_density_check(
    artifact_paths: dict[str, Path],
    must_haves: list[str],
    *,
    max_density_pct: float = _DEFAULT_MAX_DENSITY_PCT,
    max_repetitions_per_artifact: int = _DEFAULT_MAX_REPETITIONS_PER_ARTIFACT,
) -> KeywordStuffingCheck:
    """Run the per-keyword density / repetition check across all artifacts.

    *artifact_paths* maps artifact filename (e.g. `cv.md`,
    `cover-letter.md`, `upwork-proposal.md`) to its on-disk path; missing
    files are silently dropped (matches Story 4.1's content-loss tolerance
    for an absent `upwork-proposal.md` when the JD is not Upwork). The
    check is purely rule-based — no LLM call (AC8). Per-artifact
    evaluation (AC4): a keyword's count is NOT summed across artifacts.

    AC3 tie-break: when a keyword breaches BOTH thresholds on the same
    artifact, a single violation is emitted with
    `threshold_breached="max_density_pct"` — density is checked first by
    convention so the on-disk report stays diff-stable.
    """
    if not must_haves or not artifact_paths:
        return KeywordStuffingCheck(verdict="pass")

    violations: list[DensityViolation] = []
    for artifact_name, path in artifact_paths.items():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            continue
        tokens = tokenize_markdown(text)
        total_tokens = len(tokens)
        occurrences = count_keyword_occurrences(tokens, must_haves)
        densities = compute_density(occurrences, total_tokens)
        for keyword in must_haves:
            count = occurrences.get(keyword, 0)
            if count == 0:
                continue
            density_pct = densities.get(keyword, 0.0)
            # AC3 tie-break: density is the first-checked threshold. A
            # single keyword cannot produce two violations on the same
            # artifact — the density-breach short-circuits the repetition
            # check below.
            if density_pct > max_density_pct:
                violations.append(
                    DensityViolation(
                        keyword=keyword,
                        artifact=artifact_name,
                        occurrences=count,
                        total_tokens=total_tokens,
                        density_pct=density_pct,
                        threshold_breached="max_density_pct",
                    )
                )
                continue
            if count > max_repetitions_per_artifact:
                violations.append(
                    DensityViolation(
                        keyword=keyword,
                        artifact=artifact_name,
                        occurrences=count,
                        total_tokens=total_tokens,
                        density_pct=density_pct,
                        threshold_breached="max_repetitions_per_artifact",
                    )
                )

    verdict: Literal["pass", "fail"] = "fail" if violations else "pass"
    return KeywordStuffingCheck(
        verdict=verdict,
        density_violations=violations,
    )
