# Automated Job Scan — Feature Overview (North Star)

**Date:** 2026-06-26
**Status:** Approved overview — drives the design spec + implementation plans
**Author:** Dave Charm Bulaquena (with Claude)

> This document is the **north star**. Every story, spec section, and PR for the
> Job Scan feature must trace back to a User Story (US), satisfy its Acceptance
> Criteria (AC), and meet its Definition of Done (DOD) below. The detailed
> design lives in `2026-06-26-job-scan-design.md`; if the two ever disagree, this
> overview wins and the design is corrected.

## Vision (one sentence)

On a schedule, an external Claude-driven Playwright scan reads Indeed, OnlineJobs
PH, JobStreet, and LinkedIn for my configured job titles, picks the 3 best-fitting
roles per site against my canonical CV, captures each full job description, files
them as de-duplicated **candidates**, pings me on Google Chat, and lets me turn
any candidate into a tailored CV package in one click — no copy-paste.

## Boundary / architecture (the load-bearing decision)

The scanner is an **external ingestion agent**, in the same category as the
existing n8n Upwork/OnlineJobs/LinkedIn flows that POST to `/api/paste`. It runs
*outside* the app boundary:

```
n8n (Railway, Docker, Cron)
  → custom image: claude -p "<scan prompt>" + Playwright MCP   ← scrape + rank (the "smart" part)
  → n8n HTTP node POSTs structured JSON
        → jobhunter app  POST /api/scan/results               ← dedup, persist, notify (tested boundary)
              ├── Supabase           ← scan_settings, scans, scan_candidates
              ├── notifier.py        ← GChat (dashboard link, reused)
              └── run_tailoring()    ← "Generate CV" reuses existing pipeline, unchanged
```

This keeps `DECISIONS.md §4` intact: the **app** still has one LLM provider via
`llm_client.py`. The scanner's LLM usage is upstream, exactly like today's n8n
scraper flows. The app side is fully unit-testable; the flaky browser/anti-bot
work stays in n8n where flaky things belong.

## Non-goals (YAGNI — explicitly out of scope)

- **No auto-apply / auto-submit.** The human always presses submit
  (`DECISIONS.md §5/§6`). The scan *discovers*; it never applies.
- **No in-app scheduler.** Scheduling lives in n8n cron, not the Python app.
- **No raw job-board links in notifications.** GChat links to the dashboard only,
  preserving `notifier.py`'s "no job-board hostnames" guardrail (FR44/FR11).
- **No re-scan of seen jobs.** Dedup by URL is permanent (global, not windowed).
- **No new tailoring path.** "Generate CV" reuses `POST /api/paste` +
  `run_tailoring()` verbatim.

---

# Features

Six features, each independently shippable in roughly this order. F2 (the scan
engine) depends on F1 + F3 existing as contracts.

| # | Feature | One-liner |
|---|---------|-----------|
| F1 | Scan Settings | Configure *what* to search (titles, sites, picks/site) from the UI. |
| F2 | Scan Engine (n8n + Claude + Playwright) | The scheduled external run that scrapes, ranks, and POSTs candidates. |
| F3 | Candidate Ingestion & Dedup | App endpoint that accepts results, dedups by URL, persists. |
| F4 | Scan Notification | GChat ping summarizing new candidates, linking to the dashboard. |
| F5 | Candidate Dashboard | New "Job Scan" page: scans by date → site → candidate cards. |
| F6 | One-Click Generate CV | Turn a candidate into a tailored package, reusing the pipeline. |

---

## F1 — Scan Settings

**US:** *As the single user, I want to configure my search job titles, which sites
to scan, and how many picks per site, from the Settings page, so the scan looks
for the right roles without me editing code or redeploying.*

**AC:**
1. A "Job Scan" section exists in `/settings` with editable: `search_titles[]`
   (1..N free-text), `sites_enabled` (subset of indeed / onlinejobs_ph /
   jobstreet / linkedin), `picks_per_site` (int, default 3, range 1–10),
   `enabled` (master on/off).
2. Settings persist in a Supabase `scan_settings` row and survive app restarts.
3. `GET /api/scan/settings` returns current settings; `PUT /api/scan/settings`
   validates and saves them (rejects empty `search_titles`, unknown sites,
   out-of-range `picks_per_site`).
