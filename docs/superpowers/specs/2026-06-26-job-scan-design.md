# Automated Job Scan — Design Spec

**Date:** 2026-06-26
**Status:** Approved design, pending implementation plan
**Author:** Dave Charm Bulaquena (with Claude)
**North star:** `2026-06-26-job-scan-feature-overview.md` (US/AC/DOD). If this
spec and the overview disagree, the overview wins.

## Problem

Job Hunter today is **pull-only**: a JD has to arrive (paste, or an n8n flow
POSTing to `/api/paste`) before anything happens. There is no *discovery* — no
way to ask "what's out there for me right now?" Finding roles on Indeed,
OnlineJobs PH, JobStreet, and LinkedIn is manual, repetitive, and easy to let
slip. We want a scheduled scan that surfaces a small, high-fit, de-duplicated
shortlist with full JDs captured, so the only human step left is judgment +
pressing Generate.

## Key decisions

- **The scanner is an external ingestion agent, not part of the app runtime.**
  It is the same shape as the existing n8n Upwork/OnlineJobs/LinkedIn flows that
  POST to `/api/paste`. This preserves `DECISIONS.md §4` (the *app* keeps one LLM
  provider via `llm_client.py`); the scanner's Claude usage is upstream, outside
  the boundary. *(New DECISIONS.md entry to be added.)*
- **Scheduling stays in n8n** (Railway, Docker), not the Python app — consistent
  with the existing "scheduling lives in n8n" stance.
- **Claude thinks, n8n plumbs.** Claude (`claude -p --output-format json`) does
  the scrape + rank + JD capture and *returns JSON*. n8n's HTTP node performs the
  authenticated POST. This keeps delivery/auth deterministic and keeps Claude
  stateless (no app credentials in the agent).
- **Persistence: Supabase**, same pattern + rationale as the application tracker
  (`DECISIONS.md §7`). Candidates are mutable, queryable, relational, and need a
  cross-run UNIQUE dedup key — a poor fit for write-once disk sidecars.
- **Dedup is permanent and URL-keyed.** `UNIQUE(scan_candidates.url)`. "Don't
  rescan" is enforced twice: the agent receives a skip-list *before* deep
  scraping (saves tokens), and the DB rejects dupes *on insert* (correctness).
- **Notifications link to the dashboard, never to job boards** — preserves
  `notifier.py`'s no-job-board-hostname guardrail (FR44/FR11). Discovery ≠
  submission. *(Recorded in the new DECISIONS.md entry.)*
- **"Generate CV" reuses `POST /api/paste` + `run_tailoring()` verbatim.** Full
  JD is captured at scan time, so no new tailoring path and no paste step.

## Architecture

```
n8n (Railway / Docker / Cron trigger)
  │  1. GET /api/scan/settings        → titles, sites, picks_per_site, enabled
  │  2. GET /api/canonical-profile     → condensed CV profile for ranking
  │  3. GET /api/scan/known-urls       → skip-list (dedup at source)
  │  4. Execute Command:
  │       claude -p "<job_scan.vN prompt + injected settings/profile/skiplist>" \
  │              --output-format json          (custom image: Claude Code + Playwright MCP)
  │  5. HTTP Request node:
  │       POST /api/scan/results  (Authorization: Bearer INGEST_TOKEN)
  ▼
jobhunter app (FastAPI)
  ├── /api/scan/*  routes          ← settings, results-ingest, known-urls, candidates
  ├── Supabase Postgres            ← scan_settings, scans, scan_candidates
  ├── notifier.py                  ← GChat (dashboard link), reused, non-fatal
  └── POST /api/paste → run_tailoring()   ← "Generate CV", unchanged
        └── ./out/<slug>/          ← packages on disk, unchanged
React app
  └── /job-scan page               ← scans by date → site → candidate cards → Generate/Dismiss
```

## Data model (Supabase Postgres)

Migration file: `supabase/migrations/2026062600000_job_scan.sql` (timestamp to be
finalized at write time).

### `scan_settings` (single-row config)

| column          | type        | notes                                                  |
|-----------------|-------------|--------------------------------------------------------|
| id              | bool PK     | always `true` (single-row guard: `PK (id)` + `CHECK (id)`) |
| search_titles   | text[]      | non-empty                                              |
| sites_enabled   | text[]      | subset of {indeed, onlinejobs_ph, jobstreet, linkedin} |
| picks_per_site  | int         | default 3, `CHECK (1..10)`                              |
| enabled         | boolean     | default true; master switch                            |
| updated_at      | timestamptz | default now()                                          |

