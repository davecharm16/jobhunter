"""Unit tests for Story 5.2 placement detection (dump paragraphs + comma runs).

Mirrors `test_keyword_stuffing_matcher.py` style: pure-function assertions,
deterministic results, no LLM stubs (AC8). Covers:

- AC1: `split_paragraphs` produces blank-line-delimited blocks with
  heading/list filtering and bullet-block detection.
- AC2: `detect_dump_paragraphs` flags long paragraphs whose must-have ratio
  exceeds the ceiling.
- AC3: `detect_comma_runs` finds runs of `min_tokens`+ comma-separated JD
  must-haves.
- AC4: function-signature defaults are 15 / 0.30 / 4.
- AC5: `run_keyword_stuffing_check` populates `dump_paragraph_locations[]`
  with the documented dict shape.
- AC6: OR-combine — density-only fail, placement-only fail, both fail all
  yield `verdict == "fail"`; clean yields `"pass"`.
- AC7: a five-bullet pure-keywords skills list emits one
  `comma_run_violation`.
"""

from __future__ import annotations

from pathlib import Path

from jobhunter.keyword_stuffing_matcher import (
    Paragraph,
    detect_comma_runs,
    detect_dump_paragraphs,
    run_keyword_stuffing_check,
    split_paragraphs,
    tokenize_markdown,
)

# ---- helpers --------------------------------------------------------------


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# ---- AC1: split_paragraphs ------------------------------------------------


class TestSplitParagraphs:
    """AC1 — blank-line-delimited blocks; headings dropped; bullets flagged."""

    def test_two_prose_paragraphs_split_on_blank_line(self) -> None:
        text = "First paragraph here.\n\nSecond paragraph here.\n"
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 2
        assert paragraphs[0].index == 0
        assert paragraphs[0].tokens == ["first", "paragraph", "here"]
        assert paragraphs[1].index == 1
        assert paragraphs[1].tokens == ["second", "paragraph", "here"]
        assert paragraphs[0].bullet_items is None
        assert paragraphs[1].bullet_items is None

    def test_headings_are_excluded_and_do_not_advance_index(self) -> None:
        # A `# Heading` line between two prose paragraphs must NOT count
        # as its own paragraph — index 1 belongs to the second prose
        # block, not the heading.
        text = (
            "Prose one.\n"
            "\n"
            "# Skills heading\n"
            "\n"
            "Prose two.\n"
        )
        paragraphs = split_paragraphs(text)
        assert [p.index for p in paragraphs] == [0, 1]
        assert paragraphs[0].tokens == ["prose", "one"]
        assert paragraphs[1].tokens == ["prose", "two"]

    def test_bullet_block_is_one_paragraph_with_items(self) -> None:
        text = (
            "Intro paragraph.\n"
            "\n"
            "- TypeScript\n"
            "- Node\n"
            "- Kubernetes\n"
        )
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 2
        assert paragraphs[1].bullet_items == [
            "TypeScript",
            "Node",
            "Kubernetes",
        ]

    def test_ordered_list_block_is_bullet_paragraph(self) -> None:
        text = (
            "Intro.\n"
            "\n"
            "1. TypeScript\n"
            "2. Node\n"
            "3. Kubernetes\n"
        )
        paragraphs = split_paragraphs(text)
        assert paragraphs[1].bullet_items == [
            "TypeScript",
            "Node",
            "Kubernetes",
        ]

    def test_star_bullet_block_recognized(self) -> None:
        text = "* TypeScript\n* Node\n* Kubernetes\n"
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 1
        assert paragraphs[0].bullet_items == [
            "TypeScript",
            "Node",
            "Kubernetes",
        ]

    def test_frontmatter_is_stripped(self) -> None:
        text = (
            "---\n"
            "title: CV\n"
            "tags: [python]\n"
            "---\n"
            "Real body here.\n"
        )
        paragraphs = split_paragraphs(text)
        assert len(paragraphs) == 1
        assert paragraphs[0].tokens == ["real", "body", "here"]

    def test_empty_string_returns_empty_list(self) -> None:
        assert split_paragraphs("") == []

    def test_paragraph_text_preserves_original_lines(self) -> None:
        # The matcher writes the first 120 chars as `excerpt`, so the
        # source text on `Paragraph.text` must reflect the actual block
        # (not the post-tokenization view).
        text = "Hello world.\n"
        paragraphs = split_paragraphs(text)
        assert paragraphs[0].text == "Hello world."


