# Job Scan — TODO / state

Branch: `feat/job-scan` (all local commits; **nothing pushed**).

## Done (committed)
- [x] App side: Supabase tables, `/api/scan/*` endpoints, dedup, GChat notify,
      Job Scan dashboard page, "Run scan now" button, `/api/canonical-profile`.
- [x] Scan prompt `prompts/job_scan.v1.md`.
- [x] Custom Docker image (Playwright + Claude Code + MCP) — built & verified.
- [x] n8n workflow created as a DRAFT in user's n8n (id `lFU4bsgLyUO4Evxj`).
- [x] Deployment runbook `docs/deployment/n8n-scan-engine.md`.

## Uncommitted / in-flight
- [ ] `canonical-cv.json` — user's highImpact toggle edits (recovered; not committed).
- [ ] Staged reorg toward a separate scanner service (moved run-scan.sh + mcp.json
      into `deploy/scanner/`, removed the custom-n8n Dockerfile) — **paused, user said don't build**.

## DECISION (locked by user 2026-06-27): Option B — original plan
Claude + Playwright run **inside n8n** (no separate service — user considers that
a duplicate). The user's n8n was set up from the **Railway n8n template** (stock
`n8nio/n8n` image + Postgres + volume). So Option B = change that n8n service to
build from our custom Dockerfile (official n8n behavior + Claude + Playwright
added), keeping the same Postgres + env so existing workflows/credentials survive.
Rollback = point the service back at the stock image (data safe in Postgres).
Tricky part to get right: the custom image must behave exactly like the template
n8n on Railway (port binding, webhook URL) AND have working Playwright/Chromium.

