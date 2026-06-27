#!/usr/bin/env bash
# Invoked by the n8n Execute Command node. Reads BASE64-encoded JSON scan inputs
# on stdin, then scans the enabled sites ONE AT A TIME — a separate Claude +
# Playwright run per site (sites_enabled=[that site]). Keeping each run small
# (7 titles × 1 site) means Claude finishes in a single turn instead of deferring
# the work to a background task (which used to hang / return prose). All sites'
# candidates are aggregated into ONE combined JSON printed to stdout for n8n.
# Per-site progress + Claude's own logs go to stderr (visible in the n8n node).
#
# stdin: base64 of JSON { search_titles, sites_enabled, picks_per_site, location,
#                         canonical_profile, known_urls }
#
# Auth (set on the n8n service): CLAUDE_CODE_OAUTH_TOKEN. Do NOT set
# ANTHROPIC_API_KEY (it overrides the OAuth token).
set -euo pipefail

# Root container → Claude needs the sandbox escape hatch for bypassPermissions.
export IS_SANDBOX=1
# Finite ceiling (15 min) so a stuck site can't hang the whole run forever.
# (Was 0 = infinite, which let a deferred scan hang indefinitely.)
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=900000

INPUTS_JSON="$(cat | base64 -d)"

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PW_CONFIG=/opt/scan/pw-config.json

# (Re)write the Playwright MCP config, picking a fresh residential proxy IP each
# call so each site rotates to a different exit IP. Anti-bot hardening: real
# desktop UA + viewport + locale, and disable the navigator.webdriver flag.
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

SITES="$(printf '%s' "$INPUTS_JSON" | node -e 'const i=JSON.parse(require("fs").readFileSync(0,"utf8"));process.stdout.write((i.sites_enabled||[]).join(" "))')"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

for site in $SITES; do
  echo "scan: ===== ${site}: starting =====" >&2
  write_pw_config
  PROMPT="$(INPUTS_JSON="$INPUTS_JSON" SITE="$site" node -e '
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
  if claude -p "$PROMPT" \
       --mcp-config /opt/scan/mcp.json \
       --allowedTools "mcp__playwright__*" \
       --permission-mode bypassPermissions \
       --output-format json > "$TMPDIR/${site}.json"; then
    echo "scan: ===== ${site}: done =====" >&2
  else
    echo "scan: ===== ${site}: claude exited nonzero =====" >&2
  fi
done

# Aggregate every site's result into ONE combined object for n8n's Parse node.
node -e '
  const fs = require("fs");
  const dir = process.argv[1];
  const sites = process.argv.slice(2);
  const agg = { started_at: null, finished_at: null, site_summary: {}, candidates: [] };
  for (const site of sites) {
    let env;
    try { env = JSON.parse(fs.readFileSync(dir + "/" + site + ".json", "utf8")); }
    catch (e) { agg.site_summary[site] = { status: "error", count: 0 }; continue; }
    let inner = (env && env.result !== undefined) ? env.result : env;
    let payload = null;
    if (typeof inner === "string") {
      const a = inner.indexOf("{"), b = inner.lastIndexOf("}");
      if (a >= 0 && b > a) { try { payload = JSON.parse(inner.slice(a, b + 1)); } catch (e) {} }
    } else if (inner && typeof inner === "object") {
      payload = inner;
    }
    if (payload && Array.isArray(payload.candidates)) {
      agg.candidates.push(...payload.candidates);
      Object.assign(agg.site_summary, payload.site_summary || {});
    } else {
      agg.site_summary[site] = { status: "error", count: 0 };
    }
  }
  process.stdout.write(JSON.stringify(agg));
' "$TMPDIR" $SITES