4. With `enabled=false`, a scan run is a no-op that records nothing and notifies
   nothing.
5. No secret-shaped keys are stored in `scan_settings` (secrets stay in `.env`).

**DOD:**
- Migration for `scan_settings` checked in; applies cleanly to local + hosted.
- Endpoints implemented with request/response validation + unit tests (happy
  path, each validation failure, enabled=false no-op contract).
- Settings UI section renders current values, saves, and shows a save confirmation
  + validation errors.
- Defaults documented; `README` "Configuration" updated.
- `pytest -q` green; `ruff`/`mypy` clean on new modules.

---

## F2 — Scan Engine (n8n + Claude + Playwright)

**US:** *As the single user, I want a scheduled external job that searches each
enabled site for my titles, skips jobs I've already seen, picks the 3 best fits
per site against my canonical CV, and captures each full job description, so I get
a curated shortlist without lifting a finger.*

**AC:**
1. An n8n workflow on Railway: **Cron trigger → fetch settings + condensed
   canonical-CV profile + known-URL skip-list from the app → `claude -p` (custom
   image with Claude Code + Playwright MCP) → n8n HTTP node POSTs structured JSON
   to `/api/scan/results`.**
2. The custom Docker image builds and runs `claude -p ... --output-format json`
   with the Playwright MCP available.
3. The Claude run, per enabled site, searches each `search_title`, **excludes any
   URL in the known-URL skip-list before deep-scraping**, ranks remaining
   listings by fit to the canonical-CV profile, selects top `picks_per_site`, and
   scrapes the **full JD text** for each pick.
4. Output is a single JSON payload: a scan summary (per-site `ok` | `blocked` |
   `empty` + count) and a `candidates[]` array (`site`, `url`, `title`,
   `company`, `location`, `jd_text`, `fit_reason`, `fit_score`).
5. A blocked/empty/zero-result site is reported as a normal state in the summary,
   **not** an error that aborts the run; other sites still complete.
6. The POST authenticates with the existing `INGEST_TOKEN` (Bearer), set in n8n.

**DOD:**
- Custom n8n image Dockerfile + build documented in `docs/deployment/` (or n8n
  notes); image runs Claude Code + Playwright MCP successfully.
- n8n workflow exported/checked in (JSON) and documented; Cron schedule recorded.
- Scan prompt template versioned in `prompts/` (e.g. `job_scan.v1.md`) and
  referenced by the workflow.
- A documented manual test: trigger the workflow once, observe a real payload
  POSTed and candidates appearing in the dashboard.
- Anti-bot reality acknowledged in docs: stealth/pacing settings, "0 results is
  normal," and the per-site status surfaced downstream.

---

## F3 — Candidate Ingestion & Dedup

**US:** *As the single user, I want the app to accept scan results, drop anything I
already have, and store the rest, so my candidate list is clean and never repeats
a job.*

**AC:**
1. `POST /api/scan/results` accepts the F2 payload (Bearer `INGEST_TOKEN`),
   validates shape, and is idempotent: re-POSTing the same candidates inserts no
   duplicates.
2. Dedup is enforced by a **`UNIQUE` constraint on `scan_candidates.url`**;
   candidates whose URL already exists are skipped (not errored).
3. The endpoint creates one `scans` row (with the per-site summary) and inserts
   only the new candidates, then returns counts: `{received, new, skipped}`.
4. `GET /api/scan/known-urls` returns all stored candidate URLs (for the F2
   skip-list).
5. `GET /api/scan/candidates?status=` lists candidates (filterable by status);
   `PATCH /api/scan/candidates/{id}` supports `status=dismissed`.
6. New candidates default to `status=new`. Valid transitions: `new → generated`,
   `new → dismissed`.

**DOD:**
- Migration for `scans` + `scan_candidates` (with `UNIQUE(url)` and FK) checked
  in; applies locally + hosted.
- Endpoints implemented with validation + unit tests: happy path, duplicate URL
  skip, malformed payload, idempotent re-POST, status filter, dismiss,
  invalid-transition rejection.
- `pytest -q` green; `ruff`/`mypy` clean on new modules.

---

