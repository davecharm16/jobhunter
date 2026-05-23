"""Keyword-stuffing density + placement matcher (Stories 5.1 / 5.2).

Pure, rule-based check that every JD-derived must-have keyword stays under a
conservative per-keyword density / repetition ceiling on each tailored
artifact (Story 5.1) AND that the artifacts contain no "skills-dump"
paragraphs or comma-separated runs of pure JD keywords (Story 5.2). The
third drift dimension after Epic 3 (fabrication) and Epic 4
(content-loss); Story 5.3 will move thresholds to `config.yaml` + persist
the full verdict block to `package.drift.json`, and Story 5.4 will render
the UI.

This module ships the matcher logic only — no disk writes, no LLM calls
(AC8). The orchestrator in `tailoring.py` is responsible for:

1. Resolving the artifact-path dispatch table (cv.md / cover-letter.md /
   upwork-proposal.md, per Story 4.1 idiom).
2. Reading `parsed_jd_dict["must_haves"]` (a list of strings, may be empty).
3. Calling `run_keyword_stuffing_check(artifact_paths, must_haves)` to get
   the combined density + placement verdict, then folding it into
   `drift_verdicts["keyword_stuffing"]`.

Defaults are conservative (high precision): a 1.5% per-keyword density
ceiling, a 3-occurrence-per-artifact repetition ceiling, a 15-token
dump-paragraph floor with a 30% must-have-ratio ceiling, and a 4-item
comma-run floor. Story 5.3 will move these to `config.yaml` under
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
    "Paragraph",
    "compute_density",
    "count_keyword_occurrences",
    "detect_comma_runs",
    "detect_dump_paragraphs",
    "run_density_check",
    "run_keyword_stuffing_check",
    "split_paragraphs",
    "tokenize_markdown",
]


# AC5: hard-coded conservative defaults shipped as function-signature
# defaults. Story 5.3 will wire these to `config.yaml` reads under the
# top-level `keyword_stuffing` block (with per-channel overrides).
_DEFAULT_MAX_DENSITY_PCT: float = 1.5
_DEFAULT_MAX_REPETITIONS_PER_ARTIFACT: int = 3
# Story 5.2 AC4: placement defaults baked into the signature; Story 5.3
# will read them from `config.yaml` under `keyword_stuffing.*`.
_DEFAULT_DUMP_PARAGRAPH_MIN_TOKENS: int = 15
_DEFAULT_DUMP_PARAGRAPH_MAX_KEYWORD_RATIO: float = 0.30
_DEFAULT_COMMA_RUN_MIN_TOKENS: int = 4

# Excerpt length for `dump_paragraph_locations[].excerpt` per Story 5.2 AC5.
_EXCERPT_MAX_CHARS: int = 120

# A bullet-list line starts with `- `, `* `, or `<digits>. ` (ordered list).
# Used both to identify bullet blocks for paragraph splitting and to peel the
# marker so the item's text can be tokenized / comma-scanned uniformly.
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")


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

    `dump_paragraph_locations` is populated by Story 5.2's placement
    detector. Each entry is a `dict` with keys `artifact`,
    `paragraph_index`, `kind` (`"keyword_dump_paragraph"` or
    `"comma_run_violation"`), `keyword_ratio` (omitted for comma runs),
    `matched_keywords`, and `excerpt` (first 120 chars).
    """

    verdict: Literal["pass", "fail"]
    density_violations: list[DensityViolation] = field(default_factory=list)
    dump_paragraph_locations: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Paragraph:
    """One paragraph after heading/list-marker filtering (Story 5.2 AC1).

    `index` is zero-based and counts paragraphs AFTER markdown headings
    have been dropped, so a `dump_paragraph_locations[].paragraph_index`
    is the position the author sees scrolling past prose, not raw
    blank-line blocks. `tokens` is the lowercased token list produced by
    `tokenize_markdown`. `bullet_items` is the flattened list of bullet
    text (marker peeled off) when the paragraph is a markdown bullet
    block — `None` for plain prose paragraphs. The comma-run detector
    re-joins `bullet_items` so a vertical "skills list" of pure JD
    keywords is caught by the same rule that catches a comma-separated
    inline dump (AC7).
    """

    index: int
    text: str
    tokens: list[str]
    bullet_items: list[str] | None


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


