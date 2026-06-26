# n8n Scan Engine — deployment runbook

End state: a custom Docker image runs on Railway as the n8n service. An n8n
workflow (Cron + manual Webhook) fetches scan inputs from the app, runs
`claude -p` + Playwright MCP to scrape job sites, and POSTs results back to
`/api/scan/results`. New candidates appear on the `/job-scan` dashboard.

**Design spec:** `docs/superpowers/specs/2026-06-26-job-scan-design.md`  
**Feature north star:** `docs/superpowers/specs/2026-06-26-job-scan-feature-overview.md` — **F2**.

> **Security:** the n8n admin UI must NOT be publicly exposed (same rule as the
> Oracle Cloud topology — expose only the app's public endpoint). The scan engine
> calls the app over the public `APP_BASE_URL`; the app's `require_ingest_token`
> middleware guards all machine endpoints.

## 0. Prerequisites (verify before building)

| # | What | How to check |
|---|------|--------------|
| P1 | App is reachable at a public `APP_BASE_URL` (deployed, or a `cloudflared` tunnel for testing) | `curl $APP_BASE_URL/api/scan/settings` → 200 |
| P2 | `INGEST_TOKEN` value known (from the app's `.env`) | `grep INGEST_TOKEN .env` |
| P3 | Claude Code OAuth token minted for the scanner (uses your Pro/Max subscription) | `claude setup-token` — prints the token once; store it immediately |
| P4 | Railway project lets you deploy a custom Dockerfile for the n8n service | Railway service → Settings → Build |

**P3 detail:** `claude setup-token` prints a ~1-year token to stdout; it is not
saved for you. Set it as `CLAUDE_CODE_OAUTH_TOKEN` on the Railway n8n service
(step 3 below). Do **not** set `ANTHROPIC_API_KEY` on the service — if it is set,
it takes precedence and switches the scanner to metered API billing instead of
your subscription.

## 1. The custom image

The stock `n8nio/n8n` image is Alpine-based and makes Chromium installation
painful. Instead, we start from the official **Microsoft Playwright `jammy` base**
(Debian, Node, Chromium + all OS deps pre-installed) and layer n8n, the Claude
Code CLI, and the Playwright MCP on top.

| File | Role |
|------|------|
| `deploy/n8n/Dockerfile` | Image definition: Playwright jammy base → npm install n8n + claude-code + @playwright/mcp → bake scan assets into `/opt/scan` |
| `deploy/n8n/mcp.json` | MCP server config passed to `claude -p --mcp-config`; wires `npx @playwright/mcp --headless --browser chromium` |
| `deploy/n8n/run-scan.sh` | The script the n8n Execute Command node calls: reads the assembled prompt from stdin, runs `claude -p`, emits the `--output-format json` envelope to stdout |
| `prompts/job_scan.v1.md` | Versioned scan prompt baked into `/opt/scan/job_scan.v1.md`; placeholders are filled by the n8n Code node before the Execute Command call |

**Build context is the repo root** (so `COPY prompts/…` resolves):

```bash
docker build -f deploy/n8n/Dockerfile -t jobhunter-n8n-scan:dev .
```

Smoke-test the toolchain locally:

```bash
docker run --rm jobhunter-n8n-scan:dev claude --version
docker run --rm jobhunter-n8n-scan:dev sh -lc 'ls /opt/scan && which n8n'
docker run --rm jobhunter-n8n-scan:dev node -e "console.log('node ok')"
```

End-to-end headless test (proves Claude + Playwright MCP work inside the image;
requires `CLAUDE_CODE_OAUTH_TOKEN` exported in your shell):

```bash
docker run --rm -e CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  jobhunter-n8n-scan:dev \
  sh -lc 'echo "Use Playwright to open https://example.com. Return ONLY {\"h1\":\"<text>\"}." \
    | /opt/scan/run-scan.sh'
```

## 2. Deploy to Railway

### 2a. Point the Railway n8n service at the Dockerfile

In the Railway n8n service:

1. Settings → Build → **Dockerfile path**: `deploy/n8n/Dockerfile`
2. **Build context**: repo root (so `COPY deploy/n8n/...` and `COPY prompts/...` paths resolve).
3. Trigger a deploy.

### 2b. Set the service environment variables

Add these variables in Railway → n8n service → Variables:

| Variable | Value | Notes |
|----------|-------|-------|
| `CLAUDE_CODE_OAUTH_TOKEN` | output of `claude setup-token` | Runs scans on your Claude subscription |
| `INGEST_SHARED_TOKEN` | same value as the app's `INGEST_TOKEN` | Bearer token for all app calls |
| `APP_BASE_URL` | the app's public base URL, e.g. `https://<app-host>` | No trailing slash |

**Do NOT set `ANTHROPIC_API_KEY`** on the n8n service. If it is present, the
Claude CLI uses it (metered billing) instead of `CLAUDE_CODE_OAUTH_TOKEN`
(subscription). Remove it if it already exists.

Leave all existing n8n persistence variables (DB URL, encryption key, etc.)
unchanged.

### 2c. Verify the deployed container

In the Railway service shell (or a one-off command):

```bash
claude --version && ls /opt/scan && node -v && n8n --version
```

Expected: versions print; `/opt/scan` lists `mcp.json`, `run-scan.sh`,
`job_scan.v1.md`; n8n UI loads normally.

### 2d. Reconcile Claude CLI flags

```bash
claude -p --help
```

Confirm the flags used in `deploy/n8n/run-scan.sh` match the installed version:
`--mcp-config`, `--allowedTools`, `--permission-mode`, `--output-format`. If any
flag name has changed, update `run-scan.sh`, rebuild, and redeploy. Commit the
fix as `fix(scan-engine): reconcile claude CLI flags [F2]`.

## 3. The n8n workflow

Workflow file: `deploy/n8n/job-scan-workflow.json` (exported from n8n in Task 5).

### Node design (in execution order)

**Entry points (two triggers, shared path):**

- **Cron** node — daily at 08:00 Asia/Manila (or your preferred schedule).
- **Webhook** node — path `scan-run`, method POST. This is the URL the app's
  "Run scan now" button pings via `N8N_SCAN_TRIGGER_URL`.

**Fetch inputs (three HTTP Request nodes):**

Each carries `Authorization: Bearer {{$env.INGEST_SHARED_TOKEN}}`.

| Method | URL | Notes |
|--------|-----|-------|
| GET | `{{$env.APP_BASE_URL}}/api/scan/settings` | Returns `search_titles`, `sites_enabled`, `picks_per_site`, `enabled` |
| GET | `{{$env.APP_BASE_URL}}/api/scan/known-urls` | Returns `{"urls": [...]}` — skip-list for dedup |
| GET | `{{$env.APP_BASE_URL}}/api/canonical-profile` | Returns condensed CV profile for Claude's ranking |

After fetching settings, an **IF** node checks `settings.enabled`. If `false`,
the run exits via a No-Op node — nothing is POSTed.

**Assemble the prompt (Code node):**

Reads `/opt/scan/job_scan.v1.md` and replaces the placeholder tokens:

| Token | Value |
|-------|-------|
| `{{SEARCH_TITLES}}` | `settings.search_titles` (JSON array or newline list) |
| `{{SITES_ENABLED}}` | `settings.sites_enabled` (JSON array) |
| `{{PICKS_PER_SITE}}` | `settings.picks_per_site` |
| `{{CANONICAL_PROFILE}}` | `JSON.stringify(profile)` |
| `{{KNOWN_URLS}}` | `JSON.stringify(urls)` |

Outputs the assembled prompt string.

**Execute Command node:**

Command: `/opt/scan/run-scan.sh`  
The assembled prompt is piped to the command's **stdin**. `run-scan.sh` passes it
to `claude -p` with `--mcp-config /opt/scan/mcp.json`, `--allowedTools
"mcp__playwright__*"`, `--permission-mode bypassPermissions`, and
`--output-format json`. Stdout is captured.

> `--permission-mode bypassPermissions` (equivalent to
> `--dangerously-skip-permissions`) is required for headless MCP tool use.

**Parse + validate (Code node):**

`claude -p --output-format json` wraps the response in an envelope with a
`result` field. Parse the envelope, extract `result`, `JSON.parse` it, and
validate it has `site_summary` + `candidates[]` with the required fields (`site`,
`url`, `title`, `company`, `location`, `jd_text`, `fit_reason`, `fit_score`).
On parse failure, throw — n8n marks the run as errored; nothing partial is POSTed.

**POST results (HTTP Request node):**

```
POST {{$env.APP_BASE_URL}}/api/scan/results
Authorization: Bearer {{$env.INGEST_SHARED_TOKEN}}
Content-Type: application/json
```

Body: the validated JSON object (`started_at`, `finished_at`, `site_summary`,
`candidates[]`). The app responds with `{scan_id, received, new, skipped}`.

## 4. Wire the "Run scan now" button

1. Copy the Webhook node's **production URL** from n8n (e.g.
   `https://<n8n-host>/webhook/scan-run`).
2. Add to the app's `.env`:
   ```
   N8N_SCAN_TRIGGER_URL=https://<n8n-host>/webhook/scan-run
   ```
3. Restart the app (`jobhunter` process or Docker container).
4. On `/job-scan`, click **Run scan now**. Expected: alert "Scan started…", the
   n8n workflow appears in Executions, new candidates appear on the dashboard
   after it completes.
5. Run twice to confirm dedup — the second POST's `new` count should be 0 (or
   lower), and no duplicate candidate cards appear.

