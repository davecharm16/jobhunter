#!/usr/bin/env bash
# Invoked by the n8n Execute Command node. Reads the fully-assembled prompt on
# stdin (n8n pipes it in), runs Claude headless with the Playwright MCP, and
# prints Claude's result JSON to stdout for n8n to parse.
#
# Auth (set on the n8n service): CLAUDE_CODE_OAUTH_TOKEN (runs on your Claude
# subscription). Do NOT set ANTHROPIC_API_KEY in this container — it overrides
# the OAuth token. The `claude` CLI reads CLAUDE_CODE_OAUTH_TOKEN from the env.
set -euo pipefail

PROMPT="$(cat)"   # n8n writes the assembled prompt to stdin

claude -p "$PROMPT" \
  --mcp-config /opt/scan/mcp.json \
  --allowedTools "mcp__playwright__*" \
  --permission-mode bypassPermissions \
  --output-format json
