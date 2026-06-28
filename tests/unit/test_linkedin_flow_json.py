"""Structural + FR10/FR11/NFR12 guards for `n8n/linkedin-email-parser-flow.json`.

Story 7.4 — LinkedIn Job Alert email parser flow. Critically, this flow is
email-parse ONLY: it must NEVER fetch any `linkedin.com` URL. Crawling
LinkedIn would put the author's income-bearing LinkedIn account at risk
(ToS landmine + account-suspension). This test file enforces that rule by
inspection on the committed flow JSON.

Covers all 5 ACs:

- AC1: IMAP poll trigger; no LinkedIn site fetches; no LinkedIn cookie / OAuth / password.
- AC2: parser is implemented in a `Code` / Function node (editable on template drift).
- AC3: dual dedup — per email Message-ID AND per extracted job URL.
- AC4: POSTs to `${INGEST_BASE_URL}/api/paste` with Bearer token per Story 7.1 contract.
- AC5: hosting-agnostic; only documented env vars; FR10/FR11/NFR12 notes block verbatim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LINKEDIN_FLOW = PROJECT_ROOT / "n8n" / "linkedin-email-parser-flow.json"


# AC5 forbidden-node-types — same allowlist style as Story 7.1's auth-test guard.
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

# AC5 allowed env vars (and ONLY these).
_ALLOWED_ENV_VARS = frozenset(
    {
        "INGEST_BASE_URL",
        "INGEST_SHARED_TOKEN",
        "IMAP_HOST",
        "IMAP_USER",
        "IMAP_PASSWORD",
        "IMAP_PORT",
    }
)

# The FR10/FR11/NFR12 notes block must appear verbatim (per spec AC5).
_REQUIRED_NOTES_VERBATIM = (
    "FR10 + FR11 + NFR12: LinkedIn ingest is email-parse ONLY. "
    "This flow MUST NOT fetch any linkedin.com URL. "
    "Site crawling is forbidden — ToS landmine and account-suspension risk "
    "against the author's income-bearing LinkedIn account. "
    "The IMAP inbox used must be a dedicated Gmail account separate from "
    "the author's primary LinkedIn-registered email, so the polling "
    "credentials are isolated from anything tied to the author's LinkedIn login."
)


@pytest.fixture(scope="module")
def flow() -> dict:
    return json.loads(LINKEDIN_FLOW.read_text(encoding="utf-8"))


# --- AC1 + AC5: structural skeleton --------------------------------------


def test_linkedin_flow_is_valid_json(flow) -> None:
    """The fixture loaded JSON — assert the top-level shape exists."""
    assert isinstance(flow, dict)


def test_linkedin_flow_has_required_top_level_fields(flow) -> None:
    """An n8n workflow export carries `name`, `nodes[]`, `connections{}`."""
    assert isinstance(flow.get("name"), str) and flow["name"]
    assert isinstance(flow.get("nodes"), list) and flow["nodes"]
    assert isinstance(flow.get("connections"), dict)


def test_linkedin_flow_nodes_carry_id_name_and_type(flow) -> None:
    """Each node must have `id`, `name`, `type` so n8n can import it."""
    for node in flow["nodes"]:
        assert isinstance(node, dict)
        assert isinstance(node.get("id"), str) and node["id"]
        assert isinstance(node.get("name"), str) and node["name"]
        assert isinstance(node.get("type"), str) and node["type"]


# --- AC1: IMAP trigger present, filters LinkedIn Job Alert mail ----------


def test_linkedin_flow_uses_imap_email_read_as_trigger(flow) -> None:
    """AC1: an `IMAP Email Read` node is wired as the entry trigger."""
    imap_nodes = [
        node
        for node in flow["nodes"]
        if node["type"] == "n8n-nodes-base.emailReadImap"
    ]
    assert len(imap_nodes) >= 1, (
        "Story 7.4 AC1 requires an IMAP Email Read trigger node "
        "(n8n-nodes-base.emailReadImap)."
    )


def test_linkedin_flow_filters_on_linkedin_jobalerts_sender(flow) -> None:
    """AC1: the IMAP node filters mail by LinkedIn Job Alert sender pattern."""
    imap_nodes = [
        node
        for node in flow["nodes"]
        if node["type"] == "n8n-nodes-base.emailReadImap"
    ]
    assert imap_nodes, "No IMAP node found"
    serialized = json.dumps(imap_nodes, ensure_ascii=False)
    assert "jobalerts-noreply@linkedin.com" in serialized, (
        "AC1: IMAP node must filter on the LinkedIn Job Alert sender "
        "(`jobalerts-noreply@linkedin.com`)."
    )


# --- AC1 + AC5 (the critical one): NO `linkedin.com` HTTP target ---------


def test_linkedin_flow_no_node_targets_linkedin_com_via_http(flow) -> None:
    """AC1 + AC5 (the central rule of Story 7.4).

    The flow MUST NOT fetch any `linkedin.com` URL. Crawling LinkedIn would
    risk the author's income-bearing LinkedIn account.

    Checking the *entire* JSON for the substring `linkedin.com` would
    over-match: the workflow `notes` field is required to mention
    `linkedin.com` verbatim (the FR10/FR11/NFR12 reminder), the IMAP filter
    must name `jobalerts-noreply@linkedin.com`, and parsed-from-email job
    URLs (extracted as data into Function node payloads) are allowed.

    The distinguishing line is: `linkedin.com` as an HTTP fetch *target* is
    forbidden. So we scope the check to `nodes[].parameters.url` — the
    canonical place an HTTP Request node carries its target URL.
    """
    for node in flow["nodes"]:
        params = node.get("parameters") or {}
        url = params.get("url")
        if url is None:
            continue
        assert isinstance(url, str), (
            f"node {node['name']!r} has non-string `parameters.url`: {url!r}"
        )
        assert "linkedin.com" not in url.lower(), (
            f"node {node['name']!r} targets a linkedin.com URL via HTTP "
            f"({url!r}). Story 7.4 FR10/FR11/NFR12 forbid any linkedin.com "
            f"HTTP fetch — email-parse only."
        )


def test_linkedin_flow_http_request_targets_only_ingest_base_url(flow) -> None:
    """AC1 + AC4: every `httpRequest` node's `url` resolves to `${INGEST_BASE_URL}/...`.

    Positive complement of the negative `linkedin.com` test above — pins
    that the only HTTP target in the flow is the Job Hunter ingest endpoint.
    """
    http_nodes = [
        node
        for node in flow["nodes"]
        if node["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert http_nodes, "Story 7.4 needs an HTTP Request node for /api/paste."
    for node in http_nodes:
        url = (node.get("parameters") or {}).get("url", "")
        assert isinstance(url, str) and url, (
            f"httpRequest node {node['name']!r} missing `parameters.url`"
        )
        assert "$env.INGEST_BASE_URL" in url, (
            f"httpRequest node {node['name']!r} URL {url!r} must use "
            f"`{{{{$env.INGEST_BASE_URL}}}}` (hosting-agnostic)."
        )


# --- AC2: parser node present (Function / Code), editable on template drift ---


def test_linkedin_flow_has_a_function_or_code_parser_node(flow) -> None:
    """AC2: at least one Function / Code node exists for parsing the email body."""
    parser_node_types = {
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
        "n8n-nodes-base.code",
    }
    parser_nodes = [
        node for node in flow["nodes"] if node["type"] in parser_node_types
    ]
    assert parser_nodes, (
        "Story 7.4 AC2 requires a Function/Code parser node so the parser "
        "is editable when LinkedIn changes their Job Alert template."
    )


# --- AC3: dual dedup by Message-ID AND by job URL ------------------------


def test_linkedin_flow_dedups_by_email_message_id(flow) -> None:
    """AC3: the flow hashes the RFC 5322 `Message-ID` header and persists it.

    Detected via the `linkedin_email.seen_message_ids` static-data slot
    name, which the parser code must touch.
    """
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    assert "seen_message_ids" in raw, (
        "AC3: flow must dedup by Message-ID via "
        "`linkedin_email.seen_message_ids` static-data slot."
    )
    assert "sha256" in raw.lower(), (
        "AC3: Message-ID must be SHA-256-hashed before being stored."
    )


def test_linkedin_flow_dedups_by_extracted_job_url(flow) -> None:
    """AC3: the flow hashes each extracted job URL and persists it.

    Detected via the `linkedin_email.seen_job_urls` static-data slot name.
    """
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    assert "seen_job_urls" in raw, (
        "AC3: flow must dedup by extracted job URL via "
        "`linkedin_email.seen_job_urls` static-data slot."
    )


# --- AC4: POSTs canonical body to /api/paste with bearer token -----------


def test_linkedin_flow_posts_to_api_paste_endpoint() -> None:
    """AC4: the HTTP Request node targets `${INGEST_BASE_URL}/api/paste`."""
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    assert "/api/paste" in raw
    assert "$env.INGEST_BASE_URL" in raw


def test_linkedin_flow_uses_bearer_token_via_env_var() -> None:
    """AC4: the Authorization header reads from `INGEST_SHARED_TOKEN` env var."""
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    assert "Bearer {{$env.INGEST_SHARED_TOKEN}}" in raw or (
        "Bearer " in raw and "{{$env.INGEST_SHARED_TOKEN}}" in raw
    )


def test_linkedin_flow_body_carries_canonical_fields() -> None:
    """AC4: the POST body carries `source`, `jd_text`, `url`, `discovered_at`."""
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    for field in ("source", "jd_text", "url", "discovered_at"):
        assert field in raw, f"POST body must include `{field}` (AC4 contract)"
    # Source identifier per docs/n8n-contract.md source-to-metadata mapping.
    assert "linkedin_email" in raw, (
        "AC4: `source` field must be the string literal `linkedin_email`."
    )


def test_linkedin_flow_token_value_is_not_baked_in() -> None:
    """AC4: the token literal must never appear in the committed JSON."""
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    for needle in ("Bearer sk-", "Bearer secret-", "Bearer eyJ", "INGEST_TOKEN="):
        assert needle not in raw, (
            f"flow appears to bake a literal token marker {needle!r}"
        )


# --- AC5: hosting-agnostic env-var contract; allowed node types only -----


def test_linkedin_flow_references_only_documented_env_vars() -> None:
    """AC5: the only n8n env vars used are the 6 documented in the spec."""
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    matches = re.findall(r"\$env\.([A-Z_][A-Z0-9_]*)", raw)
    assert matches, "flow references no env vars at all — that can't be right"
    for env_name in matches:
        assert env_name in _ALLOWED_ENV_VARS, (
            f"flow references undocumented env var ${env_name}; "
            f"allowed: {sorted(_ALLOWED_ENV_VARS)}"
        )


def test_linkedin_flow_references_all_required_env_vars() -> None:
    """AC5: every documented env var must actually appear in the flow JSON."""
    raw = LINKEDIN_FLOW.read_text(encoding="utf-8")
    for env_var in _ALLOWED_ENV_VARS:
        assert env_var in raw, (
            f"AC5: required env var ${env_var} is not referenced in the flow."
        )


def test_linkedin_flow_uses_no_forbidden_node_types(flow) -> None:
    """AC5: no Execute Command, no SSH/shell, no browser-automation nodes."""
    used_types = {node["type"] for node in flow["nodes"]}
    overlap = used_types & _FORBIDDEN_NODE_TYPES
    assert overlap == set(), f"flow uses forbidden node type(s): {sorted(overlap)}"


def test_linkedin_flow_uses_only_allowed_node_families(flow) -> None:
    """AC5: positive allowlist of node-type prefixes the flow may use."""
    allowed_prefixes = (
        "n8n-nodes-base.emailReadImap",
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.cron",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.function",
        "n8n-nodes-base.functionItem",
        "n8n-nodes-base.code",
        "n8n-nodes-base.if",
        "n8n-nodes-base.itemLists",
        "n8n-nodes-base.set",
        "n8n-nodes-base.merge",
        "n8n-nodes-base.htmlExtract",
    )
    for node in flow["nodes"]:
        node_type = node["type"]
        assert any(node_type.startswith(prefix) for prefix in allowed_prefixes), (
            f"node {node['name']!r} uses disallowed type {node_type!r}"
        )


def test_linkedin_flow_does_not_embed_credentials_block(flow) -> None:
    """AC1 + AC5: no node may carry an inline `credentials` block.

    All authentication material — IMAP password, ingest token — flows via
    env vars at n8n runtime; nothing is baked into the committed JSON.
    """
    for node in flow["nodes"]:
        assert "credentials" not in node, (
            f"node {node['name']!r} embeds a `credentials` block; "
            "Story 7.4 requires env-var-only auth."
        )


# --- AC5: FR10/FR11/NFR12 notes block, verbatim --------------------------


def test_linkedin_flow_carries_fr10_fr11_nfr12_notes_block_verbatim(flow) -> None:
    """AC5: the workflow-level `notes` field carries the spec block VERBATIM."""
    notes = flow.get("notes")
    assert isinstance(notes, str) and notes, "n8n flow must carry a `notes` field"
    assert _REQUIRED_NOTES_VERBATIM in notes, (
        "AC5: `notes` field must carry the FR10/FR11/NFR12 reminder VERBATIM.\n"
        f"Expected substring:\n{_REQUIRED_NOTES_VERBATIM!r}"
    )


def test_linkedin_flow_notes_explicitly_name_the_three_landmines(flow) -> None:
    """AC5: `notes` must name FR10, FR11, NFR12 by identifier and the core rule."""
    notes = flow["notes"]
    for marker in ("FR10", "FR11", "NFR12"):
        assert marker in notes, f"`notes` must name {marker} by identifier"
    assert "email-parse ONLY" in notes
    assert "MUST NOT fetch any linkedin.com URL" in notes


# --- Cross-flow consistency check ----------------------------------------


def test_linkedin_flow_tagged_for_epic_7_story_7_4(flow) -> None:
    """Tags identify the flow as Story 7.4 / Epic 7 (matches auth-test convention)."""
    tags = flow.get("tags")
    assert isinstance(tags, list) and tags
    assert "story-7-4" in tags
    assert "epic-7" in tags
