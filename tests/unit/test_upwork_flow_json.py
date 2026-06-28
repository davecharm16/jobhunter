"""Structural + FR11 + hosting-agnostic guards for `n8n/upwork-search-flow.json` (Story 7.2).

Mirrors the test shape from `test_auth_test_flow_json.py` (Story 7.1):

- AC1: cron-triggered polling against Upwork's public RSS / public listing
  pages only — Cron trigger present, HTTP Request fetches the documented
  public-RSS URL, no Upwork session cookie / OAuth / login material.
- AC2: per-URL dedup — flow references `upwork.seen_urls` workflow static
  data, computes sha256 on canonical URL.
- AC3: each new JD POSTed to `${INGEST_BASE_URL}/api/paste` with the
  Story 7.1 contract (`source`, `jd_text`, `url`, `discovered_at`,
  `Authorization: Bearer ${INGEST_SHARED_TOKEN}`).
- AC4: hosting-agnostic — only the three documented env vars, no
  Execute Command, no browser-automation node, no `linkedin.com` URL,
  no `onlinejobs.ph` URL; FR11 statement at top of the flow JSON.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPWORK_FLOW = PROJECT_ROOT / "n8n" / "upwork-search-flow.json"


# Frozen forbidden lists so any future drift surfaces in a single diff site.
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
# Cross-channel hostnames that MUST NOT appear in this Upwork flow's node
# graph. (Upwork itself is the target so `upwork.com` is allowed.)
_FORBIDDEN_HOSTNAMES_FOR_UPWORK_FLOW = ("linkedin.com", "onlinejobs.ph")


@pytest.fixture(scope="module")
def flow() -> dict:
    return json.loads(UPWORK_FLOW.read_text(encoding="utf-8"))


# --- structural skeleton -------------------------------------------------


def test_upwork_flow_is_valid_json(flow) -> None:
    """The fixture loaded JSON — assert the top-level shape exists."""
    assert isinstance(flow, dict)


def test_upwork_flow_has_required_top_level_fields(flow) -> None:
    """An n8n workflow export carries `name`, `nodes[]`, `connections{}`."""
    assert isinstance(flow.get("name"), str) and flow["name"]
    assert isinstance(flow.get("nodes"), list) and flow["nodes"]
    assert isinstance(flow.get("connections"), dict)


def test_upwork_flow_nodes_carry_id_name_and_type(flow) -> None:
    """Each node must have `id`, `name`, `type` so n8n can import it."""
    for node in flow["nodes"]:
        assert isinstance(node, dict)
        assert isinstance(node.get("id"), str) and node["id"]
        assert isinstance(node.get("name"), str) and node["name"]
        assert isinstance(node.get("type"), str) and node["type"]


# --- AC4: FR11 statement at the top of every flow JSON --------------------


def test_upwork_flow_carries_fr11_notes_block(flow) -> None:
    """AC4: workflow-level `notes` field carries the FR11 statement verbatim.

    The spec mandates this exact wording at the top of the flow JSON:
      "FR11: this flow MUST NOT log into Upwork. Public RSS / public
       listing pages only. Stories 7.1-7.4 share the n8n contract;
       see `docs/n8n-contract.md`."
    """
    notes = flow.get("notes")
    assert isinstance(notes, str) and notes, "n8n flow must carry a `notes` field"
    assert "FR11" in notes
    assert "MUST NOT log into Upwork" in notes
    assert "Public RSS" in notes
    assert "docs/n8n-contract.md" in notes


# --- AC1 / AC4: no browser-automation / no platform-login material -------


def test_upwork_flow_uses_no_forbidden_node_types(flow) -> None:
    """AC4: no Execute Command, no SSH/shell, no Puppeteer/Selenium/Browserless."""
    used_types = {node["type"] for node in flow["nodes"]}
    overlap = used_types & _FORBIDDEN_NODE_TYPES
    assert overlap == set(), f"flow uses forbidden node type(s): {sorted(overlap)}"


def test_upwork_flow_uses_only_allowed_node_families(flow) -> None:
    """AC4: positive allowlist of node-type prefixes — Cron / HTTP / Function / IF / Item Lists / Code."""
    allowed_prefixes = (
        "n8n-nodes-base.cron",
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
        "n8n-nodes-base.code",
        "n8n-nodes-base.itemLists",
        "n8n-nodes-base.if",
        "n8n-nodes-base.set",
        "n8n-nodes-base.merge",
    )
    for node in flow["nodes"]:
        node_type = node["type"]
        assert any(node_type.startswith(prefix) for prefix in allowed_prefixes), (
            f"node {node['name']!r} uses disallowed type {node_type!r}"
        )


def test_upwork_flow_node_graph_excludes_cross_channel_hostnames(flow) -> None:
    """AC4: the node graph MUST NOT reference `linkedin.com` or `onlinejobs.ph`.

    The workflow-level `notes` field is allowed to name those sites (FR11
    documentation); only the node parameter graph is scanned so no HTTP /
    Function node can target the wrong channel.
    """
    nodes_only = json.dumps(flow.get("nodes", []), ensure_ascii=False).lower()
    for host in _FORBIDDEN_HOSTNAMES_FOR_UPWORK_FLOW:
        assert host not in nodes_only, (
            f"n8n/upwork-search-flow.json node graph contains cross-channel "
            f"hostname {host!r} — Story 7.2 targets Upwork only (FR11)."
        )


def test_upwork_flow_does_not_embed_credentials_block(flow) -> None:
    """AC4: no node may carry a `credentials` block — env vars only (FR11)."""
    for node in flow["nodes"]:
        assert "credentials" not in node, (
            f"node {node['name']!r} embeds a `credentials` block; "
            "upwork flow must use env vars only (FR11)."
        )


# --- AC4: hosting-agnostic env var contract --------------------------------


def test_upwork_flow_references_only_documented_env_vars() -> None:
    """AC4: only `INGEST_BASE_URL`, `INGEST_SHARED_TOKEN`, `UPWORK_SEARCH_QUERY`."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    assert "INGEST_BASE_URL" in raw
    assert "INGEST_SHARED_TOKEN" in raw
    assert "UPWORK_SEARCH_QUERY" in raw

    allowed = {"INGEST_BASE_URL", "INGEST_SHARED_TOKEN", "UPWORK_SEARCH_QUERY"}
    matches = re.findall(r"\$env\.([A-Z_][A-Z0-9_]*)", raw)
    assert matches, "expected at least one $env.* reference"
    for env_name in matches:
        assert env_name in allowed, (
            f"flow references undocumented env var ${env_name}; "
            f"allowed: {sorted(allowed)}"
        )


