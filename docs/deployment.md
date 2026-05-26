# Job Hunter — deployment & usage guide

End state: a localhost web app at `http://127.0.0.1:8765` where you paste a JD and get a tailored CV + cover letter (or Upwork proposal) with three drift checks gating quality. Single-user, single-machine, no cloud anywhere except the LLM call.

---

## Prerequisites

| | check |
|---|---|
| Python ≥ 3.11 | `python3 --version` |
| Node.js ≥ 18 | `node --version` |
| Anthropic API key (`claude-haiku-4-5` access) | from `console.anthropic.com` |
| Optional: Google Chat incoming webhook URL | for pass notifications |
| Optional: an n8n instance | for the automated front door (Part 4) |

---

## Part 1 — One-time setup (~5 minutes)

### 1.1 Install

```bash
git clone <repo-url>
cd job_hunter

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[web,dev]"

cd src/jobhunter/web/frontend
npm install
npm run build
cd ../../../..
```

The frontend build produces a static bundle the FastAPI app serves. Re-run `npm run build` only when you change frontend code; runtime doesn't need Node.

### 1.2 Configure secrets

```bash
cp .env.example .env
```

Edit `.env`:

```bash
LLM_API_KEY=sk-ant-...                  # Anthropic API key (required)
MONTHLY_SPEND_CAP_USD=25.00             # hard cap; pipeline refuses to run when reached

# Optional:
GCHAT_WEBHOOK_URL=                      # Google Chat incoming webhook; leave blank to skip notifications
INGEST_TOKEN=                           # only set if you'll run n8n flows (Part 4)
# LLM_CALL_TIMEOUT_SECONDS=60           # override per-call timeout (default 60s)
```

`.env` is in `.gitignore`. Double-check with `git check-ignore .env` — it should exit 0.

### 1.3 Set up your canonical CV