# ---- AC2: detect_dump_paragraphs ------------------------------------------


class TestDetectDumpParagraphs:
    """AC2 — long paragraph with >30% must-have ratio is flagged."""

    def _paragraph(self, text: str) -> Paragraph:
        # Build a Paragraph by reusing the tokenizer so tests stay
        # consistent with how the matcher constructs them in production.
        return Paragraph(
            index=0,
            text=text,
            tokens=tokenize_markdown(text),
            bullet_items=None,
        )

    def test_paragraph_below_min_tokens_is_never_a_dump(self) -> None:
        # 5 tokens total, 5 of which are must-haves (100% ratio) — but
        # below the 15-token floor, so no flag.
        paragraph = self._paragraph("python django flask postgres redis")
        assert detect_dump_paragraphs(
            paragraph,
            {"python", "django", "flask", "postgres", "redis"},
        ) is False

    def test_long_paragraph_under_ratio_is_not_a_dump(self) -> None:
        # 20 tokens, 4 must-haves -> 0.20 ratio, under default 0.30.
        text = (
            "I built backend services in python at acme for three years "
            "shipping django flask and a custom redis worker."
        )
        paragraph = self._paragraph(text)
        assert detect_dump_paragraphs(
            paragraph,
            {"python", "django", "flask", "redis"},
        ) is False

    def test_long_paragraph_over_ratio_is_a_dump(self) -> None:
        # 16 tokens, 6 must-haves -> 0.375 ratio, over default 0.30.
        text = (
            "skilled in python django flask postgres redis kafka "
            "across many roles built systems shipped on time"
        )
        paragraph = self._paragraph(text)
        assert detect_dump_paragraphs(
            paragraph,
            {"python", "django", "flask", "postgres", "redis", "kafka"},
        ) is True

    def test_exactly_at_ratio_is_not_a_dump(self) -> None:
        # 20 tokens, 6 must-haves -> 0.30 ratio exactly; the rule is
        # strict-greater, so this is NOT a dump.
        text = (
            "python django flask redis postgres kafka "
            "filler filler filler filler filler filler filler filler "
            "filler filler filler filler filler filler"
        )
        paragraph = self._paragraph(text)
        # Sanity-check the construction — must have exactly 20 tokens.
        assert len(paragraph.tokens) == 20
        assert detect_dump_paragraphs(
            paragraph,
            {"python", "django", "flask", "postgres", "redis", "kafka"},
        ) is False


# ---- AC3: detect_comma_runs -----------------------------------------------


class TestDetectCommaRuns:
    """AC3 — comma-separated runs of >= min_tokens consecutive must-haves."""

    def _prose(self, text: str) -> Paragraph:
        return Paragraph(
            index=0,
            text=text,
            tokens=tokenize_markdown(text),
            bullet_items=None,
        )

    def _bullets(self, items: list[str]) -> Paragraph:
        text = "\n".join(f"- {item}" for item in items)
        return Paragraph(
            index=0,
            text=text,
            tokens=tokenize_markdown(text),
            bullet_items=items,
        )

    def test_four_consecutive_must_haves_emits_one_run(self) -> None:
        # Pure comma-separated list of must-haves with a trailing period
        # — the detector strips a sentence terminator off the last item.
        paragraph = self._prose("TypeScript, Node, Kubernetes, GraphQL.")
        runs = detect_comma_runs(
            paragraph,
            {"typescript", "node", "kubernetes", "graphql"},
        )
        assert len(runs) == 1
        assert runs[0] == ["typescript", "node", "kubernetes", "graphql"]

    def test_three_consecutive_must_haves_does_not_emit(self) -> None:
        # Default min_tokens is 4; a 3-item run is under the threshold.
        paragraph = self._prose("Skills: TypeScript, Node, Kubernetes.")
        runs = detect_comma_runs(
            paragraph,
            {"typescript", "node", "kubernetes"},
        )
        assert runs == []

    def test_non_keyword_break_resets_the_run(self) -> None:
        # "TypeScript, Node, my friend, Kubernetes, GraphQL" — the
        # "my friend" piece is not a must-have, so the longest pure run
        # is only 2 (TypeScript, Node) and only 2 (Kubernetes, GraphQL),
        # neither reaching the 4-item floor.
        paragraph = self._prose(
            "TypeScript, Node, my friend, Kubernetes, GraphQL."
        )
        runs = detect_comma_runs(
            paragraph,
            {"typescript", "node", "kubernetes", "graphql"},
        )
        assert runs == []

    def test_bullet_block_flattened_for_run_detection(self) -> None:
        # AC7: five-bullet skills list of pure JD keywords -> one run.
        paragraph = self._bullets(
            ["TypeScript", "Node", "Kubernetes", "GraphQL", "Postgres"]
        )
        runs = detect_comma_runs(
            paragraph,
            {
                "typescript",
                "node",
                "kubernetes",
                "graphql",
                "postgres",
            },
        )
        assert len(runs) == 1
        assert runs[0] == [
            "typescript",
            "node",
            "kubernetes",
            "graphql",
            "postgres",
        ]

    def test_custom_min_tokens_threshold(self) -> None:
        paragraph = self._prose("TypeScript, Node, Kubernetes.")
        runs = detect_comma_runs(
            paragraph,
            {"typescript", "node", "kubernetes"},
            min_tokens=3,
        )
        assert len(runs) == 1
        assert runs[0] == ["typescript", "node", "kubernetes"]


