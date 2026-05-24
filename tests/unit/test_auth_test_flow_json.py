"""Structural + FR11 + hosting-agnostic guards for `n8n/auth-test.json` (Story 7.1).

Covers AC3 (FR11 statement at the top of every flow JSON; no platform-login
material; no browser-automation nodes) and AC4 (hosting-agnostic — only
HTTP / Cron / standard transform nodes; only `INGEST_BASE_URL` and
`INGEST_SHARED_TOKEN` environment variables; the token value never appears
literally in the flow JSON).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTH_TEST_FLOW = PROJECT_ROOT / "n8n" / "auth-test.json"


# AC3 + AC4 use a frozen forbidden-substring list. Keep it explicit so any
# future drift surfaces in a single diff site.
_FORBIDDEN_NODE_TYPES = frozenset(
    {
        "n8n-nodes-base.executeCommand",
        "n8n-nodes-base.ssh",
        "n8n-nodes-base.shell",
        "n8n-nodes-base.puppeteer",
        "n8n-nodes-base.selenium",
        "n8n-nodes-base.browserless",
    }
)
_FORBIDDEN_HOSTNAMES = ("upwork.com", "linkedin.com", "onlinejobs.ph")


@pytest.fixture(scope="module")
def flow() -> dict:
    return json.loads(AUTH_TEST_FLOW.read_text(encoding="utf-8"))


# --- AC4: structural skeleton --------------------------------------------


def test_auth_test_flow_is_valid_json(flow) -> None:
    """The fixture loaded JSON — assert the top-level shape exists."""
    assert isinstance(flow, dict)


def test_auth_test_flow_has_required_top_level_fields(flow) -> None:
    """An n8n workflow export carries `name`, `nodes[]`, `connections{}`."""
    assert isinstance(flow.get("name"), str) and flow["name"]
    assert isinstance(flow.get("nodes"), list) and flow["nodes"]
    assert isinstance(flow.get("connections"), dict)


def test_auth_test_flow_nodes_carry_id_name_and_type(flow) -> None:
    """Each node must have `id`, `name`, `type` so n8n can import it."""
    for node in flow["nodes"]:
        assert isinstance(node, dict)
        assert isinstance(node.get("id"), str) and node["id"]
        assert isinstance(node.get("name"), str) and node["name"]
        assert isinstance(node.get("type"), str) and node["type"]


# --- AC3: FR11 statement at the top of every flow JSON --------------------


def test_auth_test_flow_carries_fr11_notes_block(flow) -> None:
    """AC3: the workflow-level `notes` field carries the FR11 statement verbatim."""
    notes = flow.get("notes")
    assert isinstance(notes, str) and notes, "n8n flow must carry a `notes` field"
    assert "FR11" in notes
    assert "MUST NOT log into" in notes
    for site in ("Upwork", "LinkedIn", "OnlineJobs.ph"):
        assert site in notes, f"FR11 notes must explicitly name {site}"
    assert "email-parse only" in notes


# --- AC3: no browser-automation nodes / no platform-login material -------


def test_auth_test_flow_uses_no_forbidden_node_types(flow) -> None:
    """AC4: only HTTP / Cron / transform nodes. No Execute Command, no browser."""
    used_types = {node["type"] for node in flow["nodes"]}
    overlap = used_types & _FORBIDDEN_NODE_TYPES
    assert overlap == set(), f"flow uses forbidden node type(s): {sorted(overlap)}"


def test_auth_test_flow_uses_only_allowed_node_families(flow) -> None:
    """AC4: positive allowlist of node-type prefixes the flow may use."""
    allowed_prefixes = (
        "n8n-nodes-base.manualTrigger",
        "n8n-nodes-base.cron",
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
        "n8n-nodes-base.set",
        "n8n-nodes-base.if",
        "n8n-nodes-base.merge",
        "n8n-nodes-base.code",
    )
    for node in flow["nodes"]:
        node_type = node["type"]
        assert any(node_type.startswith(prefix) for prefix in allowed_prefixes), (
            f"node {node['name']!r} uses disallowed type {node_type!r}"
        )


def test_auth_test_flow_contains_no_platform_login_hostnames(flow) -> None:
    """AC3: no node may target upwork.com / linkedin.com / onlinejobs.ph in its parameters.

    The workflow-level `notes` field is allowed to name the sites verbatim
    (FR11 must call them out by name); only the node parameter graph is
    scanned so a Function/HTTP node can never embed a URL to one of them.
    """
    nodes_only = json.dumps(flow.get("nodes", []), ensure_ascii=False).lower()
    for host in _FORBIDDEN_HOSTNAMES:
        assert host not in nodes_only, (
            f"n8n/auth-test.json node graph contains forbidden hostname "
            f"{host!r} (FR11/FR44)."
        )


def test_auth_test_flow_does_not_embed_credentials_block(flow) -> None:
    """AC3: no node may carry a `credentials` block (the auth-test uses env vars only)."""
    for node in flow["nodes"]:
        assert "credentials" not in node, (
            f"node {node['name']!r} embeds a `credentials` block; "
            "auth-test must use env vars only (FR11)."
        )


# --- AC4: hosting-agnostic env var contract --------------------------------


def test_auth_test_flow_references_only_documented_env_vars() -> None:
    """AC4: the only n8n env vars used are `INGEST_BASE_URL` + `INGEST_SHARED_TOKEN`."""
    raw = AUTH_TEST_FLOW.read_text(encoding="utf-8")
    assert "INGEST_BASE_URL" in raw
    assert "INGEST_SHARED_TOKEN" in raw
    # Search for `$env.` references and confirm every one is in the allowlist.
    import re

    matches = re.findall(r"\$env\.([A-Z_][A-Z0-9_]*)", raw)
    allowed = {"INGEST_BASE_URL", "INGEST_SHARED_TOKEN"}
    for env_name in matches:
        assert env_name in allowed, (
            f"flow references undocumented env var ${env_name}; "
            f"allowed: {sorted(allowed)}"
        )


def test_auth_test_flow_token_value_is_not_baked_in() -> None:
    """AC1 / AC3: the token literal must never appear in the committed JSON."""
    raw = AUTH_TEST_FLOW.read_text(encoding="utf-8")
    # The token reference must be a template expression, not a literal.
    assert "Bearer {{$env.INGEST_SHARED_TOKEN}}" in raw or (
        "Bearer " in raw and "{{$env.INGEST_SHARED_TOKEN}}" in raw
    )
    # Common literal-token markers MUST be absent.
    for needle in ("Bearer sk-", "Bearer secret-", "Bearer eyJ", "INGEST_TOKEN="):
        assert needle not in raw, (
            f"flow appears to bake a literal token marker {needle!r}"
        )


def test_auth_test_flow_posts_to_api_paste_endpoint() -> None:
    """AC1: the HTTP Request node targets `${INGEST_BASE_URL}/api/paste`."""
    raw = AUTH_TEST_FLOW.read_text(encoding="utf-8")
    assert "/api/paste" in raw
    assert "$env.INGEST_BASE_URL" in raw


def test_auth_test_flow_minimal_body_matches_contract() -> None:
    """AC2: the auth-test body carries `jd_text`, `source`, `url`, `discovered_at`."""
    raw = AUTH_TEST_FLOW.read_text(encoding="utf-8")
    for field in ("jd_text", "source", "url", "discovered_at"):
        assert field in raw, f"auth-test body must include `{field}` (AC2 contract)"
