"""Unit tests for `jobhunter.keyword_stuffing_matcher` (Story 5.1 AC1-AC5, AC7).

Mirrors `test_content_loss_matcher.py` patterns: pure-function assertions,
frozen dataclasses, deterministic results, no LLM stubs (AC8 is "no LLM
call"). The matcher consumes only:

* a dict of artifact-filename -> on-disk Path
* a `must_haves: list[str]` from the parsed JD
* (optional) configurable thresholds (defaulted in the signature)
"""

from __future__ import annotations

from pathlib import Path

from jobhunter.keyword_stuffing_matcher import (
    DensityViolation,
    KeywordStuffingCheck,
    compute_density,
    count_keyword_occurrences,
    run_density_check,
    tokenize_markdown,
)


# ---- helpers --------------------------------------------------------------


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# ---- AC1: tokenization ----------------------------------------------------


class TestTokenizeMarkdown:
    """AC1 — whitespace+punctuation split, lowercased, markdown-aware strip."""

    def test_simple_prose_splits_on_whitespace(self) -> None:
        text = "I built a TypeScript service for Acme."
        tokens = tokenize_markdown(text)
        assert tokens == ["i", "built", "a", "typescript", "service", "for", "acme"]

    def test_punctuation_is_dropped(self) -> None:
        text = "Python, FastAPI; Docker — Kubernetes!"
        tokens = tokenize_markdown(text)
        assert tokens == ["python", "fastapi", "docker", "kubernetes"]

    def test_lowercases_all_tokens(self) -> None:
        text = "Python PYTHON Python"
        tokens = tokenize_markdown(text)
        assert tokens == ["python", "python", "python"]

    def test_strips_yaml_frontmatter(self) -> None:
        text = "---\ntitle: CV\ntags: [python, fastapi]\n---\nReal body here.\n"
        tokens = tokenize_markdown(text)
        # Frontmatter must NOT contribute to the token list.
        assert "title" not in tokens
        assert "fastapi" not in tokens
        assert tokens == ["real", "body", "here"]

    def test_strips_markdown_headings(self) -> None:
        text = "# Python heading\n\nbody python here\n"
        tokens = tokenize_markdown(text)
        # Heading line is dropped wholesale; only body tokens survive.
        assert tokens == ["body", "python", "here"]

    def test_strips_code_fences(self) -> None:
        text = "Some prose\n\n```\npython python python\n```\n\nmore prose\n"
        tokens = tokenize_markdown(text)
        assert "python" not in tokens
        assert tokens == ["some", "prose", "more", "prose"]

    def test_empty_string_returns_empty_list(self) -> None:
        assert tokenize_markdown("") == []

    def test_preserves_compound_identifiers(self) -> None:
        # "node.js" and "c++" survive as single tokens (engineers actually
        # write these); the regex preserves internal `+`, `#`, `.`, `-`.
        text = "We use node.js and c++ daily."
        tokens = tokenize_markdown(text)
        assert "node.js" in tokens
        assert "c++" in tokens


# ---- AC1: count keyword occurrences ---------------------------------------


class TestCountKeywordOccurrences:
    """AC1 — case-insensitive whole-token match; sliding window for phrases."""

    def test_single_token_keyword_counted(self) -> None:
        tokens = ["i", "love", "python", "but", "python", "is", "slow"]
        counts = count_keyword_occurrences(tokens, ["python"])
        assert counts == {"python": 2}

    def test_match_is_case_insensitive(self) -> None:
        tokens = tokenize_markdown("Python python PYTHON")
        counts = count_keyword_occurrences(tokens, ["Python"])
        assert counts == {"Python": 3}

    def test_whole_token_only(self) -> None:
        # "node" must NOT match the token "node.js" — they are distinct
        # tokens after tokenization.
        tokens = tokenize_markdown("I use node.js and Node together.")
        counts = count_keyword_occurrences(tokens, ["node"])
        assert counts == {"node": 1}

    def test_multi_token_keyword_via_sliding_window(self) -> None:
        tokens = tokenize_markdown("I am a data engineer at a data engineer shop.")
        counts = count_keyword_occurrences(tokens, ["data engineer"])
        assert counts == {"data engineer": 2}

    def test_zero_count_when_keyword_absent(self) -> None:
        tokens = ["python", "rust"]
        counts = count_keyword_occurrences(tokens, ["haskell"])
        assert counts == {"haskell": 0}

    def test_empty_keywords_returns_empty_dict(self) -> None:
        assert count_keyword_occurrences(["a", "b"], []) == {}

    def test_empty_tokens_returns_zero_for_each_keyword(self) -> None:
        counts = count_keyword_occurrences([], ["python", "rust"])
        assert counts == {"python": 0, "rust": 0}

    def test_blank_keyword_string_is_zero(self) -> None:
        counts = count_keyword_occurrences(["python"], ["", "  "])
        assert counts == {"": 0, "  ": 0}