### `scans` (one row per run)

| column        | type        | notes                                                |
|---------------|-------------|------------------------------------------------------|
| id            | uuid PK     |                                                      |
| started_at    | timestamptz | from payload summary                                 |
| finished_at   | timestamptz | from payload summary                                 |
| status        | text        | `completed` \| `partial` (some sites blocked)        |
| site_summary  | jsonb       | `{indeed:{status:"ok",count:3}, ...}` per-site map   |
| created_at    | timestamptz | default now()                                        |

### `scan_candidates`

| column      | type        | notes                                                      |
|-------------|-------------|------------------------------------------------------------|
| id          | uuid PK     |                                                            |
| scan_id     | uuid FK     | → scans(id)                                                |
| site        | text        | indeed \| onlinejobs_ph \| jobstreet \| linkedin           |
| url         | text        | **UNIQUE** — dedup key                                      |
| title       | text        |                                                            |
| company     | text        | nullable                                                   |
| location    | text        | nullable                                                   |
| jd_text     | text        | full scraped JD                                            |
| fit_reason  | text        | why the agent picked it                                    |
| fit_score   | numeric     | nullable, 0–1 or 0–100 (agent-defined; informational)     |
| status      | text        | `new` \| `generated` \| `dismissed` (CHECK)               |
| slug        | text        | nullable; set when a package is generated                  |
| created_at  | timestamptz | default now()                                              |

Domain/storage split mirrors the tracker: `scan.py` (dataclasses + `ScanStore`
Protocol) and `scan_store_pg.py` (`PostgresScanStore`, psycopg v3,
`SUPABASE_DB_URL`).

## App endpoints (`src/jobhunter/web/routes/scan.py`)

Machine endpoints require `Authorization: Bearer INGEST_TOKEN` for non-loopback
callers (same auth helper as `/api/paste`). UI endpoints follow the loopback
model used elsewhere.

| Method | Path                          | Purpose                                              |
|--------|-------------------------------|------------------------------------------------------|
| GET    | `/api/scan/settings`          | Read settings (UI).                                  |
| PUT    | `/api/scan/settings`          | Validate + save settings (UI).                       |
| GET    | `/api/scan/known-urls`        | Skip-list for the agent (machine).                   |
| GET    | `/api/canonical-profile`      | Condensed CV profile for ranking (machine).          |
| POST   | `/api/scan/results`           | Ingest one run's payload; dedup; persist; notify.    |
| GET    | `/api/scan/candidates`        | List (filter `?status=`, `?scan_id=`) (UI).          |
| PATCH  | `/api/scan/candidates/{id}`   | `status=dismissed` (UI).                             |

### `POST /api/scan/results` contract

Request:
```json
{
  "started_at": "2026-06-26T01:00:00Z",
  "finished_at": "2026-06-26T01:07:30Z",
  "site_summary": {
    "indeed":       {"status": "ok",      "count": 3},
    "onlinejobs_ph":{"status": "ok",      "count": 3},
    "jobstreet":    {"status": "blocked", "count": 0},
    "linkedin":     {"status": "empty",   "count": 0}
  },
  "candidates": [
    {
      "site": "indeed",
      "url": "https://www.indeed.com/viewjob?jk=...",
      "title": "Solutions Architect",
      "company": "Acme",
      "location": "Remote (PH)",
      "jd_text": "Full job description text...",
      "fit_reason": "Strong mobile + solutions-design overlap; remote.",
      "fit_score": 0.86
    }
  ]
}
```
Behavior: validate shape → insert `scans` row → for each candidate, insert unless
`url` exists (skip on conflict) → if `new > 0` and a webhook is configured, notify
→ return `{ "scan_id": "...", "received": N, "new": M, "skipped": K }`.
Idempotent: re-POSTing the same `candidates` inserts 0 new.

## The n8n workflow + custom image

- **Custom Docker image** extends the n8n base with: Node + Claude Code CLI +
  Playwright (Chromium + OS deps) + the Playwright MCP wired into the agent's
  `.mcp.json`. Documented in `docs/deployment/`. Concern to validate during
  build: image size + Railway memory headroom for headless Chromium.
- **Workflow nodes:** `Cron` → `HTTP Request` (settings) → `HTTP Request`
  (canonical-profile) → `HTTP Request` (known-urls) → `Set`/`Function` (assemble
  the prompt) → `Execute Command` (`claude -p ... --output-format json`) →
  `Function` (parse/validate JSON) → `HTTP Request` (POST results with Bearer
  token from n8n credentials). Exported workflow JSON checked into the repo.
