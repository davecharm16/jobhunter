# Gap Triage Decisions (BMad party: John/Sally/Winston/Mary)

Verdicts on `docs/design-gap-checklist.md`. The Stitch mockups are a generic SaaS
template in Job Hunter tokens, so a large share of "gaps" are template noise or
conflict with deliberate decisions. Build the **trust chain** first; UI that
needs missing data waits on the data-model work.

## REJECT — template noise / conflicts with DECISIONS.md (do NOT build)
- `02-2` / `02-3` — API Configuration panel + OpenAI API-key field (wrong provider §4; secrets are env-only, never UI).
- `01-7` / `02-4` / `02-8` / `02-9` — Notifications bell + panel + Google Chat webhook + alert triggers (no notification backend; Epic 7 at most).
- `01-9` / `04-9` (+`02-13`) — "62% Profile Completion / Tom!" widget (SaaS onboarding; single user edits a file).
- `01-5` (+`02-12`/`04-4` search) — Top-bar search / command palette (no search backend, trivial corpus).
- `01-12` — Interview-rate trend delta (no time-series store).
- `03-14` — "Scans processed today: 142" (fake metric).
- `01-19` — Mobile header (localhost desktop tool).
- `04-8` — Code-editor artifact view (users review, don't hand-edit markdown).
- `01-6` — "Create New CV" top-bar button (wrong mental model — one canonical CV; the dashboard CTA covers it).

## DEFER — real but Epic 7 / needs new persistence
- `03-1`..`03-9` — Job-Alerts Search Criteria panel, scanner enable/disable, scan frequency, Apply (needs writable config + n8n write-back = Epic 7).
- `03-5`,`03-12`..`03-15` — Integration Status / Force Sync (Epic 7 plumbing).
- `02-5` — Canonical-CV revisions history (git already covers it; v2).
- `02-6` — *Editable* monthly spend-cap field (config-in-UI fights env-only/no-DB). Note: the read-only usage display IS implemented below.

## Data-model prerequisites (build FIRST — unblocks the UI)
- **D1** — Write `job_title` + `company_name` into `metadata.json` at tailoring time (from the parsed JD). Unblocks `01-1..4`, `01-15/16`, `04-5`.
- **D2** — Store canonical `source_text` per claim in `package.drift.json` at check time. Unblocks the semantic diff `05-4/05-5`.
- **D3** — New `GET /api/drift/history` aggregate endpoint (one read-pass over `./out/*/package.drift.json`, no DB). Unblocks `05-1/05-3`.

## IMPLEMENT — in build order

### Wave 1 — Core trust chain (highest value)
- `04-2` — Inline drift/hallucination highlight with original-vs-claimed tooltip.
- `05-4` / `05-5` / `05-11` / `05-12` — Semantic Trace Diff split-pane, color-coded diff, legend, file labels (needs D2).
- `05-2` / `05-10` — Per-package drift summary metric cards + detail stat strip (fabrication count, content-loss %, keyword density — NOT the fake "142").

### Wave 2 — Dashboard + JD review
- `01-1`..`01-4`, `01-15`, `01-16`, `01-17`, `01-18` — Pipeline status cards (job title, drift-health row, state-specific actions Fix/View/Continue, red ring on failed, in-progress state) (needs D1).
- `04-1` — Inline JD-tailoring highlights (what the LLM changed).
- `04-5` — JD header shows title + company instead of slug (needs D1).
- `04-6` — Red Flags as a prominent card.
- `04-7` — Budget Range + Expected Tone stat cards for all boards.

### Wave 3 — Drift history + navigation
- `05-1` / `05-3` — Master/detail drift history (Recent Checks list) (needs D3).
- `05-8` — Check ID + run timestamp in detail header.
- `04-12` — "Drift Check Active" becomes a navigable button → drift page.
- `01-10` — "Start New Application" card prominence (move paste panel to top).

### Wave 4 — Settings + polish
- `02-1` — Raw Markdown/YAML canonical-CV editor (`GET/PUT /api/canonical-cv/raw` + CodeMirror).
- `02-7` — **Read-only** spend/usage display (from `spend_tracker`; NOT an editable cap).
- `01-8` sidebar nav icons · `01-11` metric-card icons · `01-22` three discrete metric cards · `01-20` greeting using canonical `basics.name` (Dave) · `04-11` artifact tab icons · `03-10` scanner Running/Stopped status · `03-18` provider icons on scanner cards · `01-13` drift as count "fabrications prevented".

## Sequencing summary
D1/D2/D3 (backend) → Wave 1 (drift trust) → Wave 2 (dashboard/JD) → Wave 3 (history/nav) → Wave 4 (settings/polish). Re-run the gap audit after each wave (Phase 4).
