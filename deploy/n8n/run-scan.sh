#!/usr/bin/env bash
# Invoked by the n8n Execute Command node. Reads BASE64-encoded JSON scan inputs
# on stdin (base64 is shell-safe: no quotes/newlines to escape through n8n),
# fills the baked-in prompt template /opt/scan/job_scan.v1.md with those inputs,
# runs Claude headless with the Playwright MCP, and prints Claude's result JSON
# envelope to stdout for n8n to parse.
#
# stdin: base64 of JSON { search_titles, sites_enabled, picks_per_site,
#                         canonical_profile, known_urls }
#
# Auth (set on the n8n service): CLAUDE_CODE_OAUTH_TOKEN (runs on your Claude
# subscription). Do NOT set ANTHROPIC_API_KEY in this container — it overrides
# the OAuth token. The `claude` CLI reads CLAUDE_CODE_OAUTH_TOKEN from the env.
set -euo pipefail

# The n8n container runs as root, and Claude Code refuses
# --permission-mode bypassPermissions / --dangerously-skip-permissions as root
# unless it's told it's in a sandbox. IS_SANDBOX=1 is that escape hatch (this IS
# an isolated container, so it's appropriate).
export IS_SANDBOX=1

INPUTS_JSON="$(cat | base64 -d)"

# Fill the template with the inputs (robust replace in Node — avoids sed/quoting
# pitfalls with multi-line JSON values).
PROMPT="$(INPUTS_JSON="$INPUTS_JSON" node -e '
  const fs = require("fs");
  const t = fs.readFileSync("/opt/scan/job_scan.v1.md", "utf8");
  const i = JSON.parse(process.env.INPUTS_JSON);
  const out = t
    .split("{{SEARCH_TITLES}}").join(JSON.stringify(i.search_titles))
    .split("{{SITES_ENABLED}}").join(JSON.stringify(i.sites_enabled))
    .split("{{PICKS_PER_SITE}}").join(String(i.picks_per_site))
    .split("{{CANONICAL_PROFILE}}").join(JSON.stringify(i.canonical_profile))
    .split("{{KNOWN_URLS}}").join(JSON.stringify(i.known_urls));
  process.stdout.write(out);
')"

claude -p "$PROMPT" \
  --mcp-config /opt/scan/mcp.json \
  --allowedTools "mcp__playwright__*" \
  --permission-mode bypassPermissions \
  --output-format json
