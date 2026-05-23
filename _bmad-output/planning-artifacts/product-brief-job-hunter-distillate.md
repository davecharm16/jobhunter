---
title: "Product Brief Distillate: job_hunter"
type: llm-distillate
source: "product-brief-job-hunter.md"
created: "2026-05-17"
purpose: "Token-efficient context for downstream PRD creation"
---

# Job Hunter — Distillate

## One-line positioning
"The AI résumé tool that won't get you rejected." Anti-slop, drift-checked, human-gated job-application assistant for serious applicants on Upwork, OnlineJobs.ph, and LinkedIn.

## Author / build context
- Solo developer, nights/weekends build
- Motivation: paid tools (Jobscan ~$50/mo, Teal+ $29/mo, Huntr ~$20/mo) are inferior to what the author can build for himself
- Personal-first, shareable-with-peers — explicitly NOT a VC-backed SaaS pitch
- Primary user = author; secondary = peers (freelancers, PH remote workers)

## Hard requirements / non-negotiables
- Human always presses submit — no auto-apply ever
- Drift check runs before any output reaches the user
- Canonical CV lives in markdown/YAML, in version control — never PDF/docx ingest
- Per-application LLM cost under $0.25; hard monthly spend cap on API key
- Secrets in `.env`, `.gitignore`'d
- Local-first runtime; no **hosted/multi-tenant** infra in v1. The v1 surface IS a local web app bound to `127.0.0.1` (web-only architecture, DECISIONS.md §6 — supersedes the earlier §5 framing that treated it as a layer over a CLI). Nothing leaves the machine except the LLM call.

