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
    "ContentLossConfig",
    "CostConfig",
    "DriftConfig",
    "FabricationConfig",
    "KeywordStuffingChannels",
    "KeywordStuffingConfig",
    "OnlineJobsPhRedFlags",
    "OutputConfig",
    "ProposalConfig",
    "PromptsConfig",
    "RedFlagsConfig",
    "UpworkRedFlags",
    "YamlConfig",
    "YamlConfigError",
    "load_yaml_config",
    "resolve_keyword_stuffing_thresholds",
]


# Case-insensitive match for secret-shaped keys at any nesting depth: any key
# ending in `_api_key`, `_token`, `_secret`, or starting with `secret_`.
_SECRET_KEY_PATTERN = re.compile(
    r"(?:^secret_|_api_key$|_token$|_secret$)",
    re.IGNORECASE,
)

_REQUIRED_TOP_LEVEL_SECTIONS = ("cost", "output", "prompts", "red_flags")

# Story 4.3: enumerated matcher modes for the content-loss check. Validated at
# config-load time so a typo in `config.yaml` fails fast rather than surfacing
# as an opaque dispatch error mid-pipeline.
_VALID_RELEVANCE_MATCHERS: frozenset[str] = frozenset(
    {"tag_overlap", "keyword_overlap", "embedding_distance"}
)
_VALID_PRESENCE_MATCHERS: frozenset[str] = frozenset({"substring", "semantic"})


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
    """Story 3.1 owns `claim_extraction`; Story 3.3 populates `semantic_*` keys."""

    claim_extraction: ClaimExtractionConfig
    # Story 3.3: `semantic_method` ∈ {"rule_based", "embedding_cosine"}.
    # v1 default is `rule_based` (threshold 0.65) because the locked-in
    # provider (Anthropic) does not expose an embeddings endpoint. See
    # `_bmad-output/decisions/llm-provider.md` "Story 3.3" for the rationale
    # and the upgrade path.
    semantic_method: str
    semantic_threshold: Decimal
    # Story 3.4: how long a held package lingers on disk before the next
    # pipeline run sweeps it (default 7 days, per the AC3 retention window).
    held_retention_days: int = 7


@dataclass(frozen=True)
class ContentLossConfig:
    """Story 4.3 tunables for the Epic-4 content-loss drift check."""

    # Matcher-mode dispatch keys. Enum-validated at config-load time so a
    # typo doesn't sneak through to the matcher. Names are stable — Story 4.4
    # consumes the same strings via `config_snapshot` in `package.drift.json`.
    relevance_matcher: str
    presence_matcher: str
    # Tag-overlap mode threshold (the v1 default-path tunable).
    tag_overlap_min: int
    # Keyword-overlap mode threshold; consulted only when
    # `relevance_matcher == "keyword_overlap"`.
    keyword_overlap_pct: float
    # Embedding-distance mode threshold; consulted only when
    # `relevance_matcher == "embedding_distance"` (v1 raises before use).
    embedding_distance_max: float
    # Semantic-presence cosine cutoff; consulted only when
    # `presence_matcher == "semantic"` (v1 raises before use).
    presence_semantic_threshold: float
    # Story 4.3 AC1 retains the reason-code enumeration in yaml so a future
    # story can extend the set without a code change (the matcher's
    # `VALID_DROP_REASONS` is the source of truth for v1).
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class DriftConfig:
    """Top-level `drift` section (Story 4.3); future drift dimensions nest here."""

    content_loss: ContentLossConfig


# Story 5.3: per-channel override sub-block under `keyword_stuffing.channels`.
# Each board carries any subset of the five global thresholds; missing keys
# fall back to the global default via `resolve_keyword_stuffing_thresholds`.
# A "frozen mapping" shape (per-board dicts) keeps the config faithful to the
# AC2 shape (`channels.<board>` is itself a mapping) without inventing one
# dataclass per board.
@dataclass(frozen=True)
class KeywordStuffingChannels:
    """Per-channel override dicts (Story 5.3 AC3); each value is a subset of the global thresholds."""

    upwork: dict[str, Any]
    linkedin: dict[str, Any]
    onlinejobs_ph: dict[str, Any]
    other: dict[str, Any]