Replace `canonical-cv.json` with your real CV. Format = JSON Resume v1.0.0 — see [jsonresume.org/schema](https://jsonresume.org/schema/) for the full field list.

Two key extension fields beyond stock JSON Resume:

- **`tags: ["python", "fintech"]`** on `work[]`, `projects[]`, `skills[]` entries. Tags drive JD-relevance matching for the content-loss check — when a JD lists `python` as a must-have, every tagged-`python` entry becomes relevant.
- **`highImpact: true`** on your strongest entries. The content-loss check fails the package when a high-impact, JD-relevant entry was silently dropped.

Validate after editing:

```bash
python scripts/validate_canonical_cv.py
```

Exits 0 on success. Errors point at the offending field via JSON Pointer (e.g. `/work/0/startDate`).

A worked example with both extensions lives at `samples/canonical-cv-with-extensions.json`.

### 1.4 Tune `config.yaml` (optional, do later)

`config.yaml` ships with conservative defaults (high recall — more false positives, fewer false negatives). Don't touch on day one. After 20+ real applications, edit based on override patterns:

| Setting | Default | Tune if … |
|---|---|---|
| `keyword_stuffing.max_density_pct` | `1.5` | Density check over-flags → raise to 2.0 |
| `fabrication.semantic_threshold` | `0.65` | Honest paraphrase over-flags → raise to 0.75 |
| `drift.content_loss.tag_overlap_min` | `1` | Too many entries marked "must appear" → raise to 2 |
| `held_package_ttl_days` | `7` | Want held packages kept forever → set to `0` |
| `proposal.max_words` | `250` | Upwork proposals over-truncate → raise to 350 |

Per-channel overrides exist for keyword-stuffing (the Upwork proposal legitimately repeats JD phrasing, so Upwork can be looser). See the commented `keyword_stuffing.channels.upwork` block in `config.yaml`.

---

## Part 2 — Run it

### 2.1 Boot the server

```bash
jobhunter
```

stderr logs:

```
jobhunter web app listening on http://127.0.0.1:8765/
```

Browser auto-opens (skip with `--no-browser`; override port with `--port 9000`).

### 2.2 First tailoring run

1. Find a real JD you'd actually apply to (Upwork, LinkedIn, OJ.ph, or other).
2. Paste it into the textarea on the Dashboard.
3. Click **Tailor this JD**.
4. Pipeline runs: parse → classify board → tailor (CV + cover-letter OR Upwork proposal) → claim extraction → 3 drift checks → metadata + held/passed verdict.
5. Browser navigates to `/packages/<slug>` on success. Read the staged artifacts. Click **View drift diagnostics** to see `/packages/<slug>/drift`.

Per-package files at `./out/<slug>/`:

| File | When |
|---|---|
| `cv.md` | always |
| `cover-letter.md` OR `upwork-proposal.md` | always (per-board selection) |
| `metadata.json` | always (full pipeline metadata) |
| `package.drift.json` | always (machine-readable drift report) |
| `claims.json` | always (atomic claims extracted for fabrication-check traceability) |
| `tailoring.trace.json` | always (logged drop rationales, currently empty) |
| `package.held.json` | only when any drift check fails |
| `drift-report.md` | only when any drift check fails (human-readable summary) |

### 2.3 Review held packages

If any drift check failed, the package is **held** — staged on disk, no GChat ping. The Dashboard's held-count card + recent-packages table show the queue.

Click into the package, read `/packages/<slug>/drift`. Three outcomes:

1. **The drift is real and the package shouldn't ship.** Let it sit; auto-discard after `held_package_ttl_days` (default 7).
2. **The drift is a false positive.** Click **Approve override** → fill in `reason` (required, non-empty) + tick `ack_drift` (required) → package moves to `./out/_overridden/<slug>/` with a structured `override` record in the metadata. Open and submit manually.
3. **The drift surfaces a real tuning gap.** Edit `config.yaml`, re-paste the JD (you'll need to edit slightly — see Slug collisions in Gotchas).

### 2.4 GChat notifications (optional)

If `GCHAT_WEBHOOK_URL` is set, every passing package POSTs one message:

```
Senior Python role — upwork — 3 must-haves matched
Board: upwork
Role: Senior Python Engineer
Cost: $0.004200
Package: file:///Users/you/job_hunter/out/<slug>
Ready for your review — submit when satisfied
```

Failure path: structurally silent. The pipeline NEVER POSTs to GChat on a held package — verified by Story 6.2's call-graph guard tests.

---

## Part 3 — Operations

### 3.1 Where things live

```
./out/<slug>/                # passed + held packages (held=true in metadata)
./out/_overridden/<slug>/    # packages you approved via override
./out/_discarded.log         # JSON-lines audit of TTL-swept held packages
./.cost-ledger.json          # monthly LLM spend (gitignored)
```

### 3.2 Cost cap behavior

Pipeline returns HTTP 402 with `{"error": "monthly_spend_cap_reached", "current_usd": "...", "cap_usd": "..."}` when the monthly cap is hit. Bump `MONTHLY_SPEND_CAP_USD` in `.env` and restart `jobhunter` to continue.

Inspect spend:

```bash
cat .cost-ledger.json | jq '.["2026-05"]'
```

Per-app target is `$0.25` end-to-end (Anthropic Haiku pricing). Actual is usually well under a cent.

### 3.3 Held-queue TTL

Old held packages sweep at the top of every pipeline run. To inspect what's been discarded:

```bash
tail -20 out/_discarded.log
```

Each line is JSON: `{slug, source_board, drift_fail_reason, held_at, discarded_at, created_at, failed_claims_count}`.

To disable sweeping entirely: `held_package_ttl_days: 0` in `config.yaml`.

### 3.4 Stats endpoint

```bash
curl http://127.0.0.1:8765/api/stats | jq
```

Returns applications_total, cost_per_app_avg/p95, monthly_spend, drift_catch_rate, override_rate, rolling 30-app interview_conversion_rate. The Dashboard's stats card renders the same.

Use override_rate per drift dimension as your tuning signal — vibes don't tell you whether your thresholds are too tight; this number does.

---

## Part 4 — Automated front door (optional)

n8n flows poll job sources on a cron and POST each new JD to your `/api/paste` endpoint. Three reference flows in `n8n/`.

### 4.1 Prerequisites

- A running n8n instance (Docker self-host OR [n8n cloud](https://n8n.io))
- The Job Hunter server reachable from n8n. Local-only: `INGEST_BASE_URL=http://127.0.0.1:8765` works if n8n runs on the same machine. Otherwise expose via [ngrok](https://ngrok.com) or similar tunnel.
- Set `INGEST_TOKEN=<random-secret>` in your `.env`. Restart `jobhunter`.

### 4.2 Import flows

For each of `n8n/upwork-search-flow.json`, `n8n/onlinejobs-ph-listings-flow.json`, `n8n/linkedin-email-parser-flow.json`:

1. n8n → **Workflows** → **Import from File** → select the JSON.
2. **Settings → Variables**, set:

| Variable | All 3 flows | Upwork only | OJ.ph only | LinkedIn only |
|---|---|---|---|---|
| `INGEST_BASE_URL` | ✓ (your server URL) | | | |
| `INGEST_SHARED_TOKEN` | ✓ (same value as `INGEST_TOKEN` in `.env`) | | | |
| `UPWORK_SEARCH_QUERY` | | ✓ (e.g. `"remote senior backend"`) | | |
| `OJPH_SEARCH_QUERY` | | | ✓ (e.g. `"full-stack-programming"`) | |
| `IMAP_HOST` `IMAP_PORT` `IMAP_USER` `IMAP_PASSWORD` | | | | ✓ (Gmail app-password setup) |

3. Activate the flow. Default schedule: every 6 hours for Upwork/OJ.ph; every 15 minutes for LinkedIn IMAP.

### 4.3 LinkedIn email parser — critical setup

**The LinkedIn flow MUST NOT crawl linkedin.com.** It reads LinkedIn's own outbound Job Alert emails from a dedicated Gmail inbox.

Setup:

1. Create a **dedicated Gmail account** — not your primary LinkedIn-registered email. This isolates the polling credentials from anything tied to your LinkedIn login.
2. Sign into LinkedIn with the dedicated account → set up Job Alerts → confirm subscription email lands in the dedicated inbox.
3. Enable Gmail 2FA + generate an **app password** for IMAP. Use the app password as `IMAP_PASSWORD`.
4. Import the flow JSON. The flow filters on `From: jobalerts-noreply@linkedin.com` and parses each email's job blocks. No `linkedin.com` URL is fetched — verified by the JSON's test guard.

### 4.4 Verify

Visit `/scans` in the browser. The Job Alerts & Automated Scans surface shows each flow's last-run timestamp + JD count + status. When a flow's status is `never_run`, the empty-state hint reminds you to set `INGEST_BASE_URL`.

---

## Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `pytest` shows 3 failures referencing `LLM_API_KEY` | `.env` exists; tests assume it doesn't | `mv .env .env.parked && pytest && mv .env.parked .env` |
| HTTP 409 on a re-paste of the same JD | Slug collision (deterministic from JD text + timestamp truncated to second) | Wait a second, OR edit the JD slightly, OR `rm -rf out/<slug>/` |
| HTTP 402 on paste | Monthly spend cap reached | Bump `MONTHLY_SPEND_CAP_USD`, restart `jobhunter` |
| HTTP 401 on a non-loopback POST | Missing/wrong `Authorization: Bearer` header | Check `INGEST_TOKEN` matches `INGEST_SHARED_TOKEN` in n8n |
| HTTP 422 on Approve action | `ack_drift` sent as string `"true"` instead of boolean `true` | Pydantic `StrictBool` — use the modal UI; for curl, pass `"ack_drift": true` (no quotes) |
| GChat ping never fires on pass | `GCHAT_WEBHOOK_URL` not set in `.env` | Set it; restart `jobhunter` |
| `jobhunter` command not found | venv not activated | `source .venv/bin/activate` |
| Frontend changes don't show up | Bundle cached | `cd src/jobhunter/web/frontend && npm run build` |

---

## What the brief calls v2 (do NOT touch yet)

Per the original product brief's risk mitigation, defer these until you've run **30+ real applications** through v1:

- Voice drift check
- Outcome learning loop (track which packages → interviews)
- Interview-prep handoff
- Standalone drift-check CLI for peer sharing
- Multi-CV / multi-profile support
- Hosted / multi-tenant variant

Build them when the override-rate signal from `GET /api/stats` tells you the v1 drift checks are stable. Not before.

---

## Architecture pointers

- **Foundational decisions:** [`DECISIONS.md`](../DECISIONS.md) — runtime, schema, LLM provider, web-only architecture.
- **LLM provider rationale (Epic 3):** `_bmad-output/decisions/llm-provider.md`.
- **n8n contract:** [`docs/n8n-contract.md`](./n8n-contract.md).
- **Design source of truth:** `design_guidelines/stitch-export/` (frozen Stitch export — re-export via Stitch MCP and overwrite, never hand-edit).
- **Sprint status:** `_bmad-output/implementation-artifacts/sprint-status.yaml`.
