"""Unit tests for the Story 5.3 keyword-stuffing yaml config + threshold resolution.

Mirrors `tests/unit/test_content_loss_config.py` (Story 4.3): config-loader
defaults, per-key validation, per-channel shallow-merge resolution. Pure
functional tests — no FastAPI, no LLM stub.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from jobhunter.yaml_config import (
    KeywordStuffingChannels,
    KeywordStuffingConfig,
    YamlConfigError,
    load_yaml_config,
    resolve_keyword_stuffing_thresholds,
)

_MINIMAL_REQUIRED_YAML = textwrap.dedent(
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
)


def _write_config(path: Path, extra: str = "") -> Path:
    path.write_text(_MINIMAL_REQUIRED_YAML + extra, encoding="utf-8")
    return path


# ---- AC2: config loads with defaults when section absent ------------------


def test_keyword_stuffing_section_optional_yields_story_5_1_defaults(
    tmp_path: Path,
) -> None:
    """AC2 fallback: a config without a `keyword_stuffing:` section loads with
    the Story 5.1 / 5.2 hard-coded defaults."""
    cfg_path = _write_config(tmp_path / "config.yaml")
    cfg = load_yaml_config(cfg_path)
    ks = cfg.keyword_stuffing
    assert isinstance(ks, KeywordStuffingConfig)
    assert ks.max_density_pct == 1.5
    assert ks.max_repetitions_per_artifact == 3
    assert ks.dump_paragraph_min_tokens == 15
    assert ks.dump_paragraph_max_keyword_ratio == 0.30
    assert ks.comma_run_min_tokens == 4
    # Every channel block is present but empty.
    assert isinstance(ks.channels, KeywordStuffingChannels)
    assert ks.channels.upwork == {}
    assert ks.channels.linkedin == {}
    assert ks.channels.onlinejobs_ph == {}
    assert ks.channels.other == {}


def test_committed_config_yaml_carries_story_5_3_section() -> None:
    """The committed `config.yaml` template loads with Story 5.3's defaults."""
    from jobhunter.config import CONFIG_YAML_PATH

    cfg = load_yaml_config(CONFIG_YAML_PATH)
    ks = cfg.keyword_stuffing
    assert ks.max_density_pct == 1.5
    assert ks.max_repetitions_per_artifact == 3
    # The shipped channel overrides are commented out — all channels empty.
    assert ks.channels.upwork == {}
    assert ks.channels.linkedin == {}
    assert ks.channels.onlinejobs_ph == {}
    assert ks.channels.other == {}


# ---- AC2: global thresholds override the hard-coded defaults --------------


def test_keyword_stuffing_globals_override_story_5_1_defaults(
    tmp_path: Path,
) -> None:
    """A `keyword_stuffing:` section with explicit globals overrides every
    matcher default."""
    extra = textwrap.dedent(
        """\
        keyword_stuffing:
          max_density_pct: 2.5
          max_repetitions_per_artifact: 4
          dump_paragraph_min_tokens: 20
          dump_paragraph_max_keyword_ratio: 0.4
          comma_run_min_tokens: 5
        """
    )
    cfg_path = _write_config(tmp_path / "config.yaml", extra=extra)
    cfg = load_yaml_config(cfg_path)
    ks = cfg.keyword_stuffing
    assert ks.max_density_pct == 2.5
    assert ks.max_repetitions_per_artifact == 4
    assert ks.dump_paragraph_min_tokens == 20
    assert ks.dump_paragraph_max_keyword_ratio == 0.4
    assert ks.comma_run_min_tokens == 5


def test_keyword_stuffing_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    """A typo in the `keyword_stuffing` block fails fast naming the bad key."""
    extra = textwrap.dedent(
        """\
        keyword_stuffing:
          max_densityy_pct: 2.0
        """
    )
    cfg_path = _write_config(tmp_path / "config.yaml", extra=extra)
    with pytest.raises(YamlConfigError, match="max_densityy_pct"):
        load_yaml_config(cfg_path)


def test_keyword_stuffing_rejects_non_positive_density(tmp_path: Path) -> None:
    """A non-positive numeric value fails fast (mirrors Story 4.3 coercion)."""
    extra = textwrap.dedent(
        """\
        keyword_stuffing:
          max_density_pct: 0
        """
    )
    cfg_path = _write_config(tmp_path / "config.yaml", extra=extra)
    with pytest.raises(YamlConfigError, match="positive"):
        load_yaml_config(cfg_path)


# ---- AC3: per-channel overrides shallow-merge over globals ----------------


def test_keyword_stuffing_channel_overrides_are_parsed(tmp_path: Path) -> None:
    """A `channels.upwork:` block with a subset of keys is parsed verbatim."""
    extra = textwrap.dedent(
        """\
        keyword_stuffing:
          channels:
            upwork:
              max_repetitions_per_artifact: 5
              dump_paragraph_max_keyword_ratio: 0.45
        """
    )
    cfg_path = _write_config(tmp_path / "config.yaml", extra=extra)
    cfg = load_yaml_config(cfg_path)
    assert cfg.keyword_stuffing.channels.upwork == {
        "max_repetitions_per_artifact": 5,
        "dump_paragraph_max_keyword_ratio": 0.45,
    }
    # Other channels stay empty.
    assert cfg.keyword_stuffing.channels.linkedin == {}


