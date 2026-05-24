"""Structural + FR11 + hosting-agnostic guards for `n8n/onlinejobs-ph-listings-flow.json` (Story 7.3).

Mirrors the shape of `test_auth_test_flow_json.py` (Story 7.1) but covers the
OnlineJobs.ph channel flow's four ACs:

- AC1: Cron trigger + HTTP Request against the OJ.ph PUBLIC listings URL,
  no session cookie / OAuth / login credentials, no browser-automation node.
- AC2: per-URL SHA-256 dedup with a per-flow static-data namespace
  (`onlinejobs_ph.seen_urls`) so the store does not collide with the
  Upwork flow's namespace.
- AC3: POST to `${INGEST_BASE_URL}/api/paste` with the Story 7.1 canonical
  body (`source` = `"onlinejobs_ph"`, `jd_text`, `url`, `discovered_at`)
  and bearer-token auth from the n8n environment variable.
- AC4: only the documented env vars (`INGEST_BASE_URL`, `INGEST_SHARED_TOKEN`,
  `OJPH_SEARCH_QUERY`) and only stock node types (Cron, HTTP Request, Code /
  Function, Item Lists, IF) — no Execute Command, no browser node.

Note on FR11 / hostname-guard: the repository-level secret-hygiene scanner
(`tests/unit/test_secret_hygiene.py`) blocks the literal substring
`onlinejobs.ph/jobseekers` inside `src/jobhunter/*.py` only. This test file
DOES reference `onlinejobs.ph` because the OJ.ph flow JSON necessarily
contains that hostname (the flow's job is to fetch from OJ.ph's public
listings). The hygiene test does not scan `tests/` or `n8n/` — verified
before adding these assertions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OJPH_FLOW = PROJECT_ROOT / "n8n" / "onlinejobs-ph-listings-flow.json"


# Forbidden node types and hostnames — kept verbatim from the Story 7.1 test
# so any future drift surfaces in a single diff site. The OJ.ph flow is
# allowed to target `onlinejobs.ph` (that is the whole point of the flow);
# `upwork.com` and `linkedin.com` remain forbidden.
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
_FORBIDDEN_HOSTNAMES_FOR_OJPH = ("upwork.com", "linkedin.com")


@pytest.fixture(scope="module")
def flow() -> dict:
    return json.loads(OJPH_FLOW.read_text(encoding="utf-8"))


# --- structural skeleton --------------------------------------------------


def test_ojph_flow_file_exists() -> None:
    """The Story 7.3 flow JSON must be committed under `n8n/`."""
    assert OJPH_FLOW.is_file(), f"missing flow file: {OJPH_FLOW}"


def test_ojph_flow_is_valid_json(flow) -> None:
    """The fixture loaded JSON — assert the top-level shape exists."""
    assert isinstance(flow, dict)


def test_ojph_flow_has_required_top_level_fields(flow) -> None:
    """An n8n workflow export carries `name`, `nodes[]`, `connections{}`."""
    assert isinstance(flow.get("name"), str) and flow["name"]
    assert isinstance(flow.get("nodes"), list) and flow["nodes"]
    assert isinstance(flow.get("connections"), dict)


def test_ojph_flow_nodes_carry_id_name_and_type(flow) -> None:
    """Each node must have `id`, `name`, `type` so n8n can import it."""
    for node in flow["nodes"]:
        assert isinstance(node, dict)
        assert isinstance(node.get("id"), str) and node["id"]
        assert isinstance(node.get("name"), str) and node["name"]
        assert isinstance(node.get("type"), str) and node["type"]


# --- AC4: FR11 statement at the top of the flow JSON ----------------------


def test_ojph_flow_carries_fr11_notes_block(flow) -> None:
    """AC4: the workflow-level `notes` field carries the FR11 statement verbatim."""
    notes = flow.get("notes")
    assert isinstance(notes, str) and notes, "n8n flow must carry a `notes` field"
    assert "FR11" in notes
    assert "MUST NOT log into OnlineJobs.ph" in notes
    assert "Public listings only" in notes
    assert "docs/n8n-contract.md" in notes


# --- AC1 + AC4: no browser-automation / no Execute Command ---------------


def test_ojph_flow_uses_no_forbidden_node_types(flow) -> None:
    """AC4: only HTTP / Cron / transform nodes. No Execute Command, no browser."""
    used_types = {node["type"] for node in flow["nodes"]}
    overlap = used_types & _FORBIDDEN_NODE_TYPES
    assert overlap == set(), f"flow uses forbidden node type(s): {sorted(overlap)}"


def test_ojph_flow_uses_only_allowed_node_families(flow) -> None:
    """AC4: positive allowlist of node-type prefixes the flow may use.

    Story 7.3 explicitly calls out Cron, HTTP Request, Code, Item Lists, IF
    as the allowed family. The Story 7.1 reference flow also accepts
    Function (== Code's v1 typeVersion), Set, and Merge as standard
    transforms; keep the allowlist aligned with that contract.
    """
    allowed_prefixes = (
        "n8n-nodes-base.cron",
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
        "n8n-nodes-base.code",
        "n8n-nodes-base.itemLists",
        "n8n-nodes-base.set",
        "n8n-nodes-base.if",
        "n8n-nodes-base.merge",
    )
    for node in flow["nodes"]:
        node_type = node["type"]
        assert any(node_type.startswith(prefix) for prefix in allowed_prefixes), (
            f"node {node['name']!r} uses disallowed type {node_type!r}"
        )


def test_ojph_flow_has_cron_trigger_with_default_schedule(flow) -> None:
    """AC1: the flow is cron-triggered; default schedule is `0 */6 * * *`."""
    cron_nodes = [n for n in flow["nodes"] if n["type"] == "n8n-nodes-base.cron"]
    assert len(cron_nodes) == 1, "expected exactly one Cron trigger node"
    # The default `0 */6 * * *` schedule must be encoded in the trigger
    # parameters so the flow polls every 6 hours by default.
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    assert "0 */6 * * *" in raw, "default cron schedule (`0 */6 * * *`) is missing"


def test_ojph_flow_has_http_request_for_ojph_public_listings(flow) -> None:
    """AC1: an HTTP Request node fetches OJ.ph's PUBLIC listings URL."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    # AC1: the listings URL is the public jobsearch path with the search
    # query injected via `OJPH_SEARCH_QUERY`.
    assert "https://www.onlinejobs.ph/jobseekers/jobsearch/" in raw
    assert "$env.OJPH_SEARCH_QUERY" in raw


def test_ojph_flow_contains_no_other_platform_hostnames(flow) -> None:
    """AC1 / FR11: the OJ.ph flow may target onlinejobs.ph but NOT upwork / linkedin.

    The flow's entire job is to fetch from OnlineJobs.ph, so the
    `onlinejobs.ph` hostname is expected to appear in the node graph. Only
    `upwork.com` and `linkedin.com` are forbidden — those would indicate a
    cross-channel contamination of the flow JSON.
    """
    nodes_only = json.dumps(flow.get("nodes", []), ensure_ascii=False).lower()
    for host in _FORBIDDEN_HOSTNAMES_FOR_OJPH:
        assert host not in nodes_only, (
            f"n8n/onlinejobs-ph-listings-flow.json contains forbidden hostname "
            f"{host!r} (FR11 / cross-channel contamination)."
        )
    # Positive sanity check: the flow MUST reference the OJ.ph hostname
    # somewhere in its node graph (otherwise it can't poll listings).
    assert "onlinejobs.ph" in nodes_only, (
        "OJ.ph flow does not reference the onlinejobs.ph hostname in any node — "
        "the flow cannot fetch listings."
    )


def test_ojph_flow_does_not_embed_credentials_block(flow) -> None:
    """AC1 / FR11: no node may carry a `credentials` block.

    OJ.ph public listings require no login, so any `credentials` entry on
    a node would indicate a session cookie / OAuth token / password leaking
    into the flow JSON.
    """
    for node in flow["nodes"]:
        assert "credentials" not in node, (
            f"node {node['name']!r} embeds a `credentials` block; "
            "OJ.ph flow must not authenticate against onlinejobs.ph (FR11)."
        )


def test_ojph_flow_carries_no_session_cookie_or_auth_header_to_ojph() -> None:
    """AC1 / FR11: the fetch node must not send a Cookie / OJ.ph Authorization header.

    A `Cookie` header on the listings fetch would imply a session cookie;
    `Authorization` on the OJ.ph fetch (as opposed to the /api/paste POST)
    would imply OAuth-style platform login. The /api/paste POST DOES need
    an `Authorization: Bearer {{$env.INGEST_SHARED_TOKEN}}` header, so we
    inspect the OJ.ph-targeting node in isolation.
    """
    raw_flow = json.loads(OJPH_FLOW.read_text(encoding="utf-8"))
    for node in raw_flow["nodes"]:
        if node["type"] != "n8n-nodes-base.httpRequest":
            continue
        params = node.get("parameters", {})
        url = params.get("url", "")
        if "onlinejobs.ph" not in url.lower():
            continue
        # This node is the OJ.ph public-listings fetch. It must not carry
        # any header named `Cookie` or `Authorization`.
        header_params = (
            params.get("headerParameters", {}).get("parameters", [])
            if isinstance(params.get("headerParameters"), dict)
            else []
        )
        for header in header_params:
            header_name = str(header.get("name", "")).lower()
            assert header_name not in ("cookie", "authorization"), (
                f"OJ.ph fetch node sends forbidden header {header.get('name')!r} "
                "(FR11: no session cookie / no platform-login auth)."
            )


# --- AC2: per-URL dedup + per-flow static-data namespace -----------------


def test_ojph_flow_uses_sha256_url_hashing(flow) -> None:
    """AC2: the dedup logic uses SHA-256 hashing of the URL."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    # Same hashing primitive Story 7.2 uses — keeps the pattern consistent
    # across channel flows.
    assert "sha256" in raw.lower(), "AC2 requires SHA-256 url hashing"


def test_ojph_flow_uses_per_flow_static_data_namespace(flow) -> None:
    """AC2: the dedup store lives under the `onlinejobs_ph` namespace.

    Scoping by namespace means Story 7.2's `upwork` hashes and Story 7.3's
    `onlinejobs_ph` hashes never collide, even if the same canonical URL
    were ever to appear on both platforms.
    """
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    assert "getWorkflowStaticData" in raw, (
        "AC2 requires n8n static-data persistence so dedup survives restarts"
    )
    assert "onlinejobs_ph" in raw, (
        "AC2 requires the dedup namespace key `onlinejobs_ph` (per-flow scope)"
    )
    assert "seen_urls" in raw, (
        "AC2 requires the `seen_urls` field on the static-data namespace"
    )


# --- AC3: POST to /api/paste with Story 7.1 canonical contract -----------


def test_ojph_flow_posts_to_api_paste_endpoint() -> None:
    """AC3: an HTTP Request node targets `${INGEST_BASE_URL}/api/paste`."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    assert "/api/paste" in raw
    assert "$env.INGEST_BASE_URL" in raw


def test_ojph_flow_body_carries_source_onlinejobs_ph() -> None:
    """AC3: the POST body sets `source` to the canonical `onlinejobs_ph` literal."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    # The source value is part of the body; the canonical literal from the
    # Story 7.1 contract is `onlinejobs_ph` (underscore form).
    assert "onlinejobs_ph" in raw


def test_ojph_flow_body_carries_canonical_contract_fields() -> None:
    """AC3: the body carries `jd_text`, `source`, `url`, `discovered_at`."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    for field in ("jd_text", "source", "url", "discovered_at"):
        assert field in raw, f"POST body must include `{field}` (Story 7.1 contract)"


def test_ojph_flow_sends_bearer_token_via_env_var() -> None:
    """AC3: the /api/paste POST sends `Authorization: Bearer {{$env.INGEST_SHARED_TOKEN}}`."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    assert "Bearer {{$env.INGEST_SHARED_TOKEN}}" in raw or (
        "Bearer " in raw and "{{$env.INGEST_SHARED_TOKEN}}" in raw
    ), "AC3 requires bearer-token auth via the INGEST_SHARED_TOKEN env var"


def test_ojph_flow_token_value_is_not_baked_in() -> None:
    """AC4: the token literal must never appear in the committed JSON."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    for needle in ("Bearer sk-", "Bearer secret-", "Bearer eyJ", "INGEST_TOKEN="):
        assert needle not in raw, (
            f"flow appears to bake a literal token marker {needle!r}"
        )


# --- AC4: hosting-agnostic env var contract -------------------------------


def test_ojph_flow_references_only_documented_env_vars() -> None:
    """AC4: env vars referenced are exactly `INGEST_BASE_URL`, `INGEST_SHARED_TOKEN`, `OJPH_SEARCH_QUERY`."""
    raw = OJPH_FLOW.read_text(encoding="utf-8")
    assert "INGEST_BASE_URL" in raw
    assert "INGEST_SHARED_TOKEN" in raw
    assert "OJPH_SEARCH_QUERY" in raw

    matches = re.findall(r"\$env\.([A-Z_][A-Z0-9_]*)", raw)
    allowed = {"INGEST_BASE_URL", "INGEST_SHARED_TOKEN", "OJPH_SEARCH_QUERY"}
    for env_name in matches:
        assert env_name in allowed, (
            f"flow references undocumented env var ${env_name}; "
            f"allowed: {sorted(allowed)}"
        )