def test_upwork_flow_token_value_is_not_baked_in() -> None:
    """AC4 / FR11: the token literal must never appear in the committed JSON."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    assert "Bearer {{$env.INGEST_SHARED_TOKEN}}" in raw or (
        "Bearer " in raw and "{{$env.INGEST_SHARED_TOKEN}}" in raw
    )
    for needle in ("Bearer sk-", "Bearer secret-", "Bearer eyJ", "INGEST_TOKEN="):
        assert needle not in raw, (
            f"flow appears to bake a literal token marker {needle!r}"
        )


# --- AC1: Cron + Upwork public RSS endpoint -------------------------------


def test_upwork_flow_has_cron_trigger(flow) -> None:
    """AC1: there is exactly one Cron / scheduleTrigger node."""
    triggers = [
        n
        for n in flow["nodes"]
        if n["type"]
        in {"n8n-nodes-base.cron", "n8n-nodes-base.scheduleTrigger"}
    ]
    assert len(triggers) == 1, (
        "expected exactly one Cron / scheduleTrigger node; got "
        f"{[n['name'] for n in triggers]}"
    )


def test_upwork_flow_cron_default_is_every_six_hours() -> None:
    """AC1: default cron schedule is `0 */6 * * *` (every 6 hours)."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    assert "0 */6 * * *" in raw, (
        "expected default cron expression `0 */6 * * *` in flow JSON"
    )


