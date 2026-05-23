"""Tunable configuration loader (Story 2.2).

`config.yaml` holds all tunable behavior — drift-check thresholds, prompt-
template paths, cost cap, output directory, JD red-flag floors. Secrets live
in `.env` and are loaded by `jobhunter.runtime_config`; this module rejects
secret-shaped keys so the segregation is enforced structurally.

Precedence note: if `MONTHLY_SPEND_CAP_USD` is set in the environment, the
env value wins over `cost.monthly_cap_usd` at the `runtime_config` level —
this module just returns the yaml defaults.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from jobhunter.config import CONFIG_YAML_PATH


__all__ = [
    "ClaimExtractionConfig",
    "CostConfig",
    "FabricationConfig",
    "OnlineJobsPhRedFlags",
    "OutputConfig",
    "ProposalConfig",
    "PromptsConfig",
    "RedFlagsConfig",
    "UpworkRedFlags",
    "YamlConfig",
    "YamlConfigError",
    "load_yaml_config",
]


# Case-insensitive match for secret-shaped keys at any nesting depth: any key
# ending in `_api_key`, `_token`, `_secret`, or starting with `secret_`.
_SECRET_KEY_PATTERN = re.compile(
    r"(?:^secret_|_api_key$|_token$|_secret$)",
    re.IGNORECASE,
)

_REQUIRED_TOP_LEVEL_SECTIONS = ("cost", "output", "prompts", "red_flags")


class YamlConfigError(ValueError):
    """Raised when `config.yaml` is missing, malformed, or contains secrets."""


@dataclass(frozen=True)
class CostConfig:
    monthly_cap_usd: Decimal
    per_app_max_usd: Decimal


@dataclass(frozen=True)
class OutputConfig:
    dir: str


@dataclass(frozen=True)
class PromptsConfig:
    cv: str
    cover_letter: str
    upwork_proposal: str


@dataclass(frozen=True)
class UpworkRedFlags:
    budget_floor_usd_hourly: int
    budget_floor_usd_fixed: int


@dataclass(frozen=True)
class OnlineJobsPhRedFlags:
    rate_floor_usd_monthly: int


@dataclass(frozen=True)
class RedFlagsConfig:
    upwork: UpworkRedFlags
    onlinejobs_ph: OnlineJobsPhRedFlags


@dataclass(frozen=True)
class ProposalConfig:
    max_words: int


@dataclass(frozen=True)
class ClaimExtractionConfig:
    """Per-call timeout for the Story 3.1 atomic-claim extractor."""

    timeout_seconds: float


@dataclass(frozen=True)
class FabricationConfig:
    """Story 3.1 owns `claim_extraction`; Story 3.3 will populate `semantic_*` keys."""

    claim_extraction: ClaimExtractionConfig
    # TODO(Story 3.3): wire `semantic_method` (`embedding_cosine` | `rule_based`)
    # and `semantic_threshold` (default 0.82 / 0.65) once the semantic matcher
    # lands. Stubbed strings for now so the yaml schema is forward-compatible.
    semantic_method: str
    semantic_threshold: Decimal


@dataclass(frozen=True)
class YamlConfig:
    cost: CostConfig
    output: OutputConfig
    prompts: PromptsConfig
    red_flags: RedFlagsConfig
    proposal: ProposalConfig
    fabrication: FabricationConfig


_DEFAULTS: dict[str, dict[str, Any]] = {
    "cost": {
        "monthly_cap_usd": Decimal("25"),
        "per_app_max_usd": Decimal("0.25"),
    },
    "output": {
        "dir": "out",
    },
    "prompts": {
        "cv": "prompts/cv.v1.md",
        "cover_letter": "prompts/cover_letter.v1.md",
        "upwork_proposal": "prompts/upwork_proposal.v1.md",
    },
    "red_flags": {
        "upwork": {
            "budget_floor_usd_hourly": 25,
            "budget_floor_usd_fixed": 500,
        },
        "onlinejobs_ph": {
            "rate_floor_usd_monthly": 600,
        },
    },
    "proposal": {
        "max_words": 250,
    },
    "fabrication": {
        "claim_extraction": {
            "timeout_seconds": Decimal("60.0"),
        },
        "semantic_method": "embedding_cosine",
        "semantic_threshold": Decimal("0.82"),
    },
}

_ALLOWED_TOP_LEVEL_KEYS = frozenset(_DEFAULTS.keys())
_ALLOWED_RED_FLAG_BOARDS = frozenset(_DEFAULTS["red_flags"].keys())


def load_yaml_config(path: Path | None = None) -> YamlConfig:
    yaml_path = CONFIG_YAML_PATH if path is None else path

    if not yaml_path.is_file():
        raise YamlConfigError(
            f"config.yaml not found at {yaml_path}; "
            f"copy the committed default from the repo root"
        )

    try:
        raw_text = yaml_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise YamlConfigError(f"could not read {yaml_path}: {exc}") from exc

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise YamlConfigError(f"malformed yaml in {yaml_path}: {exc}") from exc

    if parsed is None or not isinstance(parsed, dict):
        raise YamlConfigError(
            f"{yaml_path} must contain a top-level mapping, got {type(parsed).__name__}"
        )

    _reject_secret_keys(parsed, path_prefix="")

    for section in _REQUIRED_TOP_LEVEL_SECTIONS:
        if section not in parsed:
            raise YamlConfigError(f"missing required key: {section}")

    extra_keys = set(parsed.keys()) - _ALLOWED_TOP_LEVEL_KEYS
    if extra_keys:
        raise YamlConfigError(
            f"unknown top-level key(s): {', '.join(sorted(extra_keys))}"
        )

    cost = _parse_cost(parsed["cost"])
    output = _parse_output(parsed["output"])
    prompts = _parse_prompts(parsed["prompts"])
    red_flags = _parse_red_flags(parsed["red_flags"])
    proposal = _parse_proposal(parsed.get("proposal"))
    fabrication = _parse_fabrication(parsed.get("fabrication"))

    return YamlConfig(
        cost=cost,
        output=output,
        prompts=prompts,
        red_flags=red_flags,
        proposal=proposal,
        fabrication=fabrication,
    )


def _reject_secret_keys(node: Any, *, path_prefix: str) -> None:
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if isinstance(key, str) and _SECRET_KEY_PATTERN.search(key):
            full_path = f"{path_prefix}{key}" if path_prefix else key
            raise YamlConfigError(
                f"secret-shaped key not allowed in config.yaml: {full_path}; "
                f"move secrets to .env"
            )
        if isinstance(value, dict):
            nested_prefix = f"{path_prefix}{key}." if path_prefix else f"{key}."
            _reject_secret_keys(value, path_prefix=nested_prefix)


def _require_mapping(node: Any, key_path: str) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise YamlConfigError(
            f"{key_path} must be a mapping, got {type(node).__name__}"
        )
    return node


def _reject_unknown_keys(node: dict[str, Any], allowed: frozenset[str], key_path: str) -> None:
    extras = set(node.keys()) - allowed
    if extras:
        raise YamlConfigError(
            f"unknown key(s) under {key_path}: {', '.join(sorted(extras))}"
        )


def _parse_cost(node: Any) -> CostConfig:
    node = _require_mapping(node, "cost")
    defaults = _DEFAULTS["cost"]
    _reject_unknown_keys(node, frozenset(defaults.keys()), "cost")
    return CostConfig(
        monthly_cap_usd=_coerce_positive_decimal(
            node.get("monthly_cap_usd", defaults["monthly_cap_usd"]),
            "cost.monthly_cap_usd",
        ),
        per_app_max_usd=_coerce_positive_decimal(
            node.get("per_app_max_usd", defaults["per_app_max_usd"]),
            "cost.per_app_max_usd",
        ),
    )


def _parse_output(node: Any) -> OutputConfig:
    node = _require_mapping(node, "output")
    defaults = _DEFAULTS["output"]
    _reject_unknown_keys(node, frozenset(defaults.keys()), "output")
    return OutputConfig(
        dir=_coerce_non_empty_str(node.get("dir", defaults["dir"]), "output.dir"),
    )


def _parse_prompts(node: Any) -> PromptsConfig:
    node = _require_mapping(node, "prompts")
    defaults = _DEFAULTS["prompts"]
    _reject_unknown_keys(node, frozenset(defaults.keys()), "prompts")
    return PromptsConfig(
        cv=_coerce_non_empty_str(node.get("cv", defaults["cv"]), "prompts.cv"),
        cover_letter=_coerce_non_empty_str(
            node.get("cover_letter", defaults["cover_letter"]),
            "prompts.cover_letter",
        ),
        upwork_proposal=_coerce_non_empty_str(
            node.get("upwork_proposal", defaults["upwork_proposal"]),
            "prompts.upwork_proposal",
        ),
    )


def _parse_red_flags(node: Any) -> RedFlagsConfig:
    node = _require_mapping(node, "red_flags")
    _reject_unknown_keys(node, _ALLOWED_RED_FLAG_BOARDS, "red_flags")

    upwork_defaults = _DEFAULTS["red_flags"]["upwork"]
    upwork_node = _require_mapping(
        node.get("upwork", upwork_defaults), "red_flags.upwork"
    )
    _reject_unknown_keys(
        upwork_node, frozenset(upwork_defaults.keys()), "red_flags.upwork"
    )
    upwork = UpworkRedFlags(
        budget_floor_usd_hourly=_coerce_positive_int(
            upwork_node.get(
                "budget_floor_usd_hourly", upwork_defaults["budget_floor_usd_hourly"]
            ),
            "red_flags.upwork.budget_floor_usd_hourly",
        ),
        budget_floor_usd_fixed=_coerce_positive_int(
            upwork_node.get(
                "budget_floor_usd_fixed", upwork_defaults["budget_floor_usd_fixed"]
            ),
            "red_flags.upwork.budget_floor_usd_fixed",
        ),
    )

    ojph_defaults = _DEFAULTS["red_flags"]["onlinejobs_ph"]
    ojph_node = _require_mapping(
        node.get("onlinejobs_ph", ojph_defaults), "red_flags.onlinejobs_ph"
    )
    _reject_unknown_keys(
        ojph_node, frozenset(ojph_defaults.keys()), "red_flags.onlinejobs_ph"
    )
    onlinejobs_ph = OnlineJobsPhRedFlags(
        rate_floor_usd_monthly=_coerce_positive_int(
            ojph_node.get(
                "rate_floor_usd_monthly", ojph_defaults["rate_floor_usd_monthly"]
            ),
            "red_flags.onlinejobs_ph.rate_floor_usd_monthly",
        ),
    )

    return RedFlagsConfig(upwork=upwork, onlinejobs_ph=onlinejobs_ph)


def _parse_proposal(node: Any) -> ProposalConfig:
    defaults = _DEFAULTS["proposal"]
    if node is None:
        return ProposalConfig(max_words=int(defaults["max_words"]))
    node = _require_mapping(node, "proposal")
    _reject_unknown_keys(node, frozenset(defaults.keys()), "proposal")
    return ProposalConfig(
        max_words=_coerce_positive_int(
            node.get("max_words", defaults["max_words"]),
            "proposal.max_words",
        ),
    )


def _parse_fabrication(node: Any) -> FabricationConfig:
    """Build the Story 3.1 + 3.3 `fabrication` section, applying defaults."""
    defaults = _DEFAULTS["fabrication"]
    if node is None:
        return FabricationConfig(
            claim_extraction=ClaimExtractionConfig(
                timeout_seconds=float(defaults["claim_extraction"]["timeout_seconds"]),
            ),
            semantic_method=str(defaults["semantic_method"]),
            semantic_threshold=Decimal(str(defaults["semantic_threshold"])),
        )
    node = _require_mapping(node, "fabrication")
    _reject_unknown_keys(node, frozenset(defaults.keys()), "fabrication")

    extraction_defaults = defaults["claim_extraction"]
    extraction_node = node.get("claim_extraction", extraction_defaults)
    extraction_node = _require_mapping(
        extraction_node, "fabrication.claim_extraction"
    )
    _reject_unknown_keys(
        extraction_node,
        frozenset(extraction_defaults.keys()),
        "fabrication.claim_extraction",
    )
    timeout_seconds = _coerce_positive_float(
        extraction_node.get(
            "timeout_seconds", extraction_defaults["timeout_seconds"]
        ),
        "fabrication.claim_extraction.timeout_seconds",
    )

    return FabricationConfig(
        claim_extraction=ClaimExtractionConfig(timeout_seconds=timeout_seconds),
        semantic_method=_coerce_non_empty_str(
            node.get("semantic_method", defaults["semantic_method"]),
            "fabrication.semantic_method",
        ),
        semantic_threshold=_coerce_positive_decimal(
            node.get("semantic_threshold", defaults["semantic_threshold"]),
            "fabrication.semantic_threshold",
        ),
    )


def _coerce_positive_float(value: Any, key_path: str) -> float:
    if isinstance(value, bool):
        raise YamlConfigError(f"{key_path} must be a positive number")
    if isinstance(value, Decimal):
        result = float(value)
    elif isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError as exc:
            raise YamlConfigError(
                f"{key_path} must be a positive number"
            ) from exc
    else:
        raise YamlConfigError(
            f"{key_path} must be a positive number, got {type(value).__name__}"
        )
    import math as _math

    if not _math.isfinite(result) or result <= 0:
        raise YamlConfigError(f"{key_path} must be a positive number")
    return result


def _coerce_positive_decimal(value: Any, key_path: str) -> Decimal:
    if isinstance(value, bool):
        raise YamlConfigError(f"{key_path} must be a positive number")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float, str)):
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise YamlConfigError(
                f"{key_path} must be a positive number"
            ) from exc
    else:
        raise YamlConfigError(
            f"{key_path} must be a positive number, got {type(value).__name__}"
        )
    if not result.is_finite() or result <= 0:
        raise YamlConfigError(f"{key_path} must be a positive number")
    return result


def _coerce_positive_int(value: Any, key_path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise YamlConfigError(
            f"{key_path} must be a positive integer, got {type(value).__name__}"
        )
    if value <= 0:
        raise YamlConfigError(f"{key_path} must be a positive integer")
    return value


def _coerce_non_empty_str(value: Any, key_path: str) -> str:
    if not isinstance(value, str):
        raise YamlConfigError(
            f"{key_path} must be a string, got {type(value).__name__}"
        )
    if not value.strip():
        raise YamlConfigError(f"{key_path} must be a non-empty string")
    return value