def split_paragraphs(text: str) -> list[Paragraph]:
    """Split markdown *text* into `Paragraph` blocks (Story 5.2 AC1).

    Paragraphs are blank-line-delimited blocks. Markdown frontmatter and
    fenced code blocks are stripped first (consistent with
    `tokenize_markdown`); heading lines (starting with `#`) are dropped.
    A bullet-list block (consecutive lines starting with `- `, `* `, or
    `<digits>. `) is treated as a single paragraph and its flattened
    items populate `bullet_items` so the comma-run detector can scan
    across the list (AC7). The returned `index` is zero-based and reflects
    paragraph position AFTER heading filtering.
    """
    if not text:
        return []
    stripped = _FRONTMATTER_PATTERN.sub("", text, count=1)
    stripped = _CODE_FENCE_PATTERN.sub("", stripped)
    # Drop heading lines wholesale; their content is excluded from
    # paragraph indexing (consistent with `tokenize_markdown`).
    cleaned_lines = [
        line for line in stripped.splitlines()
        if not line.lstrip().startswith("#")
    ]
    paragraphs: list[Paragraph] = []
    block_lines: list[str] = []
    index = 0
    for line in cleaned_lines + [""]:  # sentinel flush
        if line.strip() == "":
            if block_lines:
                paragraph = _build_paragraph(index, block_lines)
                if paragraph is not None:
                    paragraphs.append(paragraph)
                    index += 1
                block_lines = []
            continue
        block_lines.append(line)
    return paragraphs


def _build_paragraph(index: int, lines: list[str]) -> Paragraph | None:
    """Construct a `Paragraph` from a non-empty block of lines."""
    bullet_items: list[str] = []
    all_bullets = True
    for line in lines:
        match = _BULLET_PATTERN.match(line)
        if match is None:
            all_bullets = False
            break
        bullet_items.append(match.group(1).strip())
    text = "\n".join(lines)
    tokens = tokenize_markdown(text)
    if not tokens:
        # A block with only list markers and no word content (very rare;
        # e.g. an empty bullet line) is not a meaningful paragraph.
        return None
    return Paragraph(
        index=index,
        text=text,
        tokens=tokens,
        bullet_items=bullet_items if all_bullets and bullet_items else None,
    )


def detect_dump_paragraphs(
    paragraph: Paragraph,
    must_haves_lower: set[str],
    *,
    min_tokens: int = _DEFAULT_DUMP_PARAGRAPH_MIN_TOKENS,
    max_keyword_ratio: float = _DEFAULT_DUMP_PARAGRAPH_MAX_KEYWORD_RATIO,
) -> bool:
    """Return True when *paragraph* is a "keyword dump" paragraph (AC2).

    Triggers when the paragraph's token count is at least *min_tokens*
    AND the fraction of tokens that are JD must-haves strictly exceeds
    *max_keyword_ratio*. *must_haves_lower* is the set of lowercased
    single-token JD must-haves (multi-token JD phrases are out of scope
    for this rule — see `detect_comma_runs` for the comma-list anti-
    pattern). Strict-greater matches the density rule's convention from
    Story 5.1 (exactly-at-threshold is not a breach).
    """
    total = len(paragraph.tokens)
    if total < min_tokens:
        return False
    matches = sum(1 for tok in paragraph.tokens if tok in must_haves_lower)
    return (matches / total) > max_keyword_ratio


def detect_comma_runs(
    paragraph: Paragraph,
    must_haves_lower: set[str],
    *,
    min_tokens: int = _DEFAULT_COMMA_RUN_MIN_TOKENS,
) -> list[list[str]]:
    """Return consecutive comma-separated runs of pure JD must-haves (AC3).

    For a plain prose paragraph the source string is `paragraph.text`;
    for a bullet block, `bullet_items` is joined with `", "` so a
    vertical skills list is normalized into the same comma-separated form
    (AC7). The result is a list of runs; each run is a list of the
    matched item strings (lowercased, stripped) of length >= *min_tokens*.
    An empty list means no run reached the threshold.
    """
    if paragraph.bullet_items is not None:
        source = ", ".join(paragraph.bullet_items)
    else:
        source = paragraph.text
    # Strip a trailing sentence terminator off each piece so a list that
    # ends with a period ("TypeScript, Node, Kubernetes.") still has its
    # final item recognized — authors write skills lists with terminal
    # punctuation. Leading bullet markers, surrounding whitespace, and
    # ASCII case are all normalized.
    pieces: list[str] = []
    for piece in source.split(","):
        cleaned = piece.strip()
        if cleaned.endswith((".", "!", "?", ";", ":")):
            cleaned = cleaned[:-1].rstrip()
        pieces.append(cleaned.lower())
    runs: list[list[str]] = []
    current: list[str] = []
    for piece in pieces:
        if piece and piece in must_haves_lower:
            current.append(piece)
            continue
        if len(current) >= min_tokens:
            runs.append(current)
        current = []
    if len(current) >= min_tokens:
        runs.append(current)
    return runs


def _excerpt(text: str) -> str:
    """First 120 characters of *text* for the on-disk drift report (AC5)."""
    flat = " ".join(text.split())
    return flat[:_EXCERPT_MAX_CHARS]