# ---- AC4: default thresholds ----------------------------------------------


class TestPlacementDefaults:
    """AC4 — function signatures bake the 15 / 0.30 / 4 defaults."""

    def test_dump_paragraph_defaults_in_signature(self) -> None:
        # Build a paragraph that's exactly 14 tokens — just below the
        # 15-token floor — with 100% must-haves. Default call must NOT
        # flag it.
        tokens = ["python"] * 14
        paragraph = Paragraph(
            index=0,
            text=" ".join(tokens),
            tokens=tokens,
            bullet_items=None,
        )
        assert detect_dump_paragraphs(paragraph, {"python"}) is False

    def test_comma_run_default_is_four(self) -> None:
        paragraph = Paragraph(
            index=0,
            text="a, b, c",
            tokens=["a", "b", "c"],
            bullet_items=None,
        )
        # 3 must-haves — under the default 4 floor.
        assert detect_comma_runs(paragraph, {"a", "b", "c"}) == []


# ---- AC5 + AC6: run_keyword_stuffing_check combined verdict ----------------


class TestRunKeywordStuffingCheck:
    """AC5 — location dicts have the documented shape.
    AC6 — verdict OR-combines density + placement.
    """

    def test_clean_artifact_yields_pass(self, tmp_path: Path) -> None:
        body = "# CV\n\nDave is a backend engineer with five years.\n"
        cv = _write(tmp_path, "cv.md", body)
        check = run_keyword_stuffing_check({"cv.md": cv}, ["python"])
        assert check.verdict == "pass"
        assert check.density_violations == []
        assert check.dump_paragraph_locations == []

    def test_density_only_fail_yields_fail(self, tmp_path: Path) -> None:
        # 5% density on 100 tokens with NO long must-have-heavy paragraph
        # (the keyword runs end-to-end so no comma list, no dump-ratio
        # paragraph block over 15 tokens because each "python" token sits
        # in the same single paragraph). Actually with 5 pythons in 100
        # filler tokens, the only paragraph IS 100 tokens — 5/100 = 5%
        # must-have ratio, well under 30%. So this stays density-only.
        words = ["filler"] * 95 + ["python"] * 5
        body = " ".join(words) + "\n"
        cv = _write(tmp_path, "cv.md", body)
        check = run_keyword_stuffing_check({"cv.md": cv}, ["python"])
        assert check.verdict == "fail"
        assert len(check.density_violations) == 1
        assert check.dump_paragraph_locations == []

    def test_placement_only_fail_yields_fail(self, tmp_path: Path) -> None:
        # A dump paragraph: 6 must-haves clustered in a 16-token block,
        # plus a LONG clean filler paragraph so each individual keyword's
        # per-artifact density (1 / (16 + filler_tokens)) stays under
        # 1.5%. The dump-paragraph rule operates within ONE paragraph;
        # the density rule operates across the whole artifact.
        filler = " ".join(["alpha"] * 200)
        body = (
            "# CV\n\n"
            "skilled in python django flask postgres redis kafka "
            "across many roles built systems shipped on time\n"
            "\n"
            f"{filler}\n"
        )
        cv = _write(tmp_path, "cv.md", body)
        check = run_keyword_stuffing_check(
            {"cv.md": cv},
            ["python", "django", "flask", "postgres", "redis", "kafka"],
        )
        assert check.verdict == "fail"
        assert check.density_violations == []
        assert len(check.dump_paragraph_locations) == 1
        loc = check.dump_paragraph_locations[0]
        assert loc["artifact"] == "cv.md"
        assert loc["kind"] == "keyword_dump_paragraph"
        assert loc["paragraph_index"] == 0
        assert "keyword_ratio" in loc
        assert loc["keyword_ratio"] > 0.30
        assert set(loc["matched_keywords"]) == {
            "python",
            "django",
            "flask",
            "postgres",
            "redis",
            "kafka",
        }
        assert len(loc["excerpt"]) <= 120
        assert loc["excerpt"].startswith("skilled in")

    def test_both_dimensions_fail_emits_both_violation_lists(
        self, tmp_path: Path
    ) -> None:
        # 10 occurrences of "python" inside one paragraph: per-keyword
        # density blows past 1.5% AND the paragraph itself is a dump.
        words = ["filler"] * 14 + ["python"] * 10
        body = " ".join(words) + "\n"
        cv = _write(tmp_path, "cv.md", body)
        check = run_keyword_stuffing_check({"cv.md": cv}, ["python"])
        assert check.verdict == "fail"
        assert len(check.density_violations) == 1
        assert len(check.dump_paragraph_locations) == 1
        assert (
            check.dump_paragraph_locations[0]["kind"]
            == "keyword_dump_paragraph"
        )

    def test_comma_run_violation_location_shape(self, tmp_path: Path) -> None:
        # AC7: 5-bullet skills list of pure JD keywords -> ONE
        # comma_run_violation, no keyword_ratio key.
        body = (
            "Intro paragraph.\n"
            "\n"
            "- TypeScript\n"
            "- Node\n"
            "- Kubernetes\n"
            "- GraphQL\n"
            "- Postgres\n"
        )
        cv = _write(tmp_path, "cv.md", body)
        check = run_keyword_stuffing_check(
            {"cv.md": cv},
            ["TypeScript", "Node", "Kubernetes", "GraphQL", "Postgres"],
        )
        assert check.verdict == "fail"
        # Exactly one comma-run violation (the bullet block).
        comma_runs = [
            loc
            for loc in check.dump_paragraph_locations
            if loc["kind"] == "comma_run_violation"
        ]
        assert len(comma_runs) == 1
        loc = comma_runs[0]
        assert loc["artifact"] == "cv.md"
        # The bullet block is paragraph index 1 (after the intro
        # paragraph at index 0).
        assert loc["paragraph_index"] == 1
        assert "keyword_ratio" not in loc
        assert loc["matched_keywords"] == [
            "typescript",
            "node",
            "kubernetes",
            "graphql",
            "postgres",
        ]
        assert "TypeScript" in loc["excerpt"] or "typescript" in loc["excerpt"]

    def test_empty_must_haves_yields_pass(self, tmp_path: Path) -> None:
        cv = _write(tmp_path, "cv.md", "anything goes here")
        check = run_keyword_stuffing_check({"cv.md": cv}, [])
        assert check.verdict == "pass"
        assert check.density_violations == []
        assert check.dump_paragraph_locations == []

    def test_missing_artifact_is_tolerated(self, tmp_path: Path) -> None:
        # Same idiom as Story 5.1 / Story 4.1: an absent on-disk path is
        # silently dropped, not raised — happens when the proposal artifact
        # is unproduced for a non-Upwork JD.
        check = run_keyword_stuffing_check(
            {"upwork-proposal.md": tmp_path / "ghost.md"},
            ["python"],
        )
        assert check.verdict == "pass"


# ---- AC7: bullet-block comma run end-to-end -------------------------------


class TestBulletBlockCommaRun:
    """AC7 — a five-bullet skills list of pure JD keywords is caught."""

    def test_five_bullet_skills_list_emits_comma_run_violation(
        self, tmp_path: Path
    ) -> None:
        body = (
            "# Skills\n"
            "\n"
            "- TypeScript\n"
            "- Node\n"
            "- Kubernetes\n"
            "- GraphQL\n"
            "- Postgres\n"
        )
        cv = _write(tmp_path, "cv.md", body)
        check = run_keyword_stuffing_check(
            {"cv.md": cv},
            ["TypeScript", "Node", "Kubernetes", "GraphQL", "Postgres"],
        )
        assert check.verdict == "fail"
        kinds = [
            loc["kind"] for loc in check.dump_paragraph_locations
        ]
        assert "comma_run_violation" in kinds