- **Auth:** `INGEST_TOKEN` stored as an n8n credential, not in the prompt. Claude
  never sees app credentials.
- **Anti-bot posture (documented, expected to iterate):** persistent browser
  profile/cookies volume for logged-in sites; human-like pacing; stealth launch
  flags; treat `blocked`/`empty` as normal per-site outcomes. Railway is a
  datacenter IP — a residential proxy may become necessary for Indeed/LinkedIn;
  noted as a known risk, not solved in v1.

## Scan prompt (`prompts/job_scan.v1.md`)

Versioned like other prompts (`prompts.py` loader picks highest version). The
workflow injects, at runtime: `search_titles`, `sites_enabled`, `picks_per_site`,
the condensed canonical profile, and the known-URL skip-list. The prompt instructs
Claude to: for each enabled site, search each title; exclude skip-list URLs before
opening listings; rank remaining by fit to the profile; take top `picks_per_site`;
open each pick and scrape the full JD; emit the exact `POST /api/scan/results`
JSON shape (validated by the n8n Function node before POST).

## Frontend (`src/jobhunter/web/frontend/`)

- New page `JobScanPage.tsx` + sidebar entry "Job Scan" (route `/job-scan`),
  separate from the existing `/scans` flow-telemetry page.
- API client `src/api/scan.ts` (settings, candidates list, dismiss, generate).
- Layout: scans newest-first; each scan header shows date + per-site status
  chips; candidates grouped by site as cards (title, company, location, fit
  reason/score, job link in new tab, expandable JD preview); `Generate CV` +
  `Dismiss` on `new` cards; `generated` cards deep-link to `/packages/<slug>`.
- A "Job Scan" settings section added to `SettingsPage.tsx`.

## "Generate CV" flow (F6)

Button → `POST /api/paste` with `{ jd_text, url, source: <site> }` → existing
`run_tailoring()` → on `200`, `PATCH` candidate to `status=generated` + store
`slug`. Drift checks, held-vs-passed, and applications-tracker linkage all work
unchanged because the package is produced by the identical pipeline. On failure
(e.g. spend cap), surface the error and leave `status=new` (retryable).

## Error handling & edge cases

- **Site blocked / zero results:** recorded in `site_summary`; run still
  `completed`/`partial`; surfaced on dashboard; never aborts other sites.
- **Duplicate URL:** skipped on insert via `UNIQUE`; counted in `skipped`.
- **Malformed agent JSON:** n8n Function node rejects before POST; the run logs an
  error in n8n; nothing partial reaches the app.
- **Notify failure:** non-fatal, logged; candidates already persisted.
- **`enabled=false`:** the agent run is a no-op (workflow short-circuits after
  reading settings); nothing recorded, nothing notified.
- **Generate failure:** candidate stays `new`; no orphaned package state.

## Testing strategy

App side is the tested boundary (browser/anti-bot lives in n8n, intentionally
untested in-app):
- `scan_settings`: CRUD + each validation failure + enabled=false no-op.
- `/api/scan/results`: happy path, duplicate-URL skip, malformed payload,
  idempotent re-POST, counts correctness, partial site_summary.
- `known-urls` + `canonical-profile` shape.
- Candidate list filter + dismiss + invalid-transition rejection.
- Notification builder: counts rendering, zero-new suppression, no-job-board
  hostname assertion, dashboard-link present, failure non-fatal.
- Generate-from-candidate: success sets `generated`+`slug`; failure leaves `new`.
- Frontend: `npm run build` clean; visual screenshot of populated dashboard.

## Rollout order

F1 (settings) → F3 (ingest + dedup) → F4 (notify) → F5 (dashboard) → F6
(generate) can all proceed against fixtures without the real scanner. F2 (n8n
custom image + workflow) integrates last against the now-stable contracts, then
the full end-to-end loop is demonstrated once.

## Open questions / risks

- **Anti-bot on Railway datacenter IPs** (Indeed/LinkedIn especially) — may force
  a residential proxy; deferred, flagged.
- **Custom image size / Railway memory** for headless Chromium — validate during
  F2.
- **Ranking quality** of the condensed canonical profile — may need prompt
  iteration; `fit_score` is informational, not gating.
- **LinkedIn ToS** — scraping is against LinkedIn's terms; user accepts the risk
  for personal single-user discovery use.

## DECISIONS.md addendum (to add on implementation)

A new dated entry recording: (1) the scanner as an external ingestion agent
(keeps §4 intact), (2) Supabase reuse for scan persistence (extends §7), (3)
dashboard-only notifications preserving the no-job-board-hostname guardrail.