def _run_placement_check(
    artifact_paths: dict[str, Path],
    must_haves: list[str],
    *,
    dump_paragraph_min_tokens: int,
    dump_paragraph_max_keyword_ratio: float,
    comma_run_min_tokens: int,
) -> list[dict]:
    """Scan every artifact for dump paragraphs and comma runs (Story 5.2)."""
    if not must_haves or not artifact_paths:
        return []
    # Normalize must-haves to lowercased whole-token form. Multi-token
    # JD phrases are not eligible for the dump-paragraph rule (which
    # operates token-by-token) but their first token still wouldn't be
    # confused with the phrase — we keep only the single-token forms
    # for the dump-ratio numerator. Comma-run uses the full normalized
    # phrase since "data engineer, machine learning, ..." is a real
    # anti-pattern.
    single_token_must_haves: set[str] = set()
    phrase_must_haves: set[str] = set()
    for keyword in must_haves:
        normalized = keyword.strip().lower()
        if not normalized:
            continue
        phrase_must_haves.add(normalized)
        # Single-token form for the dump-ratio: only add if the keyword
        # tokenizes to exactly one token under the same rules as the
        # body text.
        keyword_tokens = [
            match.group(0).lower()
            for match in _TOKEN_PATTERN.finditer(normalized)
        ]
        if len(keyword_tokens) == 1:
            single_token_must_haves.add(keyword_tokens[0])

    locations: list[dict] = []
    for artifact_name, path in artifact_paths.items():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            continue
        paragraphs = split_paragraphs(text)
        for paragraph in paragraphs:
            if detect_dump_paragraphs(
                paragraph,
                single_token_must_haves,
                min_tokens=dump_paragraph_min_tokens,
                max_keyword_ratio=dump_paragraph_max_keyword_ratio,
            ):
                matched = [
                    tok
                    for tok in paragraph.tokens
                    if tok in single_token_must_haves
                ]
                ratio = round(len(matched) / len(paragraph.tokens), 4)
                locations.append(
                    {
                        "artifact": artifact_name,
                        "paragraph_index": paragraph.index,
                        "kind": "keyword_dump_paragraph",
                        "keyword_ratio": ratio,
                        "matched_keywords": _dedupe_preserve_order(matched),
                        "excerpt": _excerpt(paragraph.text),
                    }
                )
            runs = detect_comma_runs(
                paragraph,
                phrase_must_haves,
                min_tokens=comma_run_min_tokens,
            )
            for run in runs:
                if paragraph.bullet_items is not None:
                    excerpt_source = ", ".join(paragraph.bullet_items)
                else:
                    excerpt_source = paragraph.text
                locations.append(
                    {
                        "artifact": artifact_name,
                        "paragraph_index": paragraph.index,
                        "kind": "comma_run_violation",
                        "matched_keywords": _dedupe_preserve_order(run),
                        "excerpt": _excerpt(excerpt_source),
                    }
                )
    return locations


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """Stable dedupe so `matched_keywords[]` stays diff-friendly on disk."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def run_keyword_stuffing_check(
    artifact_paths: dict[str, Path],
    must_haves: list[str],
    *,
    max_density_pct: float = _DEFAULT_MAX_DENSITY_PCT,
    max_repetitions_per_artifact: int = _DEFAULT_MAX_REPETITIONS_PER_ARTIFACT,
    dump_paragraph_min_tokens: int = _DEFAULT_DUMP_PARAGRAPH_MIN_TOKENS,
    dump_paragraph_max_keyword_ratio: float = (
        _DEFAULT_DUMP_PARAGRAPH_MAX_KEYWORD_RATIO
    ),
    comma_run_min_tokens: int = _DEFAULT_COMMA_RUN_MIN_TOKENS,
) -> KeywordStuffingCheck:
    """Run density (Story 5.1) AND placement (Story 5.2) and OR-combine (AC6).

    The verdict is `"fail"` if EITHER density violations OR placement
    locations are non-empty. Both checks always run so the on-disk drift
    report (Story 5.3) carries the full picture even when one dimension
    already condemned the package.
    """
    density_check = run_density_check(
        artifact_paths,
        must_haves,
        max_density_pct=max_density_pct,
        max_repetitions_per_artifact=max_repetitions_per_artifact,
    )
    locations = _run_placement_check(
        artifact_paths,
        must_haves,
        dump_paragraph_min_tokens=dump_paragraph_min_tokens,
        dump_paragraph_max_keyword_ratio=dump_paragraph_max_keyword_ratio,
        comma_run_min_tokens=comma_run_min_tokens,
    )
    has_density = bool(density_check.density_violations)
    has_placement = bool(locations)
    verdict: Literal["pass", "fail"] = (
        "fail" if (has_density or has_placement) else "pass"
    )
    return KeywordStuffingCheck(
        verdict=verdict,
        density_violations=density_check.density_violations,
        dump_paragraph_locations=locations,
    )


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