## F4 — Scan Notification

**US:** *As the single user, I want a Google Chat message after each scan telling me
how many new candidates were found and where, so I know to open the dashboard —
without job-board links leaking into chat.*

**AC:**
1. After `POST /api/scan/results` persists new candidates, a single GChat message
   is sent summarizing total new + per-site counts and a link to the dashboard
   Job Scan page.
2. The message contains **no job-board hostnames** (preserves the existing
   notifier guardrail); the only link is to the local app.
3. When a scan yields **zero** new candidates, no notification is sent (no noise).
4. Notification failures are non-fatal and logged (candidates already persisted),
   matching existing notifier behavior.
5. Reuses `notifier.py` (one outbound integration) rather than adding a new one.

**DOD:**
- Notification message builder implemented + unit tested (counts rendering,
  zero-new suppression, no-job-board-hostname assertion, dashboard link present).
- Failure path tested (notify raises → ingest still returns success).
- `pytest -q` green.

---

## F5 — Candidate Dashboard

**US:** *As the single user, I want a "Job Scan" page that shows my scans by date,
broken down by site, with a card per candidate (title, company, location, fit
reason/score, job link, JD preview), so I can review the shortlist and act on it.*

**AC:**
1. A new "Job Scan" item appears in the sidebar, routing to a new page (distinct
   from the existing `/scans` flow-telemetry page).
2. The page lists scans **newest first**; each scan shows its date and per-site
   status (`ok` / `blocked` / `empty` + counts).
3. Within a scan, candidates are grouped **by site**; each card shows title,
   company, location, `fit_reason`, `fit_score`, the job-board link (opens in new
   tab), and a JD preview (expandable to full).
4. Each `new` card has **Generate CV** and **Dismiss** actions; `dismissed`
   candidates are hidden or visually de-emphasized; `generated` cards link to the
   produced package.
5. Empty state (no scans yet) is handled gracefully.

**DOD:**
- Page + sidebar route implemented in the React app, reading the F3 endpoints.
- Renders real data end-to-end (scans → sites → candidates) against a seeded DB.
- Frontend builds (`npm run build`) clean; no type errors.
- Visual check captured (screenshot) showing grouped candidates + actions.

---

## F6 — One-Click Generate CV

**US:** *As the single user, I want to click "Generate CV" on a candidate and get a
tailored package without pasting anything, because the full JD was already
captured, so discovery flows straight into tailoring.*

**AC:**
1. Clicking **Generate CV** calls `POST /api/paste` with the candidate's stored
   `{jd_text, url, source: <site>}`; `run_tailoring()` runs **unchanged**.
2. On success, the candidate flips to `status=generated` and stores the returned
   `slug`; the card links to the package page.
3. The produced package behaves identically to a manually pasted one (drift
   checks, held-vs-passed, applications-tracker linkage all work).
4. A generate failure (e.g. spend cap hit) surfaces a clear error and leaves the
   candidate as `new` (retryable); no partial/orphaned state.
5. No new tailoring code path is introduced.

**DOD:**
- Generate action wired end-to-end; candidate→package→(tracker) linkage verified.
- Unit/integration test: generate from a candidate produces a package and sets
  `status=generated` + `slug`; failure leaves `status=new`.
- Manual verification: one real candidate → one real package via the button.
- `pytest -q` green; frontend builds clean.

---

## Global Definition of Done (the whole feature is "done" when…)

- All six features meet their individual DODs.
- `pytest -q` (the only hard CI gate) is green; `ruff`/`mypy` clean on new code.
- Migrations apply cleanly to a fresh local Supabase **and** the hosted project.
- A full loop is demonstrated once end-to-end: cron fires → sites scraped →
  candidates appear de-duplicated on the dashboard → GChat ping received →
  Generate CV produces a package.
- `DECISIONS.md` updated with a dated entry recording the scanner-as-external-
  ingestion-agent decision and the dashboard-only-notification choice.
- `README` updated: scan settings, the n8n custom image, and the Railway workflow.
- This north star and the design spec agree.

## Traceability

Each implementation plan and PR cites the feature ID (F1–F6) and the AC numbers it
satisfies. A PR that doesn't map to an AC here is out of scope until this document
is amended.
