"""Unit tests for `jobhunter.yaml_config` (Story 2.2).

Three AC groups:
- AC1: config.yaml is separate from .env, with sensible defaults, and rejects
  secret-shaped keys structurally.
- AC2: per-app cost ceiling lives in config.yaml; monthly cap default matches
  the env-based runtime config.
- AC3: missing required keys fail fast naming the missing key path.
"""

from __future__ import annotations

import textwrap
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._yaml_fixtures import DEFAULT_CONFIG_YAML, write_config_yaml

from jobhunter.config import CONFIG_YAML_PATH, PROJECT_ROOT
from jobhunter.yaml_config import (
    YamlConfig,
    YamlConfigError,
    load_yaml_config,
)

# --- AC1: config.yaml separation -------------------------------------------


def test_config_yaml_path_is_under_project_root() -> None:
    assert CONFIG_YAML_PATH.parent == PROJECT_ROOT
    assert CONFIG_YAML_PATH.name == "config.yaml"


def test_committed_config_yaml_loads_with_defaults() -> None:
    """The committed `config.yaml` template at the repo root must load."""
    assert CONFIG_YAML_PATH.is_file(), (
        f"committed config.yaml missing at {CONFIG_YAML_PATH}"
    )
    config = load_yaml_config(CONFIG_YAML_PATH)
    assert config.cost.monthly_cap_usd == Decimal("25")
    assert config.cost.per_app_max_usd == Decimal("0.25")
    assert config.output.dir == "out"
    assert config.prompts.cv == "prompts/cv.v1.md"
    assert config.prompts.cover_letter == "prompts/cover_letter.v1.md"
    assert config.prompts.upwork_proposal == "prompts/upwork_proposal.v1.md"
    assert config.red_flags.upwork.budget_floor_usd_hourly == 25
    assert config.red_flags.upwork.budget_floor_usd_fixed == 500
    assert config.red_flags.onlinejobs_ph.rate_floor_usd_monthly == 600


def test_load_yaml_config_returns_frozen_dataclass(tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path)
    config = load_yaml_config(yaml_path)
    assert isinstance(config, YamlConfig)
    with pytest.raises(Exception):
        config.cost = None  # type: ignore[misc]


def test_load_yaml_config_round_trip_default_content(tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path)
    config = load_yaml_config(yaml_path)
    assert config.cost.monthly_cap_usd == Decimal("25")
    assert config.cost.per_app_max_usd == Decimal("0.25")


def test_load_yaml_config_uses_default_path_when_none(monkeypatch, tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path)
    import jobhunter.yaml_config as module_under_test

    monkeypatch.setattr(module_under_test, "CONFIG_YAML_PATH", yaml_path)
    config = module_under_test.load_yaml_config()
    assert config.output.dir == "out"