def test_upwork_flow_fetches_public_rss_url() -> None:
    """AC1: HTTP Request fetches Upwork's public RSS endpoint with no auth."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    # Public RSS endpoint marker
    assert "www.upwork.com/ab/feed/jobs/rss" in raw, (
        "expected Upwork public-RSS endpoint URL in flow JSON"
    )
    # Search query env var is interpolated into the URL
    assert "{{$env.UPWORK_SEARCH_QUERY}}" in raw


def test_upwork_flow_carries_no_upwork_login_material(flow) -> None:
    """AC1 / FR11: no Upwork session cookie / OAuth / login credential markers.

    Scans the node graph for telltale auth strings. Workflow-level `notes`
    is intentionally excluded since it documents the FR11 ban.
    """
    nodes_only = json.dumps(flow.get("nodes", []), ensure_ascii=False).lower()
    forbidden_markers = (
        "set-cookie",
        "x-upwork-",
        "oauth_token",
        "oauth2",
        "session_id=",
        "upwork_session",
        "client_secret",
    )
    for marker in forbidden_markers:
        assert marker not in nodes_only, (
            f"upwork flow node graph contains forbidden auth marker "
            f"{marker!r} (FR11)."
        )


# --- AC2: per-URL dedup via SHA-256 + persistent static data --------------


def test_upwork_flow_uses_sha256_for_url_hashing() -> None:
    """AC2: dedup hashes the canonical URL with SHA-256."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    assert "sha256" in raw.lower(), (
        "expected SHA-256 to be used for URL hashing (AC2)"
    )


def test_upwork_flow_persists_dedup_under_namespaced_key() -> None:
    """AC2: dedup state lives in workflow static data under `upwork.seen_urls`."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    assert "upwork.seen_urls" in raw, (
        "expected static-data key `upwork.seen_urls` (AC2 namespacing)"
    )
    # n8n's persistent static-data API survives restarts; the canonical call is
    # `getWorkflowStaticData(...)` from the Function node context.
    assert "getWorkflowStaticData" in raw, (
        "expected use of getWorkflowStaticData() so dedup survives restarts (AC2)"
    )


# --- AC3: POSTs to /api/paste with Story 7.1 body contract ----------------


def test_upwork_flow_posts_to_api_paste_endpoint() -> None:
    """AC3: HTTP Request node targets `${INGEST_BASE_URL}/api/paste`."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    assert "/api/paste" in raw
    assert "$env.INGEST_BASE_URL" in raw


def test_upwork_flow_body_carries_contract_fields() -> None:
    """AC3: POSTed body includes `source`, `jd_text`, `url`, `discovered_at`."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    for field in ("source", "jd_text", "url", "discovered_at"):
        assert field in raw, (
            f"upwork flow body must include `{field}` (Story 7.1 contract)"
        )
    # Source value MUST be the canonical "upwork" string per docs/n8n-contract.md.
    assert "'upwork'" in raw or '"upwork"' in raw, (
        "POSTed body must set source='upwork' (n8n-contract.md mapping)"
    )


def test_upwork_flow_authorization_header_uses_bearer_env_token() -> None:
    """AC3: Authorization header is `Bearer ${INGEST_SHARED_TOKEN}`."""
    raw = UPWORK_FLOW.read_text(encoding="utf-8")
    # Either form is acceptable (matches auth-test pattern).
    assert "Bearer {{$env.INGEST_SHARED_TOKEN}}" in raw or (
        "Bearer " in raw and "{{$env.INGEST_SHARED_TOKEN}}" in raw
    )
