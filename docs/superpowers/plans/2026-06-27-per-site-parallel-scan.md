# Per-Site Parallel Scan — Plan (NOT YET BUILDING)

**Goal:** Replace the single all-sites Claude scan (slow, defers to background →
hangs/returns prose, zero live visibility) with **per-site scans that run in
parallel**, are reliable, and are observable.

## Why (problems with the current design)
- One Claude call does `picks × titles × sites` (e.g. 5×7×4 ≈ 140 listings) →
  too big for one turn → Claude **defers to a background task** and ends early →
  with `bg-wait=0` it then **hangs forever** (scan 30 did this).
- **No visibility** — `--output-format json` returns one buffered blob at the very
  end; you can't see which site is running or where it's stuck.
- **No isolation** — one blocked site (JobStreet) can stall/spoil the whole run.

## Target architecture
Each **site** is scanned by its own Claude + Playwright invocation
(`sites_enabled = [one site]`, 7 titles), and the per-site runs execute **in
parallel**. Results are merged and posted.

```
Trigger → Get Settings → Enabled? → Get Known URLs → Get Canonical Profile → Build Base Inputs
   ⇉ run 4 site scans IN PARALLEL:  Indeed | OnlineJobs PH | JobStreet | LinkedIn
       each: sites=[site] → Claude+Playwright (7 titles) → parse site JSON
   → Merge (combine candidates + site_summary) → Post Results to App
```

## Parallelism — how (DECISION NEEDED)
n8n does **not** truly run blocking `executeCommand` nodes concurrently (its
orchestrator runs one node at a time). So "4 nodes side by side" alone runs
*sequentially*. To get REAL parallelism, options:

- **Option C — shell-parallel inside one node (simplest true parallel):**
  `run-scan.sh` launches 4 per-site Claude processes with `&`, `wait`s for all,
  aggregates their JSON. One n8n node, genuine parallelism.
  *Cons:* per-site logs interleave in one node's output (less clean than per-node).
- **Option A — 4 nodes, background + poll:** each node launches Claude detached,
  writes its result to a file; a collector node waits for all 4 files.
  *Pros:* per-node visibility + parallel. *Cons:* most complex (PID/file handshake).
- **Option B — 4 parallel sub-workflows** (`Execute Sub-workflow`): clean per-run
  visibility; parallelism depends on n8n queue/concurrency settings.
- **Sequential fallback (4 nodes in turn):** dead reliable + per-node visibility,
  but ~4× wall-clock. (Not what you asked for, listed for completeness.)

## Resource constraint (DECISION NEEDED)
Parallel = **4 concurrent headless Chromium + 4 Claude processes + proxy** in the
Railway n8n container. Rough peak ~**1.5–2.5 GB RAM**. If the Railway plan's RAM
is below that → **OOM / crashes**. Mitigations: cap concurrency at **2**, raise
Railway resources, or go sequential. → *Need to confirm the n8n service's RAM.*

## Reliability (applies to every option)
- `sites=[one site]` keeps each call small → completes in one turn → **no deferral**.
- Revert `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` from `0` to a **finite** value
  (e.g. 900000 = 15 min) so a stuck site can never hang forever.
- Per-site failure isolated: a blocked site returns `{status: blocked}`, others
  still succeed and post.

## Logging / visibility (the "logs next time" ask)
- `claude -p --output-format stream-json --verbose`, **tee the stream to stderr**
  → visible in **n8n → Executions → that node → stderr** (live play-by-play:
  navigations, searches, scrapes, decisions).
- Per-node status (Options A/B) shows which site is running/blocked at a glance.
- *Optional:* per-site **incremental POST** so the dashboard + live banner fill in
  progressively ("Indeed ✓ · LinkedIn scanning…").

## Changes required
- `deploy/n8n/run-scan.sh`: per-site arg / parallel launch; finite bg-wait; stream
  logs. → **n8n image rebuild**.
- Workflow: per-site nodes + merge (or Option C single node). → **n8n API, no rebuild**.
- App (only if incremental posting): endpoint to append a site's results to the
  current scan. → app rebuild.
- **Stop the stuck scan 30** before any n8n rebuild.

## DECIDED (2026-06-27)
1. **Parallelism:** 4 separate per-site n8n nodes (per-site visibility/status).
2. **Concurrency:** cap at **2** concurrent (Railway RAM safety).
3. **Posting:** **incremental per-site** (progressive dashboard + banner).
4. **Logs:** `stream-json --verbose`, always on, teed to n8n stderr.

## Build approach implied by those choices (wrinkles to solve at build time)
- **2-concurrent across 4 separate nodes** is the tricky part: n8n won't natively
  run blocking command-nodes concurrently. Mechanism options to pick/verify when
  building:
  - **Sub-workflow + "Execute Sub-workflow" with batching/concurrency 2** — each
    site is a sub-workflow run; main workflow runs them 2 at a time. Cleanest fit
    for "separate nodes + cap 2 + per-site visibility". *Verify n8n honors the
    concurrency cap.*
  - **Background launch + semaphore + collector** — each node launches Claude
    detached to a result file; a controller enforces 2 in-flight, waits, collects.
    Fallback if sub-workflow concurrency doesn't behave.
- **Incremental per-site posting** needs an app change: per-site results must
  **append to the same scan record** (not create 4 scans). Plan:
  - On scan start: `scan_status` already flips to `running`. Create the scan row
    up front (or on first site post) and have each site POST append its candidates
    to the **current** scan.
  - Add `scan_status.per_site` (jsonb) so the banner can show
    `Indeed ✓ · LinkedIn scanning…`; each site post updates its slot.
  - New/extended endpoint, e.g. `POST /api/scan/site-results` {site, candidates,
    status} → append + dedup + update per-site status. `mark_scan_completed` fires
    when all enabled sites report (a final "collector" call, or count-based).
- **run-scan.sh**: take a single `--site` arg (scan one site), finite
  `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` (e.g. 900000), `stream-json --verbose`
  tee to stderr, POST that site's results incrementally.
- **Still TBD to confirm before building:** the Railway n8n service's RAM (to
  validate even 2-concurrent is safe), and which 2-concurrency mechanism n8n
  actually honors (quick spike test).

## Status: PLAN ONLY — awaiting "go" to build. Scan 30 still stuck; stop it first.

## NOT in scope right now
Building it. This doc is the plan only. Scan 30 is still running/stuck — we stop it
when we start building.