## Remaining work once decided (NOT started — user said don't build yet)
- [ ] Finish the chosen topology (scanner service + swap the workflow's one node, if C).
- [ ] Deploy: scanner service on Railway; set env; wire `N8N_SCAN_TRIGGER_URL`.
- [ ] App must be publicly reachable for the loop to close (currently localhost).
- [ ] Commit `canonical-cv.json`; push branch; merge/PR decision.

## Status (2026-06-27)
- ✅ Custom n8n image FIXED (Node 22.22) + VALIDATED: boots as n8n (`/healthz` OK),
  has Claude + Playwright. Safe to swap onto the Railway n8n service.
- ✅ Branches pushed; single PR open: https://github.com/davecharm16/jobhunter/pull/1
  (feat/job-scan → main, includes application-tracker + job-scan + CV toggles).

## DEPLOY STATE (2026-06-27)
APP: ✅ LIVE on AWS EC2 (t4g.small, arm64, Ubuntu 24.04). https://18.136.89.90.sslip.io
  - Caddy basic-auth (user `dave`), Let's Encrypt via sslip.io, docker-compose.prod.yml + Watchtower.
  - Fixes applied & committed: Node 22.22 bump; CADDY hash $$-escape in .env; FORWARDED_ALLOW_IPS=10.255.255.255
    (so uvicorn ignores XFF → app sees Caddy as loopback → basic-auth is the gate).
  - N8N_SCAN_TRIGGER_URL set on app = https://n8n-production-45e3.up.railway.app/webhook/scan-run
N8N: ✅ custom image (Claude 2.1.195 + Playwright) deployed on Railway from main/deploy/n8n/Dockerfile.
  - Vars on n8n service: APP_BASE_URL, CLAUDE_CODE_OAUTH_TOKEN (no ANTHROPIC_API_KEY).
  - Workflow "Job Scan — Discovery Engine" (id lFU4bsgLyUO4Evxj): 4 HTTP nodes set to Basic Auth
    (Authorization: Basic <base64 dave:pw>). NOT yet activated.

## BLOCKER (parked): n8n won't register the Execute Command node
- `n8n-nodes-base.executeCommand` file EXISTS in the image
  (/usr/local/lib/node_modules/n8n/.../ExecuteCommand/ExecuteCommand.node.js) but n8n UI says
  "not installed" and activation/publish errors "Unrecognized node type". No NODES_EXCLUDE env set.
  Cause not yet found (didn't check /root/.n8n/config or n8n version).
- GUARANTEED FIX (next session): drop the Execute Command node. Add a tiny HTTP helper to
  deploy/n8n/Dockerfile (e.g. node server that runs /opt/scan/run-scan.sh on POST), start it
  alongside `n8n start`; change the workflow's "Run Claude Scan" node → HTTP Request to
  http://127.0.0.1:<port>/run. No separate service, no Execute Command node.
- THEN remaining scan unknowns to verify: headless Claude auth in container, Playwright run,
  job-site anti-bot, then activate workflow + test "Run scan now".

## PLAN: Screenshot/Image → CV (via Claude Code vision)  [awaiting approval]

**Goal:** In the app, upload a job-posting **screenshot** instead of pasting JD text →
Claude Code (subscription, in n8n) extracts the JD from the image → app runs the
normal `run_tailoring()` → tailored CV package. No metered Claude-vision API.

**Architecture (honors DECISIONS §4):** CV generation stays in the app via
`llm_client`/`run_tailoring`. The image→JD *vision* is an EXTERNAL Claude-Code
step in n8n (same "external ingestion agent" pattern as the scanner). App calls
n8n for the JD text, then tailors in-app.

**DECIDED:** in-app upload (on the paste panel); confirm-first → extracted JD fills the
existing paste textarea for review/edit, then the normal Generate runs. So the image
step only EXTRACTS the JD (no tailoring); existing `/api/paste` does the CV. Cleaner +
smaller.

```
Frontend paste panel: "Upload screenshot" → app POST /api/extract-jd (image)
  → app base64s image → POST n8n image-vision webhook (Bearer)
      → n8n: write temp file → claude -p (reads image, IS_SANDBOX) → returns JD text
  → app returns { jd_text }  → frontend fills the JD textarea (user reviews/edits)
  → user clicks Generate → existing POST /api/paste → run_tailoring → CV
```

**Tasks (checkable):**
- [ ] T1 — n8n workflow "Image → JD": Webhook (POST, base64 image, responseMode lastNode)
      → Code node writes `/tmp/shot.png` → Execute Command `claude -p "Read /tmp/shot.png
      and output ONLY the full job-description text, no commentary"` (allowedTools Read,
      bypassPermissions, IS_SANDBOX) → Respond with `{ jd_text }`. VERIFY claude reads an
      image in `-p` mode (test the webhook with a sample screenshot before wiring).
- [ ] T2 — App `POST /api/extract-jd`: accept image upload, base64 + POST to
      `N8N_IMAGE_VISION_URL` (new env, Bearer INGEST), return `{ jd_text }` (NO tailoring).
      Vision call injected as a dependency (stub in tests). Errors: vision unreachable →
      502; empty JD → 422.
- [ ] T3 — Tests (TDD): success (stub → jd_text), vision-failure → 502, empty → 422.
- [ ] T4 — Frontend (PastePanel): "Upload screenshot" button → POST /api/extract-jd →
      put returned JD into the existing textarea (user reviews/edits) → existing Generate.
- [ ] T5 — Config + deploy: `N8N_IMAGE_VISION_URL` in .env(.example) + on EC2 app; build
      the n8n workflow via n8n-mcp; merge to main (app via Watchtower).
- [ ] T6 — E2E: upload a real job screenshot → JD fills textarea → Generate → CV.

**Risks:** verifying `claude -p` image reading (one unknown to shake out, like the scan);
screenshot size limits; vision occasionally misreads a noisy screenshot (confirm-first
mitigates).

## Branch/PR
- feat/job-scan merged to main via PRs #2/#3. Local feat/job-scan may be a few commits ahead
  (deploy docs/fixes) — merge when convenient.
