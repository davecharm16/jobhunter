"""Story-local fixtures for `tests/unit/test_yaml_config.py`.

`tests/conftest.py` is frozen by Story 2.2 boundaries, so any helpers needed by
the yaml-config tests live here. Import them directly from the test module.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

DEFAULT_CONFIG_YAML: str = textwrap.dedent(
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


def write_config_yaml(tmp_path: Path, content: str = DEFAULT_CONFIG_YAML) -> Path:
    """Write *content* to `<tmp_path>/config.yaml` and return the path."""
    target = tmp_path / "config.yaml"
    target.write_text(content, encoding="utf-8")
    return target