# ---- AC1: density computation --------------------------------------------


class TestComputeDensity:
    """AC1 — `(occurrences / total_tokens) * 100`, rounded to four decimals."""

    def test_basic_density(self) -> None:
        densities = compute_density({"python": 3}, total_tokens=100)
        assert densities == {"python": 3.0}

    def test_rounds_to_four_decimals(self) -> None:
        # 1 / 7 * 100 = 14.285714... → 14.2857.
        densities = compute_density({"python": 1}, total_tokens=7)
        assert densities == {"python": 14.2857}

    def test_zero_total_tokens_yields_zero_density(self) -> None:
        densities = compute_density({"python": 5}, total_tokens=0)
        assert densities == {"python": 0.0}

    def test_zero_occurrences_yields_zero_density(self) -> None:
        densities = compute_density({"python": 0}, total_tokens=100)
        assert densities == {"python": 0.0}


# ---- AC2 + AC3: per-keyword threshold violations --------------------------


class TestDensityViolations:
    """AC2 — `density > max_density_pct` flags the keyword.
    AC3 — `occurrences > max_repetitions_per_artifact` flags the keyword.
    """

    def test_density_breach_emits_violation(self, tmp_path: Path) -> None:
        # 5 occurrences in a 100-token doc = 5% density; with default 1.5%
        # ceiling that's a clear breach.
        words = ["filler"] * 95 + ["python"] * 5
        body = " ".join(words) + "\n"
        cv_path = _write(tmp_path, "cv.md", body)

        check = run_density_check({"cv.md": cv_path}, ["python"])

        assert check.verdict == "fail"
        assert len(check.density_violations) == 1
        v = check.density_violations[0]
        assert v.keyword == "python"
        assert v.artifact == "cv.md"
        assert v.occurrences == 5
        assert v.total_tokens == 100
        assert v.density_pct == 5.0
        assert v.threshold_breached == "max_density_pct"

    def test_repetition_breach_only_emits_repetition_violation(
        self, tmp_path: Path
    ) -> None:
        # 4 occurrences in a 1000-token doc = 0.4% density (under 1.5%
        # default) but 4 > 3 default repetition ceiling -> repetition
        # breach only.
        words = ["filler"] * 996 + ["python"] * 4
        body = " ".join(words) + "\n"
        cv_path = _write(tmp_path, "cv.md", body)

        check = run_density_check({"cv.md": cv_path}, ["python"])

        assert check.verdict == "fail"
        assert len(check.density_violations) == 1
        v = check.density_violations[0]
        assert v.threshold_breached == "max_repetitions_per_artifact"
        assert v.occurrences == 4

    def test_both_thresholds_breached_emits_single_density_violation(
        self, tmp_path: Path
    ) -> None:
        # AC3 tie-break: a keyword that breaches BOTH thresholds on the
        # same artifact emits ONE violation with `threshold_breached =
        # "max_density_pct"` (density is checked first by convention).
        # 6 occurrences in a 100-token doc = 6% density AND 6 > 3 reps.
        words = ["filler"] * 94 + ["python"] * 6
        body = " ".join(words) + "\n"
        cv_path = _write(tmp_path, "cv.md", body)

        check = run_density_check({"cv.md": cv_path}, ["python"])

        # Single violation, density branch wins.
        assert len(check.density_violations) == 1
        assert check.density_violations[0].threshold_breached == "max_density_pct"

    def test_exactly_at_threshold_is_not_a_breach(self, tmp_path: Path) -> None:
        # Exactly 3 occurrences (the default repetition ceiling) and
        # exactly 1.5% density should NOT breach — the spec uses strict
        # inequality (`>`).
        # 3 / 200 * 100 = 1.5% exactly.
        words = ["filler"] * 197 + ["python"] * 3
        body = " ".join(words) + "\n"
        cv_path = _write(tmp_path, "cv.md", body)

        check = run_density_check({"cv.md": cv_path}, ["python"])

        assert check.verdict == "pass"
        assert check.density_violations == []

    def test_custom_thresholds_override_defaults(self, tmp_path: Path) -> None:
        # With a tighter 0.5% ceiling, 1% density should fail.
        words = ["filler"] * 99 + ["python"]
        body = " ".join(words) + "\n"
        cv_path = _write(tmp_path, "cv.md", body)

        check = run_density_check(
            {"cv.md": cv_path},
            ["python"],
            max_density_pct=0.5,
            max_repetitions_per_artifact=999,
        )

        assert check.verdict == "fail"
        assert check.density_violations[0].threshold_breached == "max_density_pct"


# ---- AC4: per-artifact evaluation (not summed) ----------------------------


