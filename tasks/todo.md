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

## Status: PAUSED — waiting on user. Do not build.