@pytest.mark.parametrize(
    "secret_block",
    [
        "openai_api_key: sk-leak\n",
        "anthropic_token: tok-leak\n",
        "client_secret: shh\n",
        "secret_thing: shh\n",
        "OPENAI_API_KEY: SK-LEAK\n",
    ],
)
def test_load_yaml_config_rejects_secret_shaped_top_level_keys(
    tmp_path: Path, secret_block: str
) -> None:
    yaml_path = write_config_yaml(tmp_path, DEFAULT_CONFIG_YAML + secret_block)
    with pytest.raises(YamlConfigError, match="secret"):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_nested_secret_keys(tmp_path: Path) -> None:
    content = textwrap.dedent(
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
            anthropic_api_key: sk-leak
          onlinejobs_ph:
            rate_floor_usd_monthly: 600
        """
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="secret"):
        load_yaml_config(yaml_path)


def test_committed_config_yaml_has_no_secret_shaped_keys() -> None:
    """Repository-level guarantee that the committed template stays clean.

    Story 5.3: matches the loader's actual `_SECRET_KEY_PATTERN` (end-anchored
    on the suffix forms + start-anchored on `secret_`) so non-secret yaml keys
    that happen to contain the substring (e.g. `dump_paragraph_min_tokens`,
    `comma_run_min_tokens`) don't trip the hygiene check.
    """
    import re

    text = CONFIG_YAML_PATH.read_text(encoding="utf-8")
    # Same regex shape as _SECRET_KEY_PATTERN in yaml_config.py: anchored at
    # the end of an identifier or at the start with `secret_`. Treat each
    # non-comment yaml line as `<key>:` and check the key against the regex.
    secret_pattern = re.compile(
        r"(?:^secret_|_api_key$|_token$|_secret$)", re.IGNORECASE
    )
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key = stripped.split(":", 1)[0].strip().lstrip("-").strip()
        # Bare lists / nested values without keys (e.g. `- python`) skip.
        if not key or " " in key:
            continue
        assert not secret_pattern.search(key), (
            f"committed config.yaml line {lineno} key `{key}` looks secret-shaped "
            f"(secrets belong in .env)"
        )


# --- AC2: per-app cost ceiling read on every run ---------------------------


def test_load_yaml_config_per_app_max_default_is_25_cents(tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path)
    config = load_yaml_config(yaml_path)
    assert config.cost.per_app_max_usd == Decimal("0.25")


def test_load_yaml_config_per_app_max_override(tmp_path: Path) -> None:
    content = DEFAULT_CONFIG_YAML.replace(
        "per_app_max_usd: 0.25", "per_app_max_usd: 0.10"
    )
    yaml_path = write_config_yaml(tmp_path, content)
    config = load_yaml_config(yaml_path)
    assert config.cost.per_app_max_usd == Decimal("0.10")


def test_load_yaml_config_monthly_cap_override(tmp_path: Path) -> None:
    """Changing monthly_cap_usd in config.yaml takes effect on the next load."""
    content = DEFAULT_CONFIG_YAML.replace(
        "monthly_cap_usd: 25", "monthly_cap_usd: 10"
    )
    yaml_path = write_config_yaml(tmp_path, content)
    config = load_yaml_config(yaml_path)
    assert config.cost.monthly_cap_usd == Decimal("10")


def test_load_yaml_config_runtime_config_env_still_wins() -> None:
    """`runtime_config.load_runtime_config()` keeps reading MONTHLY_SPEND_CAP_USD.

    Story 2.2 is additive: the env-based loader is the source of truth for the
    secret-adjacent monthly cap; yaml is the defensive default for the new
    per_app_max_usd field. This test pins that runtime_config is untouched.
    """
    # Importing succeeds; signature is unchanged.
    import inspect

    from jobhunter.runtime_config import load_runtime_config  # noqa: F401

    sig = inspect.signature(load_runtime_config)
    assert list(sig.parameters) == ["env_path"]


# --- AC3: missing required key fails fast ----------------------------------


def test_load_yaml_config_missing_file_names_path(tmp_path: Path) -> None:
    missing = tmp_path / "config.yaml"
    with pytest.raises(YamlConfigError) as exc:
        load_yaml_config(missing)
    assert str(missing) in str(exc.value)


@pytest.mark.parametrize(
    "missing_section", ["cost", "output", "prompts", "red_flags"]
)
def test_load_yaml_config_missing_required_section(
    tmp_path: Path, missing_section: str
) -> None:
    lines = DEFAULT_CONFIG_YAML.splitlines(keepends=True)
    filtered: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith(f"{missing_section}:"):
            skipping = True
            continue
        if skipping:
            if line.startswith(" ") or line.strip() == "":
                continue
            skipping = False
        filtered.append(line)
    yaml_path = write_config_yaml(tmp_path, "".join(filtered))

    with pytest.raises(YamlConfigError, match=missing_section):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_unknown_top_level_keys(tmp_path: Path) -> None:
    content = DEFAULT_CONFIG_YAML + "\nbogus_section:\n  foo: bar\n"
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="bogus_section"):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_unknown_nested_keys(tmp_path: Path) -> None:
    content = DEFAULT_CONFIG_YAML.replace(
        "  per_app_max_usd: 0.25",
        "  per_app_max_usd: 0.25\n  bogus_key: 1",
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="bogus_key"):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_empty_file(tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path, "")
    with pytest.raises(YamlConfigError):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_non_mapping_top_level(tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path, "- list\n- not a mapping\n")
    with pytest.raises(YamlConfigError, match="mapping"):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_malformed_yaml(tmp_path: Path) -> None:
    yaml_path = write_config_yaml(tmp_path, "cost: [unterminated\n")
    with pytest.raises(YamlConfigError, match="malformed"):
        load_yaml_config(yaml_path)


@pytest.mark.parametrize(
    "bad_value",
    ["abc", "-1", "0", ".nan", ".inf"],
)
def test_load_yaml_config_rejects_invalid_monthly_cap(
    tmp_path: Path, bad_value: str
) -> None:
    content = DEFAULT_CONFIG_YAML.replace(
        "monthly_cap_usd: 25", f"monthly_cap_usd: {bad_value}"
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="cost.monthly_cap_usd"):
        load_yaml_config(yaml_path)


@pytest.mark.parametrize(
    "bad_value",
    ["abc", "-1", "0", "1.5"],
)
def test_load_yaml_config_rejects_invalid_red_flag_floor(
    tmp_path: Path, bad_value: str
) -> None:
    content = DEFAULT_CONFIG_YAML.replace(
        "budget_floor_usd_hourly: 25",
        f"budget_floor_usd_hourly: {bad_value}",
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="red_flags.upwork.budget_floor_usd_hourly"):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_empty_prompt_path(tmp_path: Path) -> None:
    content = DEFAULT_CONFIG_YAML.replace(
        "cv: prompts/cv.v1.md", "cv: ''"
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="prompts.cv"):
        load_yaml_config(yaml_path)


def test_load_yaml_config_rejects_bool_as_int(tmp_path: Path) -> None:
    content = DEFAULT_CONFIG_YAML.replace(
        "budget_floor_usd_hourly: 25", "budget_floor_usd_hourly: true"
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="budget_floor_usd_hourly"):
        load_yaml_config(yaml_path)