class TestPerArtifactEvaluation:
    """AC4 — thresholds are evaluated per artifact, not summed across files."""

    def test_two_per_artifact_below_threshold_does_not_sum(
        self, tmp_path: Path
    ) -> None:
        # 2 occurrences in cv.md + 2 in cover-letter.md. Default reps
        # ceiling is 3 — each file is under, so combined they must NOT
        # produce a violation (AC4).
        cv_body = " ".join(["filler"] * 998 + ["python"] * 2) + "\n"
        cover_body = " ".join(["filler"] * 998 + ["python"] * 2) + "\n"
        cv_path = _write(tmp_path, "cv.md", cv_body)
        cover_path = _write(tmp_path, "cover-letter.md", cover_body)

        check = run_density_check(
            {"cv.md": cv_path, "cover-letter.md": cover_path},
            ["python"],
        )

        assert check.verdict == "pass"
        assert check.density_violations == []

    def test_each_artifact_evaluated_independently(self, tmp_path: Path) -> None:
        # cv.md fails (5% density), cover-letter.md passes (clean).
        cv_body = " ".join(["filler"] * 95 + ["python"] * 5) + "\n"
        cover_body = "Dear hiring manager, this letter is clean.\n"
        cv_path = _write(tmp_path, "cv.md", cv_body)
        cover_path = _write(tmp_path, "cover-letter.md", cover_body)

        check = run_density_check(
            {"cv.md": cv_path, "cover-letter.md": cover_path},
            ["python"],
        )

        assert check.verdict == "fail"
        assert len(check.density_violations) == 1
        # Only cv.md should be in the violations list — cover-letter.md is
        # clean even though it shares the same keyword set.
        assert check.density_violations[0].artifact == "cv.md"


# ---- AC5: default thresholds --------------------------------------------


class TestDefaultThresholds:
    """AC5 — conservative defaults (1.5% / 3 reps) bake into the signature."""

    def test_defaults_are_1_5_pct_and_3_reps(self, tmp_path: Path) -> None:
        # Probe the signature defaults by triggering breaches that should
        # only fire under those exact values.
        # 4 occurrences in 1000 tokens = 0.4% density (under 1.5%) but
        # 4 > 3 reps — must fail under defaults.
        body = " ".join(["filler"] * 996 + ["python"] * 4) + "\n"
        cv_path = _write(tmp_path, "cv.md", body)
        # No threshold kwargs — relying on the function-signature defaults.
        check = run_density_check({"cv.md": cv_path}, ["python"])
        assert check.verdict == "fail"


# ---- AC7: pass-state shape ----------------------------------------------


class TestPassState:
    """AC7 — empty violations + empty dump_paragraph_locations -> pass."""

    def test_no_violations_means_pass_with_empty_lists(
        self, tmp_path: Path
    ) -> None:
        cv_path = _write(
            tmp_path,
            "cv.md",
            "# CV\n\nDave is a backend engineer with five years of experience.\n",
        )
        check = run_density_check({"cv.md": cv_path}, ["python", "fastapi"])
        assert check.verdict == "pass"
        assert check.density_violations == []
        # Story 5.2 will populate dump_paragraph_locations; for Story 5.1
        # the field exists but is always empty.
        assert check.dump_paragraph_locations == []

    def test_empty_must_haves_yields_pass(self, tmp_path: Path) -> None:
        cv_path = _write(tmp_path, "cv.md", "anything")
        check = run_density_check({"cv.md": cv_path}, [])
        assert check == KeywordStuffingCheck(verdict="pass")

    def test_no_artifacts_yields_pass(self) -> None:
        check = run_density_check({}, ["python"])
        assert check == KeywordStuffingCheck(verdict="pass")

    def test_missing_artifact_file_tolerated(self, tmp_path: Path) -> None:
        # File does not exist on disk; matcher silently drops it (same
        # idiom as Story 4.1 for absent upwork-proposal.md). Verdict is
        # pass because no readable artifact = no countable text.
        missing = tmp_path / "ghost.md"
        check = run_density_check({"ghost.md": missing}, ["python"])
        assert check.verdict == "pass"


# ---- frozen-dataclass contract -----------------------------------------


class TestDataclassContract:
    """DensityViolation and KeywordStuffingCheck are frozen value objects."""

    def test_density_violation_is_frozen(self) -> None:
        violation = DensityViolation(
            keyword="python",
            artifact="cv.md",
            occurrences=5,
            total_tokens=100,
            density_pct=5.0,
            threshold_breached="max_density_pct",
        )
        try:
            violation.keyword = "rust"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("DensityViolation should be frozen")

    def test_keyword_stuffing_check_is_frozen(self) -> None:
        check = KeywordStuffingCheck(verdict="pass")
        try:
            check.verdict = "fail"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("KeywordStuffingCheck should be frozen")
