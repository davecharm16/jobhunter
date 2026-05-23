"""Unit tests for the Story 4.3 content-loss config plumbing."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from jobhunter.content_loss_matcher import (
    ContentLossCheck,
    EmbeddingMatcherUnavailable,
    iter_high_impact_relevant,
    run_check,
)
from jobhunter.content_loss_writer import write_content_loss_block
from jobhunter.yaml_config import (
    ContentLossConfig,
    DriftConfig,
    YamlConfigError,
    load_yaml_config,
)


_DRIFT_DEFAULTS = {
    "relevance_matcher": "tag_overlap",
    "presence_matcher": "substring",
    "tag_overlap_min": 1,
    "keyword_overlap_pct": 0.20,
    "embedding_distance_max": 0.35,
    "presence_semantic_threshold": 0.80,
    "reason_codes": ("irrelevant_to_jd", "silently_lost"),
}


def _config(**overrides: object) -> ContentLossConfig:
    data = {**_DRIFT_DEFAULTS, **overrides}
    return ContentLossConfig(**data)  # type: ignore[arg-type]


# ---- AC1: config loads with defaults ----------------------------------------


def test_load_yaml_config_returns_drift_defaults_when_section_absent(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            cost:
              monthly_cap_usd: 25
              per_app_max_usd: 0.25
            output:
              dir: out
            prompts:
              cv: prompts/cv.v1.md
              cover_letter: prompts/cover_letter.v1.md
              upwork_proposal: prompts/upwork_proposal.v1.md
            red_flags:
              upwork:
                budget_floor_usd_hourly: 25
                budget_floor_usd_fixed: 500
              onlinejobs_ph:
                rate_floor_usd_monthly: 600
            """
        ),
        encoding="utf-8",
    )
    cfg = load_yaml_config(path)
    assert isinstance(cfg.drift, DriftConfig)
    cl = cfg.drift.content_loss
    assert cl.relevance_matcher == "tag_overlap"
    assert cl.presence_matcher == "substring"
    assert cl.tag_overlap_min == 1


def test_load_yaml_config_rejects_unknown_relevance_matcher(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            cost: {monthly_cap_usd: 25, per_app_max_usd: 0.25}
            output: {dir: out}
            prompts:
              cv: prompts/cv.v1.md
              cover_letter: prompts/cover_letter.v1.md
              upwork_proposal: prompts/upwork_proposal.v1.md
            red_flags:
              upwork: {budget_floor_usd_hourly: 25, budget_floor_usd_fixed: 500}
              onlinejobs_ph: {rate_floor_usd_monthly: 600}
            drift:
              content_loss:
                relevance_matcher: bogus
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(YamlConfigError, match="relevance_matcher"):
        load_yaml_config(path)


def test_load_yaml_config_rejects_unknown_presence_matcher(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            cost: {monthly_cap_usd: 25, per_app_max_usd: 0.25}
            output: {dir: out}
            prompts:
              cv: prompts/cv.v1.md
              cover_letter: prompts/cover_letter.v1.md
              upwork_proposal: prompts/upwork_proposal.v1.md
            red_flags:
              upwork: {budget_floor_usd_hourly: 25, budget_floor_usd_fixed: 500}
              onlinejobs_ph: {rate_floor_usd_monthly: 600}
            drift:
              content_loss:
                presence_matcher: bogus
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(YamlConfigError, match="presence_matcher"):
        load_yaml_config(path)


# ---- AC2: matcher mode dispatch -------------------------------------------


def test_embedding_distance_raises_unavailable() -> None:
    cfg = _config(relevance_matcher="embedding_distance")
    with pytest.raises(EmbeddingMatcherUnavailable, match="no embeddings client"):
        iter_high_impact_relevant({}, {"must_haves": [], "nice_to_haves": []}, cfg)


def test_semantic_presence_raises_unavailable() -> None:
    cfg = _config(presence_matcher="semantic")
    with pytest.raises(EmbeddingMatcherUnavailable, match="no embeddings client"):
        run_check([], {}, [], cfg)


def test_tag_overlap_min_higher_filters_out_single_overlap() -> None:
    cv = {
        "work": [
            {
                "highImpact": True,
                "position": "Engineer",
                "name": "Acme",
                "tags": ["typescript"],
                "highlights": ["Built a TypeScript ingestion service"],
            }
        ]
    }
    parsed_jd = {"must_haves": ["typescript"], "nice_to_haves": []}

    cfg_default = _config(tag_overlap_min=1)
    assert len(iter_high_impact_relevant(cv, parsed_jd, cfg_default)) == 1

    cfg_strict = _config(tag_overlap_min=2)
    assert iter_high_impact_relevant(cv, parsed_jd, cfg_strict) == []


def test_keyword_overlap_matcher_uses_token_ratio() -> None:
    cv = {
        "work": [
            {
                "highImpact": True,
                "position": "Engineer",
                "name": "Acme",
                "tags": ["unrelated"],
                "highlights": ["Built a TypeScript fintech billing reconciler"],
            }
        ]
    }
    parsed_jd = {
        "must_haves": ["typescript", "fintech"],
        "nice_to_haves": ["billing"],
    }
    cfg = _config(relevance_matcher="keyword_overlap", keyword_overlap_pct=0.20)
    result = iter_high_impact_relevant(cv, parsed_jd, cfg)
    assert len(result) == 1


# ---- AC4: config_snapshot written into drift.json --------------------------


def test_writer_records_config_snapshot(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    check = ContentLossCheck(verdict="pass", preserved_entries=[], dropped_entries=[])
    snapshot = {
        "relevance_matcher": "tag_overlap",
        "presence_matcher": "substring",
        "tag_overlap_min": 1,
    }
    target = write_content_loss_block(out, check, config_snapshot=snapshot)
    import json

    block = json.loads(target.read_text(encoding="utf-8"))["content_loss"]
    assert block["config_snapshot"] == snapshot


def test_writer_records_error_on_unavailable_matcher(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    check = ContentLossCheck(verdict="fail", preserved_entries=[], dropped_entries=[])
    target = write_content_loss_block(
        out, check, config_snapshot={"relevance_matcher": "embedding_distance"},
        error="embedding matcher selected but no embeddings client configured",
    )
    import json

    block = json.loads(target.read_text(encoding="utf-8"))["content_loss"]
    assert block["error"].startswith("embedding matcher selected")
    assert block["verdict"] == "fail"


# ---- AC5: no LLM call in default mode -------------------------------------


def test_default_mode_does_not_import_llm_client() -> None:
    import jobhunter.content_loss_matcher as m
    import ast
    import pathlib

    source = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "llm_client" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "llm_client" not in node.module