## v0.1 walking skeleton (week 1)
Minimal end-to-end FastAPI app: `jobhunter` boots a server on `127.0.0.1:8765`, a browser textarea POSTs to `POST /api/paste`, the backend tailors a markdown CV + cover letter and surfaces file paths in the browser. No drift check, no notifications, no production-quality UI yet. Proves concept before anything else is built. *(Originally framed as "a single CLI script"; reframed on 2026-05-23 when the project pivoted to web-only architecture — see DECISIONS.md §6. Epic 1's core modules from Stories 1.1–1.5 survive unchanged; Story 1.6 carries the pivot.)*

## v1 scope (in order)
1. **Walking skeleton + FastAPI pivot** — `jobhunter` launcher binds `127.0.0.1:8765`, `POST /api/paste` is the one ingest endpoint, minimal React + Vite + Tailwind frontend scaffold with design tokens from `design_guidelines/stitch-export/design.md`. No CLI subcommand surface (`DECISIONS.md` §6).
2. Paste-pipeline hardening + artifact system (structured JD parser, Upwork proposal as a first-class artifact, prompt-template versioning, metadata sidecars, `POST /api/paste` shared-token auth for n8n callers) **plus** the Settings & Canonical CV editor surface (Stitch screen 02) and the JD Pipeline & Tailoring viewer (Stitch screen 04)
3. **Fabrication drift check** — claim-to-source-CV traceability (structural, not LLM-judge vibes) + drift diagnostics surface fabrication slice (Stitch screen 05)
4. **Content-loss drift check** — high-impact original entries survive rewrite + drift diagnostics content-loss slice
5. **Keyword-stuffing drift check** — density/placement natural, ATS-passable, not ATS-tell + drift diagnostics keyword-stuffing slice (completes Stitch screen 05)
6. Single notification channel: Google Chat webhook + Dashboard surface (Stitch screen 01) showing held queue + KPI stats + Approve action (`POST /api/override/<slug>`)
7. Scheduled-search via n8n (or Make.com / equivalent workflow tool) — ingests Upwork, OnlineJobs.ph, LinkedIn job-alert emails into `POST /api/paste`; LinkedIn ingest = parse official Job Alert emails, NOT crawl the site + Job Alerts & Automated Scans surface (Stitch screen 03)

*Note on architecture: v1 is a **single-user local web app bound to `127.0.0.1`**. Web surfaces are scattered into the feature epics — there is no separate "Epic 8 — Local Web UI" (dissolved 2026-05-23, DECISIONS.md §6). Each feature epic ships an end-to-end vertical slice (backend route + frontend surface).*

## v1 explicit non-scope (rejected for v1)
- **Voice drift check** — deferred to v2; no clean pass/fail, known tuning rabbit hole, requires hand-labeled eval set first
- **PDF/docx canonical-CV ingest** — markdown-only is treated as a feature; parser hell rejected
- **Email digest / push notifications** — single GChat webhook is enough for solo user; multi-channel deferred
- **Browser auto-fill / one-click apply** — ToS landmine and big build; deferred indefinitely
- **Multi-CV / multi-profile support** — single canonical CV in v1
- **Hosted/multi-tenant SaaS web UI with auth/state** — v1 ships a local-only single-user web app bound to `127.0.0.1` with no auth; hosted/multi-tenant remains v2+
- **CLI subcommand surface** — v1 has no `jobhunter paste`/`status`/`override`/`stats` subcommands; the web app is the only user surface (revised 2026-05-23, DECISIONS.md §6)
- **Peer packaging / setup docs** — v2 conversation, only after 30+ real applications by author

## Pipeline architecture (high-level)
- **Inputs:** paste-mode (always) + scheduled n8n flow (optional)
- **Parse:** JD → structured fields (must-haves, nice-to-haves, tone, seniority, red flags, board-specific signals like Upwork budget)
- **Tailor:** generate CV/cover letter or Upwork proposal from canonical-CV YAML against parsed JD
- **Drift check:** v1 = fabrication + content-loss + keyword-stuffing; v2 = voice
- **Notify:** Google Chat webhook with link/path to staged package
- **Review:** user opens `.md`, edits, copies to board, submits manually

## Output artifact types (treated separately, NOT one format)
- Traditional CV + cover letter (LinkedIn, OJ.ph traditional roles)
- Upwork proposal — short, conversational, answers client screening questions, length-bounded
- (OJ.ph applications may use cover-letter shape; verify in v1)

## Success metrics (pre-committed)
- **Primary:** interview conversion rate = baseline × 2 over rolling 30-application window
- **Baseline measurement:** 2–4 weeks pre-launch manual logging; n ≥ 30 baseline applications
- **Kill criterion:** if 8-week lift < 25% over baseline → revisit or kill
- **Supporting:** time-per-app under 10 min review; fabrication drift catches ≥1 issue per ~10 packages; per-app LLM cost < $0.25; author still using it after build phase
- **Anti-metric:** applications-submitted-per-week (volume is explicitly NOT the goal)

## Vision extensions (post-v1, in priority order if pursued)
- **Outcome learning loop:** track which packages → screens/interviews/offers; feed back into tailoring. Personal hit-rate optimizer that compounds with use; structurally impossible for generic SaaS to replicate.
- **Interview-prep handoff:** when a screen is booked, regenerate prep doc (likely questions, matching stories from canonical CV, JD-specific talking points). Uses material already in the pipeline.
- **Standalone drift-check CLI:** ship fabrication checker as separate tool peers can run against ANY AI-tailored CV (Teal, ChatGPT outputs, etc.). Softer on-ramp for sharing, credibility builder.

## Competitive intelligence (preserve for PRD)
- **Analyzers (Jobscan, Teal+, Huntr, ResumeWorded):** ATS scoring or tailoring but push all work to user; no continuous discovery; no drift/fabrication guardrails
- **Auto-appliers (LazyApply, Sonara, JobRight.ai, LoopCV, AIApply):** volume sprayers; LazyApply Trustpilot 2.4★; Sonara user reported 1 screen per ~700 auto-applies; LinkedIn blacklists frequent; JobRight.ai (Mar 2026) cited for keyword stuffing, phantom postings, bad rewrites — exact failure modes this product targets
- **Hybrid (Simplify Copilot + Huntr):** browser autofill + Kanban tracker; user-initiated per role; no drift guardrails
- **Pricing context:** Jobscan ~$50/mo, Teal+ $29/mo, Huntr ~$20/mo, LazyApply tiered. Job Hunter target: cents per application on user's own LLM key.

## Market context (preserve for PRD)
- Online recruitment SaaS market: ~$4.73B (2025) → $7.58B by 2034 (7% CAGR)
- Broader online recruitment platform market: ~$57.7B → $132B by 2032 (12.56% CAGR)
- 97.8% of F500 use a detectable ATS (Jobscan 2025); Workday parses ~39% of F500
- ATS rejects ~75% of resumes pre-human review; 88% of employers lose qualified candidates to bad ATS formatting
- 78% of applications now contain AI-generated content; differentiation is shifting from "has AI" to "AI that doesn't get you rejected"

## Recruiter-side signals (the WHY behind anti-slop positioning)
- 33.5% of hiring managers claim to spot AI in <20 seconds
- 19.6% would auto-reject AI-detected applications
- 62% of employers reject AI-generated résumés that lack personalization (Resume-Now survey)
- Recruiter AI fatigue is rising in 2025–26; over-tailored / keyword-stuffed outputs are the #1 tell

## Why-now enablers
- LLM inference costs ~10× drop 2023–2025 → per-JD tailoring economical at consumer prices
- ATS saturation (97.8% F500) makes ATS-alignment universal not niche
- Workflow automation (n8n, Make, Zapier) commoditized → don't hand-roll scrapers
- Multi-channel notification rails (GChat webhooks, push, email) commodity infra
- Public backlash against spray-and-pray bots = clear opening for quality-first alternative

## Risks & mitigations (operational)
| Risk | Mitigation |
|---|---|
| Upwork/LinkedIn ToS / account suspension | Paste-mode always works; n8n flows isolated from author's logged-in accounts; LinkedIn = parse Job Alert emails not crawl; never auto-submit |
| PII / NDA / client-confidential JDs through third-party LLM APIs | Prefer no-training data-handling terms; redact client identifiers; local storage default |
| LLM-as-judge unreliability for drift check | Fabrication check is structural (claim-to-source traceability), not vibes; subjective checks (voice) deferred until eval set exists |
| Cost runaway from buggy evaluator loops | Hard monthly spend cap; per-request token logging from day one; $0.25/app target tracked as KPI |
| Scope creep on solo build | v0.1 walking skeleton in week 1 (now FastAPI-shaped, not pure CLI); "shareable" is v2; voice/PDF explicitly cut; web app bounded to localhost + no auth + no outbound submission; pivoted to web-only on 2026-05-23 to avoid building CLI + UI twice (DECISIONS.md §6) |
| Confounded success metric (selection effects) | Track application-fit-score + recruiter response rate alongside screen rate to disentangle |
| Regulatory (GDPR/CCPA, NYC LL144, EU AI Act) | Candidate-side tool largely sidesteps employer-side rules; PII handling minimized; future hosted variant would need compliance review |

## Open questions / decisions deferred
- Specific LLM provider for v1 (Anthropic vs OpenAI vs local) — picked at build time based on cost/quality of fabrication-check tracing
- Concrete schema for canonical CV YAML (use JSON Resume schema, or invent minimal one) — decide before drift-check is built
- How to structure the JD red-flag heuristics (Upwork budget thresholds, vague-scope detection) — defer to first real-use feedback
- Whether n8n self-hosted or n8n cloud for scheduled flows — author's call, both work
- Eval set construction for the v2 voice check — not needed until v2

## Notes for downstream PRD
- The drift check is the moat AND the headline — every PRD section should reinforce it
- Upwork proposals must be a first-class artifact type with their own prompt template, NOT a cover-letter variant — Upwork is a primary channel
- Build sequence in v1 is non-negotiable order; resist parallelizing
- "Shareable with peers" is aspiration not requirement for v1 — do not let PRD generate setup docs / install scripts / multi-tenant features for v1
- Markdown canonical CV is a feature decision, not a technical limitation — PRD should reflect that framing
