"""Story 6.5 AC1: top-level `held_package_ttl_days` config key.

Three contracts pinned here:

1. The new top-level key wins over the legacy
   `fabrication.held_retention_days` when both are present (no deprecation
   warning, because the author migrated cleanly).
2. The legacy key still loads with a `DeprecationWarning` when the new key
   is absent (back-compat — Story 3.4's existing config still works).
3. `0` is a valid value for the new key (disables the auto-discard sweep)
   AND negative values still raise `YamlConfigError`.
"""

from __future__ import annotations

import textwrap
import warnings
from pathlib import Path

import pytest
from tests.unit._yaml_fixtures import DEFAULT_CONFIG_YAML, write_config_yaml

from jobhunter.yaml_config import YamlConfigError, load_yaml_config

# ---- AC1: top-level key precedence over legacy --------------------------


def test_top_level_held_package_ttl_days_wins_over_legacy(tmp_path: Path) -> None:
    """Author can migrate by adding the new key; legacy value is ignored."""
    content = DEFAULT_CONFIG_YAML + textwrap.dedent(
        """\
        held_package_ttl_days: 14

        fabrication:
          claim_extraction:
            timeout_seconds: 60.0
          semantic_method: rule_based
          semantic_threshold: 0.65
          held_retention_days: 7
        """
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with warnings.catch_warnings():
        # Treating warnings as errors here would fail the assertion-that-no-
        # warning-fires (catch_warnings + simplefilter "error") if the new
        # key's precedence path accidentally still hits the deprecation branch.
        warnings.simplefilter("error", DeprecationWarning)
        config = load_yaml_config(yaml_path)
    assert config.held_package_ttl_days == 14
    # Legacy key still parses and lands on the fabrication block for back-
    # compat consumers (none in v1 — but the field stays in the schema).
    assert config.fabrication.held_retention_days == 7


def test_top_level_held_package_ttl_days_defaults_to_7(tmp_path: Path) -> None:
    """When neither the new nor legacy key is present, default is 7."""
    yaml_path = write_config_yaml(tmp_path, DEFAULT_CONFIG_YAML)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        config = load_yaml_config(yaml_path)
    assert config.held_package_ttl_days == 7


def test_top_level_held_package_ttl_days_accepts_zero_to_disable(
    tmp_path: Path,
) -> None:
    """AC1: `held_package_ttl_days: 0` is valid and disables the sweep."""
    content = DEFAULT_CONFIG_YAML + "held_package_ttl_days: 0\n"
    yaml_path = write_config_yaml(tmp_path, content)
    config = load_yaml_config(yaml_path)
    assert config.held_package_ttl_days == 0


def test_top_level_held_package_ttl_days_rejects_negative(tmp_path: Path) -> None:
    """Negative values are rejected — only `>= 0` is allowed."""
    content = DEFAULT_CONFIG_YAML + "held_package_ttl_days: -1\n"
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="held_package_ttl_days"):
        load_yaml_config(yaml_path)


def test_top_level_held_package_ttl_days_rejects_non_int(tmp_path: Path) -> None:
    """Floats and strings are rejected — the key is strictly an int."""
    content = DEFAULT_CONFIG_YAML + "held_package_ttl_days: 7.5\n"
    yaml_path = write_config_yaml(tmp_path, content)
    with pytest.raises(YamlConfigError, match="held_package_ttl_days"):
        load_yaml_config(yaml_path)


# ---- AC1: legacy key fallback + deprecation warning ---------------------


def test_legacy_held_retention_days_emits_deprecation_warning(
    tmp_path: Path,
) -> None:
    """Story 3.4's key still works; the loader warns the author to migrate."""
    content = DEFAULT_CONFIG_YAML + textwrap.dedent(
        """\
        fabrication:
          claim_extraction:
            timeout_seconds: 60.0
          semantic_method: rule_based
          semantic_threshold: 0.65
          held_retention_days: 10
        """
    )
    yaml_path = write_config_yaml(tmp_path, content)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        config = load_yaml_config(yaml_path)
    # The legacy value is honored when the new key is absent.
    assert config.held_package_ttl_days == 10
    deprecation_warnings = [
        w for w in captured if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 1
    message = str(deprecation_warnings[0].message)
    assert "fabrication.held_retention_days" in message
    assert "held_package_ttl_days" in message


def test_no_deprecation_warning_when_only_new_key_present(tmp_path: Path) -> None:
    """When the author uses the new key only, no warning is emitted."""
    content = DEFAULT_CONFIG_YAML + "held_package_ttl_days: 3\n"
    yaml_path = write_config_yaml(tmp_path, content)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        config = load_yaml_config(yaml_path)
    assert config.held_package_ttl_days == 3
    assert [
        w for w in captured if issubclass(w.category, DeprecationWarning)
    ] == []


def test_no_deprecation_warning_when_neither_key_present(tmp_path: Path) -> None:
    """A bare config (Story 2.2's shape) loads cleanly with default=7."""
    yaml_path = write_config_yaml(tmp_path, DEFAULT_CONFIG_YAML)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        config = load_yaml_config(yaml_path)
    assert config.held_package_ttl_days == 7
    assert [
        w for w in captured if issubclass(w.category, DeprecationWarning)
    ] == []


def test_committed_config_yaml_has_new_top_level_key() -> None:
    """The repo's committed config.yaml ships the new top-level key (AC1)."""
    from jobhunter.config import CONFIG_YAML_PATH

    config = load_yaml_config(CONFIG_YAML_PATH)
    assert config.held_package_ttl_days == 7