@dataclass(frozen=True)
class KeywordStuffingConfig:
    """Story 5.3 tunables for the Epic-5 keyword-stuffing drift check.

    The five global thresholds mirror Stories 5.1 + 5.2's hard-coded defaults
    one-for-one; `channels` holds optional per-board overrides that
    shallow-merge over the globals at resolution time. A board with `{}` is
    a structural placeholder — present but with no overrides — so a
    `keyword_stuffing.channels.upwork:` block can be uncommented field-by-field
    without re-introducing the channels key wholesale.
    """

    max_density_pct: float
    max_repetitions_per_artifact: int
    dump_paragraph_min_tokens: int
    dump_paragraph_max_keyword_ratio: float
    comma_run_min_tokens: int
    channels: KeywordStuffingChannels


@dataclass(frozen=True)
class YamlConfig:
    cost: CostConfig
    output: OutputConfig
    prompts: PromptsConfig
    red_flags: RedFlagsConfig
    proposal: ProposalConfig
    fabrication: FabricationConfig
    drift: DriftConfig
    keyword_stuffing: KeywordStuffingConfig


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
        "semantic_method": "rule_based",
        "semantic_threshold": Decimal("0.65"),
        "held_retention_days": 7,
    },
    "drift": {
        "content_loss": {
            "relevance_matcher": "tag_overlap",
            "tag_overlap_min": 1,
            "keyword_overlap_pct": 0.20,
            "embedding_distance_max": 0.35,
            "presence_matcher": "substring",
            "presence_semantic_threshold": 0.80,
            "reason_codes": ["irrelevant_to_jd", "silently_lost"],
        },
    },
    # Story 5.3: keyword-stuffing thresholds + per-channel overrides. The
    # globals mirror Story 5.1/5.2's hard-coded defaults one-for-one. Channels
    # default to empty `{}` so the shipped config does not silently loosen any
    # board's behavior — the author opts in by uncommenting overrides.
    "keyword_stuffing": {
        "max_density_pct": 1.5,
        "max_repetitions_per_artifact": 3,
        "dump_paragraph_min_tokens": 15,
        "dump_paragraph_max_keyword_ratio": 0.30,
        "comma_run_min_tokens": 4,
        "channels": {
            "upwork": {},
            "linkedin": {},
            "onlinejobs_ph": {},
            "other": {},
        },
    },
}

# Story 5.3: the five global thresholds that can also appear inside a
# per-channel override block. `channels` is intentionally excluded — a
# channel-override cannot recursively declare its own channels.
_KEYWORD_STUFFING_GLOBAL_KEYS: frozenset[str] = frozenset(
    {
        "max_density_pct",
        "max_repetitions_per_artifact",
        "dump_paragraph_min_tokens",
        "dump_paragraph_max_keyword_ratio",
        "comma_run_min_tokens",
    }
)