## 5. Auth model

The scan engine is a non-loopback caller and must present
`Authorization: Bearer <INGEST_SHARED_TOKEN>` on every call to a token-guarded
endpoint. See `docs/n8n-contract.md` for the shared contract.

The scanner runs under your **Claude subscription** (Pro/Max) via
`CLAUDE_CODE_OAUTH_TOKEN`. Each scan is a multi-step agentic run with browser
tool calls; usage counts against your Pro/Max plan limits — the **same** quota
you use for coding. This is separate from the app's `MONTHLY_SPEND_CAP_USD`,
which guards only `run_tailoring()` (the app's own LLM calls). Tune the Cron
schedule and `picks_per_site` if usage is high.

## 6. Known issues and tips

**(a) Pin npm packages for reproducible Railway builds.**
The Dockerfile installs `n8n@latest` and `@playwright/mcp@latest` at build time.
For reproducible builds, pin these (e.g. `n8n@2`, `@playwright/mcp@<version>`).
Check the installed Playwright base tag and match the MCP version to it.

**(b) EBADENGINE warning.**
n8n may warn that the installed Node version is older than n8n expects. n8n still
runs in most cases, but if it misbehaves at runtime, bump the Node version in the
Dockerfile (e.g. add an `nvm install` step or switch to a newer Node base before
installing n8n).

**(c) Anti-bot: Railway is a datacenter IP.**
Indeed, LinkedIn, and JobStreet actively block datacenter IPs. Expect per-site
`status: "blocked"` or `status: "empty"` results, especially on the first few
runs — this is normal, not a failure. The workflow continues across all enabled
sites; a residential proxy is a future option if blocking is persistent.

**(d) Reconcile `claude -p` flags against the installed CLI version.**
Run `claude -p --help` inside the deployed container (step 2c) and confirm the
flag names in `run-scan.sh`. The Claude Code CLI evolves; flag names can change
between versions.
