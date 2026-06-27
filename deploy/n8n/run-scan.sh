#!/usr/bin/env bash
# Invoked by the n8n Execute Command node, ONCE PER SITE. The site to scan is
# passed as `--site <site>` and the BASE64-encoded JSON scan inputs arrive on
# stdin. This runs a single Claude + Playwright pass scoped to that one site
# (sites_enabled is overridden to [that site]). Keeping each run small means
# Claude finishes in one turn instead of deferring to a background task.
#
# This script ALWAYS exits 0 — even if Claude fails — so the n8n node never
# errors and the workflow chain advances to the next site. The site's outcome is
# communicated entirely via the single JSON object printed to stdout.
#
# stdout (THE ONLY thing on stdout): exactly one JSON object:
#   {"site":"<site>","site_status":"ok|blocked|empty|error","candidates":[...]}
# All progress / diagnostics / Claude's own logs go to stderr.
#
# Usage: run-scan.sh --site <site>   (stdin = base64 JSON scan inputs)
# stdin JSON: { search_titles, sites_enabled, picks_per_site, location,
#               canonical_profile, known_urls }
#
# Auth (set on the n8n service): CLAUDE_CODE_OAUTH_TOKEN. Do NOT set
# ANTHROPIC_API_KEY (it overrides the OAuth token).
#
# Resilient on purpose: no `-e` (a failing Claude must not abort the script).
set -uo pipefail

# Root container → Claude needs the sandbox escape hatch for bypassPermissions.
export IS_SANDBOX=1
# Finite ceiling (15 min) so a stuck site can't hang the run forever.
# (NOT 0 = infinite, which let a deferred scan hang indefinitely.)
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=900000

# --- Parse --site <site> from args -------------------------------------------
SITE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --site)
      SITE="${2:-}"
      shift 2 || shift
      ;;
    --site=*)
      SITE="${1#--site=}"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# emit_result <site_status> [candidates_json]
# Prints the one-and-only stdout JSON object and exits 0.
emit_result() {
  local status="$1" cands="${2:-[]}"
  SITE="$SITE" STATUS="$status" CANDS="$cands" node -e '
    const out = {
      site: process.env.SITE,
      site_status: process.env.STATUS,
      candidates: (() => { try { const c = JSON.parse(process.env.CANDS); return Array.isArray(c) ? c : []; } catch (e) { return []; } })(),
    };
    process.stdout.write(JSON.stringify(out));
  '
  exit 0
}

if [ -z "$SITE" ]; then
  echo "scan: ERROR no --site provided" >&2
  emit_result "error"
fi

echo "scan: ===== ${SITE}: starting =====" >&2

INPUTS_JSON="$(cat | base64 -d)"

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PW_CONFIG=/opt/scan/pw-config.json

# Write the Playwright MCP config, picking a fresh residential proxy IP so each
# site (each invocation) rotates to a different exit IP. Anti-bot hardening:
# real desktop UA + viewport + locale, and disable the navigator.webdriver flag.
write_pw_config() {
  local proxy_json="" host
  if [ -n "${SCAN_PROXY_HOSTS:-}" ]; then
    host="$(printf '%s' "$SCAN_PROXY_HOSTS" | tr ',; ' '\n\n\n' | grep -v '^[[:space:]]*$' | shuf -n1 | tr -d '[:space:]')"
    proxy_json=", \"proxy\": { \"server\": \"http://${host}\", \"username\": \"${SCAN_PROXY_USERNAME:-}\", \"password\": \"${SCAN_PROXY_PASSWORD:-}\" }"
    echo "scan: proxy ${host}" >&2
  fi
  cat > "$PW_CONFIG" <<EOF
{ "browser": {
  "browserName": "chromium",
  "launchOptions": {
    "headless": true,
    "args": ["--disable-blink-features=AutomationControlled", "--no-sandbox"]${proxy_json}
  },
  "contextOptions": {
    "userAgent": "${UA}",
    "viewport": { "width": 1366, "height": 768 },
    "locale": "en-US"
  }
} }
EOF
}

write_pw_config

# Fill the prompt template, scoping {{SITES_ENABLED}} to just this one site.
PROMPT="$(INPUTS_JSON="$INPUTS_JSON" SITE="$SITE" node -e '
  const fs = require("fs");
  const t = fs.readFileSync("/opt/scan/job_scan.v1.md", "utf8");
  const i = JSON.parse(process.env.INPUTS_JSON);
  const site = process.env.SITE;
  const out = t
    .split("{{SEARCH_TITLES}}").join(JSON.stringify(i.search_titles))
    .split("{{SITES_ENABLED}}").join(JSON.stringify([site]))
    .split("{{LOCATION}}").join(i.location || "(none — search broadly / use profile location)")
    .split("{{PICKS_PER_SITE}}").join(String(i.picks_per_site))
    .split("{{CANONICAL_PROFILE}}").join(JSON.stringify(i.canonical_profile))
    .split("{{KNOWN_URLS}}").join(JSON.stringify(i.known_urls));
  process.stdout.write(out);
')"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
RAW="$TMPDIR/claude.json"

# Claude output can be large → capture to a file, never via env var / arg.
claude -p "$PROMPT" \
     --mcp-config /opt/scan/mcp.json \
     --allowedTools "mcp__playwright__*" \
     --permission-mode bypassPermissions \
     --output-format json > "$RAW"
RC=$?
echo "scan: ${SITE}: claude rc=${RC}" >&2

# Extract { site_status, candidates } from Claude's --output-format json envelope
# ({...,"result":"<text>"}); the text holds the site JSON possibly wrapped in
# prose/fences → slice first `{` … last `}`. Diagnostics go to stderr; the lone
# stdout line is the result JSON.
RESULT="$(SITE="$SITE" node -e '
  const fs = require("fs");
  const site = process.env.SITE;
  let payload = null;
  try {
    const env = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
    let inner = (env && env.result !== undefined) ? env.result : env;
    if (typeof inner === "string") {
      const a = inner.indexOf("{"), b = inner.lastIndexOf("}");
      if (a >= 0 && b > a) { try { payload = JSON.parse(inner.slice(a, b + 1)); } catch (e) {} }
    } else if (inner && typeof inner === "object") {
      payload = inner;
    }
  } catch (e) { payload = null; }
  let out;
  if (payload && Array.isArray(payload.candidates)) {
    const candidates = payload.candidates;
    const ss = payload.site_summary && payload.site_summary[site];
    const status = (ss && ss.status) ? ss.status : (candidates.length > 0 ? "ok" : "empty");
    out = { site, site_status: status, candidates };
  } else {
    out = { site, site_status: "error", candidates: [] };
  }
  process.stdout.write(JSON.stringify(out));
' "$RAW")"

echo "scan: ===== ${SITE}: done =====" >&2

# RESULT is already the exact contract JSON; print it as the sole stdout output.
printf '%s' "$RESULT"
exit 0