# The fixed set of channel sub-block names. Mirrors
# `board_classifier.ALLOWED_SOURCE_BOARDS` value-for-value so a channel name
# in `config.yaml` is always a valid `Classification.source_board`. Note: the
# Story 5.3 spec text uses `ojph` as shorthand; the canonical board value in
# the codebase (and in `Classification.source_board`) is `onlinejobs_ph`, so
# we use the canonical form here for symmetry with the classifier output.
_KEYWORD_STUFFING_CHANNEL_NAMES: frozenset[str] = frozenset(
    {"upwork", "linkedin", "onlinejobs_ph", "other"}
)

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
    drift = _parse_drift(parsed.get("drift"))
    keyword_stuffing = _parse_keyword_stuffing(parsed.get("keyword_stuffing"))

    return YamlConfig(
        cost=cost,
        output=output,
        prompts=prompts,
        red_flags=red_flags,
        proposal=proposal,
        fabrication=fabrication,
        drift=drift,
        keyword_stuffing=keyword_stuffing,
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


def _parse_drift(node: Any) -> DriftConfig:
    """Build the Story 4.3 `drift.content_loss` section, applying defaults."""
    content_loss_defaults = _DEFAULTS["drift"]["content_loss"]

    if node is None:
        return DriftConfig(
            content_loss=ContentLossConfig(
                relevance_matcher=str(content_loss_defaults["relevance_matcher"]),
                presence_matcher=str(content_loss_defaults["presence_matcher"]),
                tag_overlap_min=int(content_loss_defaults["tag_overlap_min"]),
                keyword_overlap_pct=float(content_loss_defaults["keyword_overlap_pct"]),
                embedding_distance_max=float(content_loss_defaults["embedding_distance_max"]),
                presence_semantic_threshold=float(
                    content_loss_defaults["presence_semantic_threshold"]
                ),
                reason_codes=tuple(content_loss_defaults["reason_codes"]),
            )
        )

    node = _require_mapping(node, "drift")
    _reject_unknown_keys(node, frozenset({"content_loss"}), "drift")
    cl_node = node.get("content_loss", content_loss_defaults)
    cl_node = _require_mapping(cl_node, "drift.content_loss")
    _reject_unknown_keys(
        cl_node, frozenset(content_loss_defaults.keys()), "drift.content_loss"
    )

    relevance_matcher = _coerce_non_empty_str(
        cl_node.get("relevance_matcher", content_loss_defaults["relevance_matcher"]),
        "drift.content_loss.relevance_matcher",
    )
    if relevance_matcher not in _VALID_RELEVANCE_MATCHERS:
        raise YamlConfigError(
            f"drift.content_loss.relevance_matcher must be one of "
            f"{sorted(_VALID_RELEVANCE_MATCHERS)}, got {relevance_matcher!r}"
        )
    presence_matcher = _coerce_non_empty_str(
        cl_node.get("presence_matcher", content_loss_defaults["presence_matcher"]),
        "drift.content_loss.presence_matcher",
    )
    if presence_matcher not in _VALID_PRESENCE_MATCHERS:
        raise YamlConfigError(
            f"drift.content_loss.presence_matcher must be one of "
            f"{sorted(_VALID_PRESENCE_MATCHERS)}, got {presence_matcher!r}"
        )

    reason_codes_value = cl_node.get(
        "reason_codes", content_loss_defaults["reason_codes"]
    )
    if not isinstance(reason_codes_value, list) or not all(
        isinstance(rc, str) and rc for rc in reason_codes_value
    ):
        raise YamlConfigError(
            "drift.content_loss.reason_codes must be a list of non-empty strings"
        )

    return DriftConfig(
        content_loss=ContentLossConfig(
            relevance_matcher=relevance_matcher,
            presence_matcher=presence_matcher,
            tag_overlap_min=_coerce_positive_int(
                cl_node.get("tag_overlap_min", content_loss_defaults["tag_overlap_min"]),
                "drift.content_loss.tag_overlap_min",
            ),
            keyword_overlap_pct=_coerce_positive_float(
                cl_node.get(
                    "keyword_overlap_pct", content_loss_defaults["keyword_overlap_pct"]
                ),
                "drift.content_loss.keyword_overlap_pct",
            ),
            embedding_distance_max=_coerce_positive_float(
                cl_node.get(
                    "embedding_distance_max",
                    content_loss_defaults["embedding_distance_max"],
                ),
                "drift.content_loss.embedding_distance_max",
            ),
            presence_semantic_threshold=_coerce_positive_float(
                cl_node.get(
                    "presence_semantic_threshold",
                    content_loss_defaults["presence_semantic_threshold"],
                ),
                "drift.content_loss.presence_semantic_threshold",
            ),
            reason_codes=tuple(reason_codes_value),
        )
    )


def _parse_keyword_stuffing(node: Any) -> KeywordStuffingConfig:
    """Build the Story 5.3 `keyword_stuffing` section, applying defaults.

    The top-level section is optional (Story 5.3 AC2 fallback): when absent,
    Stories 5.1/5.2's hard-coded thresholds apply and every channel block is
    empty. When present, the five global thresholds + `channels.<board>`
    overrides are validated; unknown keys (typos) raise so the author cannot
    silently end up with the default. Each per-channel override block is
    itself a mapping whose keys are a strict subset of the five globals.
    """
    defaults = _DEFAULTS["keyword_stuffing"]
    if node is None:
        return _keyword_stuffing_from_defaults(defaults)

    node = _require_mapping(node, "keyword_stuffing")
    allowed_top_keys = _KEYWORD_STUFFING_GLOBAL_KEYS | {"channels"}
    _reject_unknown_keys(node, frozenset(allowed_top_keys), "keyword_stuffing")

    max_density_pct = _coerce_positive_float(
        node.get("max_density_pct", defaults["max_density_pct"]),
        "keyword_stuffing.max_density_pct",
    )
    max_repetitions_per_artifact = _coerce_positive_int(
        node.get(
            "max_repetitions_per_artifact",
            defaults["max_repetitions_per_artifact"],
        ),
        "keyword_stuffing.max_repetitions_per_artifact",
    )
    dump_paragraph_min_tokens = _coerce_positive_int(
        node.get(
            "dump_paragraph_min_tokens",
            defaults["dump_paragraph_min_tokens"],
        ),
        "keyword_stuffing.dump_paragraph_min_tokens",
    )
    dump_paragraph_max_keyword_ratio = _coerce_positive_float(
        node.get(
            "dump_paragraph_max_keyword_ratio",
            defaults["dump_paragraph_max_keyword_ratio"],
        ),
        "keyword_stuffing.dump_paragraph_max_keyword_ratio",
    )
    comma_run_min_tokens = _coerce_positive_int(
        node.get(
            "comma_run_min_tokens",
            defaults["comma_run_min_tokens"],
        ),
        "keyword_stuffing.comma_run_min_tokens",
    )

    channels_node = node.get("channels", defaults["channels"])
    channels = _parse_keyword_stuffing_channels(channels_node)

    return KeywordStuffingConfig(
        max_density_pct=max_density_pct,
        max_repetitions_per_artifact=max_repetitions_per_artifact,
        dump_paragraph_min_tokens=dump_paragraph_min_tokens,
        dump_paragraph_max_keyword_ratio=dump_paragraph_max_keyword_ratio,
        comma_run_min_tokens=comma_run_min_tokens,
        channels=channels,
    )


def _keyword_stuffing_from_defaults(
    defaults: dict[str, Any],
) -> KeywordStuffingConfig:
    """Build a `KeywordStuffingConfig` from the bare `_DEFAULTS` mapping."""
    return KeywordStuffingConfig(
        max_density_pct=float(defaults["max_density_pct"]),
        max_repetitions_per_artifact=int(defaults["max_repetitions_per_artifact"]),
        dump_paragraph_min_tokens=int(defaults["dump_paragraph_min_tokens"]),
        dump_paragraph_max_keyword_ratio=float(
            defaults["dump_paragraph_max_keyword_ratio"]
        ),
        comma_run_min_tokens=int(defaults["comma_run_min_tokens"]),
        channels=KeywordStuffingChannels(
            upwork={},
            linkedin={},
            onlinejobs_ph={},
            other={},
        ),
    )


def _parse_keyword_stuffing_channels(node: Any) -> KeywordStuffingChannels:
    """Build a `KeywordStuffingChannels` from the optional `channels:` mapping.

    Each per-channel override block is an arbitrary subset of the five global
    thresholds, validated key-by-key. An empty `{}` block is allowed (the
    shipped config's default) and produces an empty override dict.
    """
    node = _require_mapping(node, "keyword_stuffing.channels")
    _reject_unknown_keys(
        node,
        frozenset(_KEYWORD_STUFFING_CHANNEL_NAMES),
        "keyword_stuffing.channels",
    )
    return KeywordStuffingChannels(
        upwork=_parse_channel_overrides(node.get("upwork"), "upwork"),
        linkedin=_parse_channel_overrides(node.get("linkedin"), "linkedin"),
        onlinejobs_ph=_parse_channel_overrides(
            node.get("onlinejobs_ph"), "onlinejobs_ph"
        ),
        other=_parse_channel_overrides(node.get("other"), "other"),
    )


def _parse_channel_overrides(node: Any, channel: str) -> dict[str, Any]:
    """Validate + coerce per-key the optional override block for *channel*.

    Returns `{}` when *node* is `None` or `{}`. Each present key must be one
    of the five global thresholds AND must coerce to a positive number under
    the same rules as the global parser.
    """
    if node is None:
        return {}
    node = _require_mapping(node, f"keyword_stuffing.channels.{channel}")
    _reject_unknown_keys(
        node,
        frozenset(_KEYWORD_STUFFING_GLOBAL_KEYS),
        f"keyword_stuffing.channels.{channel}",
    )
    result: dict[str, Any] = {}
    if "max_density_pct" in node:
        result["max_density_pct"] = _coerce_positive_float(
            node["max_density_pct"],
            f"keyword_stuffing.channels.{channel}.max_density_pct",
        )
    if "max_repetitions_per_artifact" in node:
        result["max_repetitions_per_artifact"] = _coerce_positive_int(
            node["max_repetitions_per_artifact"],
            f"keyword_stuffing.channels.{channel}.max_repetitions_per_artifact",
        )
    if "dump_paragraph_min_tokens" in node:
        result["dump_paragraph_min_tokens"] = _coerce_positive_int(
            node["dump_paragraph_min_tokens"],
            f"keyword_stuffing.channels.{channel}.dump_paragraph_min_tokens",
        )
    if "dump_paragraph_max_keyword_ratio" in node:
        result["dump_paragraph_max_keyword_ratio"] = _coerce_positive_float(
            node["dump_paragraph_max_keyword_ratio"],
            f"keyword_stuffing.channels.{channel}.dump_paragraph_max_keyword_ratio",
        )
    if "comma_run_min_tokens" in node:
        result["comma_run_min_tokens"] = _coerce_positive_int(
            node["comma_run_min_tokens"],
            f"keyword_stuffing.channels.{channel}.comma_run_min_tokens",
        )
    return result


def resolve_keyword_stuffing_thresholds(
    config: KeywordStuffingConfig, channel: str
) -> dict[str, Any]:
    """Shallow-merge per-channel overrides over global defaults (Story 5.3 AC3).

    Returns the effective threshold dict the matcher consumes AND the snapshot
    persisted under `package.drift.json.keyword_stuffing.thresholds_applied`
    (AC1). Channel names outside the allowed set degrade gracefully to the
    global defaults — the same fallback shape an unrecognised
    `Classification.source_board` would produce — so a future board value
    cannot block the pipeline. The output ordering is fixed so the on-disk
    `thresholds_applied` block is diff-stable across runs.
    """
    globals_dict: dict[str, Any] = {
        "max_density_pct": config.max_density_pct,
        "max_repetitions_per_artifact": config.max_repetitions_per_artifact,
        "dump_paragraph_min_tokens": config.dump_paragraph_min_tokens,
        "dump_paragraph_max_keyword_ratio": config.dump_paragraph_max_keyword_ratio,
        "comma_run_min_tokens": config.comma_run_min_tokens,
    }
    overrides_for_channel: dict[str, Any]
    if channel == "upwork":
        overrides_for_channel = dict(config.channels.upwork)
    elif channel == "linkedin":
        overrides_for_channel = dict(config.channels.linkedin)
    elif channel == "onlinejobs_ph":
        overrides_for_channel = dict(config.channels.onlinejobs_ph)
    elif channel == "other":
        overrides_for_channel = dict(config.channels.other)
    else:
        # Unknown channel -> fall back to globals (no override applied).
        overrides_for_channel = {}
    globals_dict.update(overrides_for_channel)
    return globals_dict


def _parse_fabrication(node: Any) -> FabricationConfig:
    """Build the Story 3.1 + 3.3 + 3.4 `fabrication` section, applying defaults."""
    defaults = _DEFAULTS["fabrication"]
    if node is None:
        return FabricationConfig(
            claim_extraction=ClaimExtractionConfig(
                timeout_seconds=float(defaults["claim_extraction"]["timeout_seconds"]),
            ),
            semantic_method=str(defaults["semantic_method"]),
            semantic_threshold=Decimal(str(defaults["semantic_threshold"])),
            held_retention_days=int(defaults["held_retention_days"]),
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
        held_retention_days=_coerce_positive_int(
            node.get("held_retention_days", defaults["held_retention_days"]),
            "fabrication.held_retention_days",
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