def test_keyword_stuffing_rejects_unknown_channel_name(tmp_path: Path) -> None:
    """A channel name outside the allowed set fails fast."""
    extra = textwrap.dedent(
        """\
        keyword_stuffing:
          channels:
            indeed:
              max_density_pct: 2.0
        """
    )
    cfg_path = _write_config(tmp_path / "config.yaml", extra=extra)
    with pytest.raises(YamlConfigError, match="indeed"):
        load_yaml_config(cfg_path)


def test_keyword_stuffing_rejects_unknown_channel_override_key(
    tmp_path: Path,
) -> None:
    """A typo inside a per-channel block fails fast naming the bad key."""
    extra = textwrap.dedent(
        """\
        keyword_stuffing:
          channels:
            upwork:
              max_repetitionz_per_artifact: 5
        """
    )
    cfg_path = _write_config(tmp_path / "config.yaml", extra=extra)
    with pytest.raises(YamlConfigError, match="max_repetitionz_per_artifact"):
        load_yaml_config(cfg_path)


def test_resolve_thresholds_returns_globals_when_channel_empty() -> None:
    """An empty per-channel block resolves to the bare global thresholds."""
    cfg = KeywordStuffingConfig(
        max_density_pct=1.5,
        max_repetitions_per_artifact=3,
        dump_paragraph_min_tokens=15,
        dump_paragraph_max_keyword_ratio=0.3,
        comma_run_min_tokens=4,
        channels=KeywordStuffingChannels(
            upwork={}, linkedin={}, onlinejobs_ph={}, other={}
        ),
    )
    resolved = resolve_keyword_stuffing_thresholds(cfg, "upwork")
    assert resolved == {
        "max_density_pct": 1.5,
        "max_repetitions_per_artifact": 3,
        "dump_paragraph_min_tokens": 15,
        "dump_paragraph_max_keyword_ratio": 0.3,
        "comma_run_min_tokens": 4,
    }


def test_resolve_thresholds_overlays_partial_channel_overrides() -> None:
    """A channel block with two overrides leaves the other three keys at globals."""
    cfg = KeywordStuffingConfig(
        max_density_pct=1.5,
        max_repetitions_per_artifact=3,
        dump_paragraph_min_tokens=15,
        dump_paragraph_max_keyword_ratio=0.3,
        comma_run_min_tokens=4,
        channels=KeywordStuffingChannels(
            upwork={
                "max_repetitions_per_artifact": 5,
                "dump_paragraph_max_keyword_ratio": 0.45,
            },
            linkedin={},
            onlinejobs_ph={},
            other={},
        ),
    )
    resolved = resolve_keyword_stuffing_thresholds(cfg, "upwork")
    # Overridden keys.
    assert resolved["max_repetitions_per_artifact"] == 5
    assert resolved["dump_paragraph_max_keyword_ratio"] == 0.45
    # Globals on the rest.
    assert resolved["max_density_pct"] == 1.5
    assert resolved["dump_paragraph_min_tokens"] == 15
    assert resolved["comma_run_min_tokens"] == 4


def test_resolve_thresholds_unknown_channel_falls_back_to_globals() -> None:
    """A channel string outside the allowed set degrades to bare globals."""
    cfg = KeywordStuffingConfig(
        max_density_pct=2.0,
        max_repetitions_per_artifact=4,
        dump_paragraph_min_tokens=15,
        dump_paragraph_max_keyword_ratio=0.3,
        comma_run_min_tokens=4,
        channels=KeywordStuffingChannels(
            upwork={"max_repetitions_per_artifact": 10},
            linkedin={},
            onlinejobs_ph={},
            other={},
        ),
    )
    resolved = resolve_keyword_stuffing_thresholds(cfg, "bogus_channel")
    # The upwork override does NOT bleed in; bare globals only.
    assert resolved["max_repetitions_per_artifact"] == 4
    assert resolved["max_density_pct"] == 2.0


def test_resolve_thresholds_other_channel_uses_other_block() -> None:
    """The `other` channel's overrides are routed to that block specifically."""
    cfg = KeywordStuffingConfig(
        max_density_pct=1.5,
        max_repetitions_per_artifact=3,
        dump_paragraph_min_tokens=15,
        dump_paragraph_max_keyword_ratio=0.3,
        comma_run_min_tokens=4,
        channels=KeywordStuffingChannels(
            upwork={"max_density_pct": 9.9},
            linkedin={},
            onlinejobs_ph={},
            other={"max_density_pct": 2.5},
        ),
    )
    assert resolve_keyword_stuffing_thresholds(cfg, "other")["max_density_pct"] == 2.5
    assert resolve_keyword_stuffing_thresholds(cfg, "linkedin")["max_density_pct"] == 1.5
    assert resolve_keyword_stuffing_thresholds(cfg, "upwork")["max_density_pct"] == 9.9
