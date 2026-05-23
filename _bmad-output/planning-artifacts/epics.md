---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/product-brief-job-hunter.md
  - _bmad-output/planning-artifacts/product-brief-job-hunter-distillate.md
---

# Job Hunter - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Job Hunter, decomposing the requirements from the PRD (and product brief inputs) into implementable stories.

Job Hunter is a local-first, human-gated CLI tool plus workflow-automation surface (n8n / Make / equivalent). The PRD classifies the project as `cli_tool_plus_workflow` with a `phased` release mode. v1 build order is non-negotiable per the brief: walking skeleton → paste pipeline hardening → fabrication drift → content-loss drift → keyword-stuffing drift → GChat webhook → n8n scheduled flows. Every epic in this breakdown ladders up to one of three moat dimensions: **drift integrity** (epics 3, 4, 5), **channel coverage** (epics 2, 6, 7), or **solo-buildability** (epic 1 — the week-1 walking-skeleton gate).

There is no Architecture document and no UX Design Specification for this project. The PRD is the single source of truth for technical decisions; UX surface is a CLI + the user's markdown editor + a Google Chat space, with no UI design artifacts to extract.

## Requirements Inventory

### Functional Requirements

**Canonical CV Management**

- FR1: Author can maintain their canonical CV as a single markdown/YAML file in a version-controlled directory.
- FR2: Author can attach tags to individual canonical-CV entries (e.g. `node, typescript, fintech`) to indicate which contexts each entry is relevant to.
- FR3: Author can mark canonical-CV entries as "high-impact" so the content-loss drift check protects them.
- FR4: System reads the canonical CV fresh on every pipeline run; no re-import or re-parse step exists.
- FR5: System rejects any attempt to ingest PDF or docx as a canonical-CV source.

**JD Ingest**

- FR6: Author can paste a JD into the pipeline via the browser textarea (which POSTs to `POST /api/paste`) and trigger the full tailoring + drift-check + notification pipeline.
- FR7: System exposes a single internal endpoint (`POST /api/paste`) that both the web UI and scheduled flows POST JDs to.
- FR8: Scheduled flows (n8n / Make / equivalent) can post JDs from Upwork search results into the pipeline endpoint.
- FR9: Scheduled flows can post JDs from OnlineJobs.ph listings into the pipeline endpoint.
- FR10: Scheduled flows can post JDs from parsed LinkedIn Job Alert emails into the pipeline endpoint.
- FR11: System never logs into the user's Upwork or LinkedIn account on the user's behalf.

**JD Parsing**

- FR12: System parses each JD into structured fields including must-have requirements, nice-to-have requirements, tone, seniority, and red flags.
- FR13: System classifies the source board (Upwork, OJ.ph, LinkedIn, other) and applies board-specific signal extraction.
- FR14: System extracts Upwork-specific signals including budget band, hourly vs fixed-price, and screening questions, when present.
- FR15: System extracts OJ.ph-specific signals including stated rate range and role type.
- FR16: System surfaces JD red flags (e.g. budget below user-configured floor, vague-scope detection) on the staged package summary.

**Tailoring**

- FR17: System generates a tailored markdown CV against the canonical CV for a given parsed JD.
- FR18: System generates a tailored markdown cover letter against the canonical CV for a given parsed JD.
- FR19: System generates a tailored Upwork proposal as a distinct artifact type with its own prompt template, separate from the cover letter.
- FR20: System selects the artifact set produced (CV+cover-letter vs Upwork proposal vs both) based on the JD's classified source board.
- FR21: Each prompt template is a versioned file in the repo, and the template version used is recorded in per-application metadata.

**Drift Check — Fabrication**

- FR22: System verifies that every skill or claim asserted in the tailored CV traces to a corresponding entry in the canonical CV via structural matching (string match plus semantic-equivalence threshold).
- FR23: System fails the fabrication check if any tailored-output claim cannot be traced to a canonical-CV entry.
- FR24: System records each failed claim, its location in the tailored output, and the reason it failed traceability in per-application metadata.

**Drift Check — Content Loss**

- FR25: System verifies that canonical-CV entries marked as "high-impact" appear in the tailored output when the JD's parsed requirements call for them.
- FR26: System fails the content-loss check if a high-impact, relevant entry was dropped.
- FR27: System records each dropped entry and the JD requirements it would have addressed in per-application metadata.

**Drift Check — Keyword Stuffing**

- FR28: System measures density and placement of JD-derived keywords in the tailored output against configurable thresholds.
- FR29: System fails the keyword-stuffing check when density exceeds the configured per-section limits or when placement looks like a dump-paragraph.
- FR30: System records the offending keywords, density measurements, and locations in per-application metadata.

**Notification + Held-Package Queue**

- FR31: System posts a notification to a configured Google Chat webhook when a package passes all drift checks.
- FR32: The GChat notification includes a one-line fit summary, the source board, and the path to the staged markdown package.
- FR33: System holds packages that fail any drift check without sending a notification.
- FR34: System writes the staged markdown artifacts to disk even when a package is held, so the user can read them.
- FR35: Author can list held packages and their failure reasons via the Dashboard surface, backed by `GET /api/queue`.
- FR36: Author can override a held package via the Approve action on the Dashboard, backed by `POST /api/override/<slug>`; the override is logged in per-application metadata.

**Output, Metadata, and Cost Observability**

- FR37: System writes each generated package to `./out/<slug>/` as markdown artifacts (one file per artifact type).
- FR38: System writes a per-application metadata file (JSON or YAML) capturing JD source, parsed fields, drift verdicts, override flag if any, prompt-template versions, and total cost-to-produce.
- FR39: System logs per-request LLM token usage (model, input tokens, output tokens, dollar cost) from the first call onward.
- FR40: Author can view aggregated cost-per-application, drift-catch rate, and override rate on the Dashboard surface, backed by `GET /api/stats`.

**Configuration and Safety**

- FR41: All secrets (LLM API keys, GChat webhook URLs, scheduled-flow tokens) live in `.env` and `.env` is `.gitignore`'d.
- FR42: All tunables (drift-check thresholds, prompt template paths, cost cap, output directory, JD-red-flag floors) live in a `config.yaml` separate from secrets.
- FR43: System enforces a configured hard monthly LLM spend cap and refuses to run when the cap is exceeded.
- FR44: System never auto-submits an application to any platform.

### NonFunctional Requirements

**Performance**

- NFR1: End-to-end pipeline latency in paste mode is under 90 seconds per JD from paste to staged package (JD parse + tailoring + all three drift checks).
- NFR2: Scheduled mode has no hard per-JD latency SLO; throughput is constrained only by the monthly cost cap.
- NFR3: Pipeline must not block on a single slow LLM call beyond a configurable per-call timeout (default 60 seconds). Timeouts fail the package cleanly with an explanatory verdict rather than hanging.

**Cost (first-class NFR)**

- NFR4: Per-application LLM cost target is under $0.25 end-to-end, including JD parse, tailoring, all three drift checks, and any single retry.
- NFR5: Hard monthly spend cap on the LLM API key, enforced both at the provider portal (defense-in-depth) and in `config.yaml`. System refuses to run pipeline calls when the cap is breached.
- NFR6: Per-request token logging from the first call onward; no call is unaccounted for.
- NFR7: Aggregated cost-per-application is reported on the Dashboard surface (`GET /api/stats`) so the KPI is always visible.

**Security and Privacy**

- NFR8: All secrets in `.env`; `.env` is `.gitignore`'d; sample `.env.example` is checked in with placeholder values only.
- NFR9: Canonical CV, parsed JDs, tailored artifacts, and per-application metadata are stored on the user's local filesystem only. No cloud sync in v1.
- NFR10: LLM provider selected for v1 must offer no-training data-handling terms.
- NFR11: Client-confidential JD content is redacted before being sent upstream where feasible.
- NFR12: System never auto-submits, never logs into user platform accounts, and never crawls LinkedIn (LinkedIn ingest is email parsing of official Job Alerts only).

**Reliability**

- NFR13: Paste mode is the always-available path. If scheduled flows, GChat webhook, or any accessory subsystem is broken, paste mode must still produce a staged package.
- NFR14: Held-package queue is durable on disk. A crash mid-pipeline does not lose a JD that was accepted by the ingest endpoint.
- NFR15: Cost-cap enforcement is non-bypassable by application logic; the cap check happens before any LLM call is made.

**Integration**

- NFR16: One LLM provider at a time in v1 (provider choice deferred to build time). Switching providers must be a config change — model name, base URL, and API key all configurable.
- NFR17: One outbound Google Chat incoming webhook URL, configurable.
- NFR18: A single internal inbound JD endpoint (`POST /api/paste`) accepts payloads from both the web UI's browser textarea and scheduled flows; non-loopback callers (n8n) must present a shared token from `.env`, browser-origin requests from `127.0.0.1` are accepted without the token header.
- NFR19: n8n / workflow tool is self-hosted or cloud at author's choice. Flows live in n8n's own state, not in the core repo. The only contract between n8n and the core is the inbound JD endpoint.

**Maintainability**

- NFR20: Drift-check thresholds, prompt templates, and red-flag floors are configuration, not code. Behavior is tunable without redeploying.
- NFR21: Prompt templates are versioned files with version strings recorded in per-application metadata so output quality correlates with template revisions.
- NFR22: Per-application metadata is structured (JSON or YAML) so `GET /api/stats` can aggregate without re-parsing markdown.

### Additional Requirements

No Architecture document exists for this project. Technical-architecture-shape requirements that influence epic structure are sourced from the PRD's Project-Type Specific Requirements section and folded into the relevant epic:

- Language/runtime decision (Python or TypeScript) is deferred to the first story of Epic 1 — chosen at build time based on solo author's velocity.
- LLM provider decision (Anthropic, OpenAI, or local) is deferred to the first story of Epic 3 (fabrication drift) per PO direction — the choice depends on which provider's traces best support structural claim-matching.
- Canonical CV schema is JSON Resume schema as the working assumption, with the explicit option to fall back to a minimal custom YAML if JSON Resume does not fit. Decision finalized in Epic 1.
- n8n hosting (self-hosted vs cloud) is deferred to the author at build time within Epic 7. Epic 7 is hosting-agnostic.
- Filesystem-based persistence (no database in v1). Canonical CV in markdown in version control; per-application outputs as markdown files under `./out/<slug>/` with JSON/YAML metadata sidecars.
- Single internal `POST /api/paste`-style endpoint as the contract between the web UI and scheduled flows; shared-token authentication from `.env` for non-loopback callers.

### UX Design Requirements

The user-facing surface in v1 is a **local single-user web app bound to `127.0.0.1`** plus an external workflow-automation surface (n8n / Make / equivalent). On the user side:

- The `jobhunter` command boots a FastAPI server on `127.0.0.1:8765` (no subcommands) and best-effort opens the default browser.
- The browser is the canonical surface; surfaces are: Dashboard (`/`), Settings & Canonical CV (`/settings`), JD Pipeline & Tailoring (`/packages/<slug>`), Drift Check Diagnostics (`/packages/<slug>/drift`), Job Alerts & Automated Scans (`/scans`).
- The canonical CV file on disk remains markdown/YAML and is also editable through the Settings surface.
- A Google Chat space receives webhook pings on pass.

**Design source of truth.** Stitch project `14722049854544467629` ("Drift-Checked Job Hunter"), exported into `design_guidelines/stitch-export/`:

- `design.md` — design tokens (Inter typography, deep navy + vibrant blue palette, 8px base grid, soft 0.25rem corners) plus component guidance.
- `html/*.html` — five screen mockups, source of truth for layout + Tailwind classes (dashboard, settings & canonical CV, job alerts, JD pipeline, drift diagnostics).
- `screenshots/*.png` — pixel reference per screen.
- `INDEX.md` — screen-to-epic mapping + dev-story usage rules.

Re-export with the Stitch MCP and overwrite that directory if the Stitch source changes. Do not hand-edit files inside `stitch-export/`.

**Web surfaces are scattered across the feature epics** (per `DECISIONS.md` §6 — supersedes the prior "Epic 8 owns the UI" framing from §5). Each feature epic ships its own end-to-end vertical slice (backend route + frontend surface) as one shipping unit:

- Epic 1 / Story 1.6 — FastAPI port + frontend scaffold + design tokens wired (the architectural pivot story; replaces the argparse CLI surface).
- Epic 2 / Stories 2.13, 2.14 — Settings & Canonical CV editor (Stitch screen 02), JD Pipeline & Tailoring (Stitch screen 04).
- Epic 3 / Story 3.5 — Drift Check Diagnostics: fabrication section (Stitch screen 05, fabrication slice).
- Epic 4 / Story 4.4 — Drift Check Diagnostics: content-loss section (extends 3.5).
- Epic 5 / Story 5.4 — Drift Check Diagnostics: keyword-stuffing section (completes 3.5/4.4).
- Epic 6 / Stories 6.3, 6.4 — Dashboard surface (Stitch screen 01) + Override Approve action.
- Epic 7 / Story 7.5 — Job Alerts & Automated Scans surface (Stitch screen 03).

Every web story references its corresponding Stitch HTML file as the design source of truth and consumes design tokens from `design.md` (no ad-hoc hex / pixel values in component source).

### FR Coverage Map

**Epic 1 — Walking Skeleton (v0.1) + FastAPI pivot**

- FR1: Canonical CV as a single markdown/YAML file in version control (first read happens here).
- FR4: System reads canonical CV fresh on every run (no re-import ceremony).
- FR5: System rejects PDF/docx canonical-CV ingest (markdown-only enforcement).
- FR6: `POST /api/paste` accepts a JD via JSON body and triggers the pipeline (replaces CLI stdin/file ingest from Stories 1.2/1.4 — see Story 1.6 + `DECISIONS.md` §6).
- FR17: System generates a tailored markdown CV against the canonical CV.
- FR18: System generates a tailored markdown cover letter against the canonical CV.
- FR37: System writes each generated package to `./out/<slug>/` as markdown artifacts.
- FR41: Secrets live in `.env`; `.env` is `.gitignore`'d (foundational, in place before first LLM call).
- FR43: Hard monthly LLM spend cap enforced; pipeline refuses to run when exceeded (must exist before first LLM call — cost runaway risk).
- FR44: System never auto-submits an application (foundational stance; baked in from day one — the tool stops at writing files to disk).
- FR45: `jobhunter` command boots a FastAPI server bound to `127.0.0.1:8765` (no CLI subcommands; lands in Story 1.6).

**Epic 2 — Paste Pipeline Hardening & Artifact System**

- FR2: Author can tag canonical-CV entries.
- FR3: Author can mark canonical-CV entries as "high-impact" (schema support; drift check that uses it ships in Epic 4).
- FR7: Single internal endpoint (`POST /api/paste`) that both the browser textarea and scheduled flows POST to.
- FR11: System never logs into user platform accounts (cross-cutting; codified here because this is where ingest abstractions land).
- FR12: Structured JD parsing (must-haves, nice-to-haves, tone, seniority, red flags).
- FR13: Source-board classification + board-specific signal extraction.
- FR14: Upwork-specific signal extraction (budget band, hourly vs fixed, screening questions).
- FR15: OnlineJobs.ph-specific signal extraction (rate range, role type).
- FR16: JD red flags surfaced on the staged package summary.
- FR19: Upwork proposal as a distinct artifact type with its own prompt template.
- FR20: Artifact set selected based on classified source board.
- FR21: Prompt templates are versioned files; version recorded in per-application metadata.
- FR38: Per-application metadata file (JD source, parsed fields, drift verdicts placeholder, prompt-template versions, cost).
- FR39: Per-request LLM token usage logging.
- FR40: `GET /api/stats` aggregates cost-per-application, drift-catch rate, override rate; surfaced on the Dashboard stats card (Story 2.12).
- FR42: Tunables live in `config.yaml` separate from secrets.
- FR47: Settings & Canonical CV editor surface (Story 2.13 / Stitch screen 02) — full CV editor preserving tags + high-impact flag.
- FR48: JD Pipeline & Tailoring surface (Story 2.14 / Stitch screen 04) — per-package staged-artifact viewer.

**Epic 3 — Fabrication Drift Check**

- FR22: Every claim in tailored CV traces to a canonical-CV entry via structural matching.
- FR23: System fails the fabrication check on any untraceable claim.
- FR24: Per-application metadata captures each failed claim, location, and reason.
- FR49 (fabrication slice): Drift Check Diagnostics surface — fabrication section (Story 3.5 / Stitch screen 05).

**Epic 4 — Content-Loss Drift Check**

- FR25: System verifies high-impact canonical-CV entries appear in tailored output when relevant.
- FR26: System fails the content-loss check if a high-impact relevant entry was dropped.
- FR27: Per-application metadata records each dropped entry and the JD requirements it would have addressed.
- FR49 (content-loss slice): Drift Check Diagnostics surface — content-loss section (Story 4.4 / extends 3.5).

**Epic 5 — Keyword-Stuffing Drift Check**

- FR28: System measures density and placement of JD-derived keywords against configurable thresholds.
- FR29: System fails the check when density or placement breaches the thresholds.
- FR30: Per-application metadata records offending keywords, densities, and locations.
- FR49 (keyword-stuffing slice): Drift Check Diagnostics surface — keyword-stuffing section (Story 5.4 / completes the surface).

**Epic 6 — Notifications & Held-Package Queue**

- FR31: GChat webhook notification on pass.
- FR32: Notification includes one-line fit summary, source board, and staged-package path.
- FR33: Packages that fail any drift check are held with no notification.
- FR34: Staged markdown artifacts are written to disk even when held.
- FR35: `GET /api/queue` lists held packages and failure reasons; surfaced on the Dashboard (Story 6.3 / Stitch screen 01).
- FR36: `POST /api/override/<slug>` releases a held package via the Approve action; override is logged in per-application metadata (Story 6.4).
- FR46: Dashboard surface (Story 6.3 / Stitch screen 01) — composes held queue, stats card, recent verdicts.
- FR51: Approve action invokes the same override code path; never POSTs externally (Story 6.4 — FR44 stance structurally enforced).

**Epic 7 — Automated Job Ingestion (n8n Scheduled Flows)**

- FR8: n8n flows POST JDs from Upwork search results into the internal endpoint.
- FR9: n8n flows POST JDs from OnlineJobs.ph listings into the internal endpoint.
- FR10: n8n flows POST JDs from parsed LinkedIn Job Alert emails into the internal endpoint.
- FR50: Job Alerts & Automated Scans surface (Story 7.5 / Stitch screen 03) — per-flow status without exposing credentials.

**Coverage stats:** 51 / 51 FRs mapped. FR45 → Epic 1 (Story 1.6). FR46 → Epic 6 (Story 6.3). FR47, FR48 → Epic 2 (Stories 2.13, 2.14). FR49 → split across Epics 3/4/5 (one slice per drift dimension, Stories 3.5/4.4/5.4). FR50 → Epic 7 (Story 7.5). FR51 → Epic 6 (Story 6.4). Epic 8 dissolved on 2026-05-23 — see `DECISIONS.md` §6.

## Epic List

### Epic 1: Walking Skeleton (v0.1) + FastAPI pivot
End-to-end smoke path proving the concept on a real application within week 1: paste a JD, tailor a markdown CV + cover letter against the canonical CV, write to `./out/<slug>/`. Stories 1.1–1.5 shipped as a CLI. Story 1.6 (added 2026-05-23) ports the surface to FastAPI + a minimal React/Vite/Tailwind scaffold and removes the argparse subcommand layer entirely (`DECISIONS.md` §6). Locks in the canonical-CV markdown stance, the cost cap, the no-auto-submit stance, and now the web-only architectural baseline that every later epic builds on.
**FRs covered:** FR1, FR4, FR5, FR6, FR17, FR18, FR37, FR41, FR43, FR44, FR45.

### Epic 2: Paste Pipeline Hardening & Artifact System
Turns the v0.1 spike into a real v1 pipeline: structured JD parsing with board classification and red flags, the canonical-CV tagging schema, the Upwork proposal as a first-class artifact (separate prompt template), prompt-template versioning, per-application metadata + cost-per-request logging, and the single internal `POST /api/paste` endpoint that both the browser textarea and the scheduled flows call. Also lands the first two production-quality web surfaces: Settings & Canonical CV editor (Story 2.13 / Stitch screen 02) and JD Pipeline & Tailoring viewer (Story 2.14 / Stitch screen 04). This is the foundation every drift check and notification rests on.
**FRs covered:** FR2, FR3, FR7, FR11, FR12, FR13, FR14, FR15, FR16, FR19, FR20, FR21, FR38, FR39, FR40, FR42, FR47, FR48.

### Epic 3: Fabrication Drift Check
The headline moat. Structural claim-to-source-CV traceability: every skill or claim in the tailored CV must trace to a real entry in the canonical CV via string match plus semantic-equivalence threshold. Not LLM-as-judge. This is the only check that makes output unsendable, and it ships first among the drift checks per the non-negotiable build order. Also establishes the package-held-on-fail pattern (artifacts still written to disk) that epics 4–6 build on, and lands the first slice of the Drift Check Diagnostics surface (Story 3.5 / Stitch screen 05, fabrication section).
**FRs covered:** FR22, FR23, FR24, FR49 (fabrication slice).

### Epic 4: Content-Loss Drift Check
Catches "the AI cut your best line." Verifies that canonical-CV entries marked as "high-impact" (schema support landed in Epic 2 via FR3) appear in the tailored output when the JD's parsed requirements call for them. Drops are recorded with the JD requirement they would have addressed, so the author can see exactly what was lost and why. Extends the Drift Check Diagnostics surface from Epic 3 with the content-loss section (Story 4.4).
**FRs covered:** FR25, FR26, FR27, FR49 (content-loss slice).

### Epic 5: Keyword-Stuffing Drift Check
ATS-passable but not ATS-tell. Measures density and placement of JD-derived keywords against configurable thresholds; flags dump-paragraphs and over-stuffing per section. Closes the third recruiter-side failure mode (after fabrication and content-loss) that the brief calls out as the moat dimension. Completes the Drift Check Diagnostics surface with the keyword-stuffing section (Story 5.4) — `05-drift-check-diagnostics.html` is fully realized after this epic.
**FRs covered:** FR28, FR29, FR30, FR49 (keyword-stuffing slice).

### Epic 6: Notifications & Held-Package Queue
The user's daily-driver surface. GChat webhook ping with one-line fit summary on pass; silent hold on fail with the package readable on disk; Dashboard surface (Stitch screen 01) listing the held queue + recent verdicts; Approve action (`POST /api/override/<slug>`) releasing held packages with structured metadata (not a free-text comment, per PRD PO Assumptions). Single notification channel — email/push are explicitly v2.
**FRs covered:** FR31, FR32, FR33, FR34, FR35, FR36, FR46, FR51.

### Epic 7: Automated Job Ingestion (n8n Scheduled Flows)
The second front door to the pipeline. Hosting-agnostic n8n (or Make / equivalent) flows poll Upwork search results, OnlineJobs.ph listings, and the user's LinkedIn Job Alert email inbox, then POST each JD to the same `POST /api/paste` endpoint the browser textarea uses. LinkedIn is email parsing only — no site crawling. Also ships the Job Alerts & Automated Scans surface (Story 7.5 / Stitch screen 03) so flow health is visible without SSHing into the n8n host. Sequenced last in v1 so a brittle ingest layer never blocks the rest of the system; the browser paste textarea remains the always-available path.
**FRs covered:** FR8, FR9, FR10, FR50.

*(Epic 8 was dissolved on 2026-05-23 — the web UI is now scattered across the feature epics above, one surface per epic. See `DECISIONS.md` §6 for the supersession rationale.)*

## Epic 1: Walking Skeleton (v0.1)

The week-1 gate. This epic exists to answer one question: does the concept actually save real time on a real application? The author pastes a real Upwork or LinkedIn JD into a CLI command, the script makes a single LLM call (or a tightly-bounded set of calls) to produce a tailored markdown CV and a markdown cover letter against the canonical-CV markdown file, writes both to `./out/<slug>/`, and exits. No drift check. No GChat. No held-package queue. No board-specific parsing. The output may be rough — that's fine, because the question is whether tailoring against a markdown source-of-truth is faster than the author's current 30–60-minutes-per-application baseline, not whether the output is recruiter-ready. This epic also locks in three foundational stances that every later epic inherits: secrets live in `.env` and are `.gitignore`'d (FR41), a hard monthly spend cap on the LLM key (FR43) is in place before the first call so a buggy loop cannot drain the wallet overnight, and the tool stops at writing files — never auto-submits anywhere (FR44). The language/runtime choice (Python vs TypeScript) and the canonical-CV schema choice (JSON Resume schema vs minimal custom YAML) are finalized inside this epic's first stories. If this epic ships and saves real time on a real application, v1 is built on top of it. If it doesn't, the concept itself is suspect and bigger features will not fix it.

### Story 1.1: Runtime, language, and canonical-CV schema bootstrap

As a solo developer (the author),
I want to commit a runtime/language choice and a canonical-CV schema decision to the repo on day one,
So that every later story builds on a stable foundation and I don't relitigate the decision mid-build.

**Acceptance Criteria:**

**Given** an empty repository,
**When** I complete this story,
**Then** the repo contains a top-level `README.md` (or `DECISIONS.md`) recording the chosen runtime/language (Python or TypeScript) with a one-paragraph rationale,
**And** the repo contains a runnable project skeleton for that runtime (e.g. `pyproject.toml` + `src/` for Python, or `package.json` + `tsconfig.json` + `src/` for TypeScript),
**And** running the project's standard install command (`pip install -e .` or `npm install`) exits 0 on a clean machine.

**Given** the runtime is bootstrapped,
**When** I commit the canonical-CV schema decision,
**Then** the repo contains a `canonical-cv.md` (or `canonical-cv.yaml`) sample file using the JSON Resume schema as the working assumption,
**And** the sample file is valid against the schema (validated by the standard JSON Resume validator, or by a custom validator if minimal-YAML fallback was chosen),
**And** the decision document explicitly states the schema choice (JSON Resume vs minimal custom YAML) and the criterion that would force a fallback.

**Given** the schema decision is committed,
**When** another story in this epic reads the canonical CV,
**Then** it reads from this single file path with no re-import or re-parse ceremony (FR4).

### Story 1.2: CLI scaffold, `.env` secrets handling, and cost-cap config

As a solo developer (the author),
I want a CLI entrypoint with `.env`-based secrets and a hard monthly LLM spend cap configured before the first LLM call is ever made,
So that a buggy loop on day one cannot drain my wallet overnight, and so secrets never get committed to git.

**Acceptance Criteria:**

**Given** the runtime from Story 1.1 is in place,
**When** I run the CLI binary with no arguments (e.g. `jobhunter`),
**Then** it prints a usage line listing at least one subcommand (`paste`),
**And** it exits with a non-zero exit code (usage error).

**Given** the CLI scaffold exists,
**When** I inspect the repository,
**Then** `.env` is listed in `.gitignore`,
**And** a `.env.example` file is checked in containing placeholder values only (no real keys),
**And** required env vars are documented in `.env.example` including `LLM_API_KEY` and `MONTHLY_SPEND_CAP_USD` (FR41).

**Given** the CLI starts up,
**When** the `LLM_API_KEY` environment variable is missing,
**Then** the CLI exits with a non-zero exit code and prints an error message naming the missing variable,
**And** no LLM call is attempted.

**Given** the CLI starts up,
**When** the `MONTHLY_SPEND_CAP_USD` environment variable is missing or non-numeric,
**Then** the CLI exits with a non-zero exit code and prints an error message,
**And** no LLM call is attempted (FR43).

**Given** the CLI is configured correctly,
**When** I inspect the source code or run `jobhunter --help`,
**Then** there is no code path that performs an HTTP submit to Upwork, LinkedIn, OnlineJobs.ph, or any job board, and the help text or README explicitly states the tool only writes files to disk (FR44).

### Story 1.3: Canonical CV reader with PDF/docx ingest rejection

As a solo developer (the author),
I want the pipeline to read the canonical CV fresh from a markdown/YAML file on every run and explicitly reject any PDF or docx ingest attempt,
So that I never re-import my CV, I get diffable/mergeable history for free, and the "markdown-only is a feature" stance is enforced in code rather than documentation.

**Acceptance Criteria:**

**Given** a valid canonical CV file exists at the configured path (markdown or YAML, per Story 1.1's schema decision),
**When** the CLI invokes the canonical-CV reader,
**Then** the reader returns a parsed in-memory representation of the CV,
**And** the file is read fresh from disk on every invocation with no caching layer (FR1, FR4).

**Given** the canonical CV file path points to a `.pdf` file,
**When** the canonical-CV reader is invoked,
**Then** the CLI exits with a non-zero exit code,
**And** prints an error message containing the text "PDF" and stating that the canonical CV must be markdown or YAML,
**And** no LLM call is attempted (FR5).

**Given** the canonical CV file path points to a `.docx` (or `.doc`) file,
**When** the canonical-CV reader is invoked,
**Then** the CLI exits with a non-zero exit code,
**And** prints an error message containing the text "docx" (or "Word") and stating that the canonical CV must be markdown or YAML,
**And** no LLM call is attempted (FR5).

**Given** the canonical CV file does not exist at the configured path,
**When** the canonical-CV reader is invoked,
**Then** the CLI exits with a non-zero exit code and prints an error message naming the missing file path.

### Story 1.4: `jobhunter paste` JD ingest from stdin or file argument

As a solo developer (the author),
I want a `jobhunter paste` subcommand that accepts a JD via stdin or a `--file` argument and hands the text off to the tailoring step,
So that I can drop a JD into the pipeline in two keystrokes during a Tuesday-evening session without any web UI.

**Acceptance Criteria:**

**Given** the CLI is correctly configured,
**When** I run `jobhunter paste` and pipe a non-empty JD into stdin (e.g. `cat jd.txt | jobhunter paste`),
**Then** the CLI accepts the stdin payload as the JD text,
**And** proceeds to the tailoring step (Story 1.5) (FR6).

**Given** the CLI is correctly configured,
**When** I run `jobhunter paste --file path/to/jd.txt` with a readable file at that path,
**Then** the CLI reads the JD text from that file,
**And** proceeds to the tailoring step (FR6).

**Given** I run `jobhunter paste` with no stdin input and no `--file` argument,
**When** the command starts,
**Then** the CLI exits with a non-zero exit code and prints an error message explaining that a JD must be provided via stdin or `--file`,
**And** no LLM call is attempted.

**Given** I run `jobhunter paste --file path/to/missing.txt`,
**When** the file does not exist,
**Then** the CLI exits with a non-zero exit code and prints an error message naming the missing file path,
**And** no LLM call is attempted.

### Story 1.5: Single tailoring LLM call writes tailored CV + cover letter to `./out/<slug>/`

As a solo developer (the author),
I want the pipeline to make a tightly-bounded LLM call that tailors a markdown CV and a markdown cover letter against my canonical CV for the pasted JD, and write both artifacts to `./out/<slug>/`,
So that I can open the staged files in my editor, make 1–3 manual edits, and submit — proving the concept saves real time on a real application within week 1.

**Acceptance Criteria:**

**Given** a valid canonical CV, a JD from `jobhunter paste`, an `LLM_API_KEY` in `.env`, and a `MONTHLY_SPEND_CAP_USD` value that has not yet been reached,
**When** the tailoring step runs,
**Then** the system makes a single LLM call (or a tightly-bounded set of calls) producing a tailored markdown CV and a tailored markdown cover letter,
**And** writes the CV to `./out/<slug>/cv.md` (FR17, FR37),
**And** writes the cover letter to `./out/<slug>/cover-letter.md` (FR18, FR37),
**And** the `<slug>` is a deterministic, filesystem-safe identifier derived from the JD (e.g. timestamp plus normalized title),
**And** the CLI exits with code 0 on success.

**Given** the running total of LLM spend for the current calendar month is already at or above `MONTHLY_SPEND_CAP_USD`,
**When** the tailoring step is about to make its first LLM call,
**Then** the CLI exits with a non-zero exit code before any LLM call is made,
**And** prints an error message stating that the monthly spend cap has been reached and naming the current spend and the cap (FR43).

**Given** the tailoring step completes successfully,
**When** I inspect `./out/<slug>/`,
**Then** the directory contains `cv.md` and `cover-letter.md` as plain markdown files openable in my editor,
**And** no HTTP request was made to Upwork, LinkedIn, OnlineJobs.ph, or any job board during the run (FR44).

**Given** the LLM call fails (network error, provider error, or per-call timeout),
**When** the tailoring step encounters the failure,
**Then** the CLI exits with a non-zero exit code and prints an error message identifying the failure,
**And** no partial or empty artifact files are written to `./out/<slug>/`.

### Story 1.6: FastAPI port + frontend scaffold + `jobhunter` launcher (web-only pivot)

As a solo developer (the author),
I want to replace the argparse CLI surface from Stories 1.2–1.5 with a FastAPI app and a minimal React + Vite + Tailwind frontend scaffold, all booted by a bare `jobhunter` command,
So that every subsequent epic builds on the web-only architecture (`DECISIONS.md` §6) instead of a CLI that we'd have to rewrite later, while the load-bearing Epic 1 core modules (canonical-CV reader, LLM client, spend tracker, package writer) survive untouched.

**Context.** Added 2026-05-23 in response to the web-only pivot (`DECISIONS.md` §6). Epic 1 had previously shipped as a CLI walking skeleton; this story carries the architectural pivot. The core modules from Stories 1.1–1.5 remain authoritative — only the entrypoint changes from `argparse` to FastAPI route handlers. The 189 tests for those core modules survive; only the CLI-entry tests need replacement with route-handler tests.

**Acceptance Criteria:**

**Given** the Epic 1 core modules from Stories 1.1–1.5 (canonical-CV reader, LLM client + spend tracker, package writer) exist in `src/jobhunter/`,
**When** I run `jobhunter` with no arguments,
**Then** a FastAPI server starts and binds to `127.0.0.1:8765` (port overridable via `JOBHUNTER_WEB_PORT` env),
**And** a startup check refuses to bind to `0.0.0.0` or any non-loopback host (raises and exits non-zero before the socket opens),
**And** the URL `http://127.0.0.1:8765/` is logged to stderr,
**And** the system best-effort opens the user's default browser via `webbrowser.open` (best-effort — failure to open the browser does not crash the server),
**And** the process exits cleanly on `SIGINT` (FR45).

**Given** the FastAPI app is running,
**When** an HTTP request hits `GET /healthz`,
**Then** the server returns `200 OK` with a JSON body `{"status": "ok", "version": "<package version>"}`,
**And** no route requires authentication (single-user, localhost only — `DECISIONS.md` §6).

**Given** the FastAPI app is running and `LLM_API_KEY` is configured,
**When** an HTTP request hits `POST /api/paste` with JSON body `{"jd_text": "<JD text>", "source": "browser"}`,
**Then** the handler invokes the **same** tailoring + package-write code path as Story 1.5 (no duplicated business logic — the route imports and calls the existing module),
**And** the response body contains the staged `slug`, the relative paths of `cv.md` and `cover-letter.md`, and the per-request cost (FR6, FR7, FR17, FR18, FR37),
**And** the cost-cap pre-check from Story 1.2/1.5 fires before any LLM call is made (FR43); when the cap is reached, the response is `402 Payment Required` with a JSON body naming current spend and cap, and no LLM call is attempted,
**And** no outbound HTTP request is made to Upwork, LinkedIn, OnlineJobs.ph, or any job board during the run (FR44).

**Given** the frontend scaffold,
**When** I inspect `src/jobhunter/web/frontend/`,
**Then** the directory contains a Vite + React + Tailwind project with `package.json`, `vite.config.ts`, and a `tailwind.config.ts` that consumes design tokens from `design_guidelines/stitch-export/design.md` (colors, typography scale, spacing scale, border-radius scale) via a shared TS module or a build-time codegen step,
**And** no hard-coded hex colors or pixel values appear in component source files (a grep-based lint check enforces this in CI),
**And** `npm run build` produces a static bundle under `src/jobhunter/web/frontend/dist/` that the FastAPI app serves at `/`,
**And** the bundle renders a minimal landing page with the Stitch sidebar shell + main content area applied, sized and themed according to `design.md` (260px sidebar, Inter typography, 8px base spacing, 0.25rem default radius).

**Given** the landing page is loaded,
**When** I look at the main content area,
**Then** a single JD-paste textarea is rendered with a "Tailor this JD" button,
**And** clicking the button POSTs the textarea contents to `POST /api/paste`,
**And** the response is displayed in a basic results panel showing the staged slug + file paths + per-request cost (no styling beyond the design tokens — production-quality screens land in Epic 2.14 and later).

**Given** the argparse CLI surface from Stories 1.2/1.4 is no longer the user entrypoint,
**When** I inspect the codebase,
**Then** `jobhunter` is the only console_script entry registered in `pyproject.toml`,
**And** there is no `jobhunter paste`, `jobhunter status`, `jobhunter override`, or `jobhunter stats` subcommand — these names are not parsed, not aliased, not present (`DECISIONS.md` §6),
**And** the existing test suite from Stories 1.1, 1.3, and 1.5 (canonical-CV reader, schema validation, tailoring logic, spend tracker) still passes unchanged,
**And** the test suite from Stories 1.2 and 1.4 (which exercised the argparse entry surface) has been replaced by route-handler tests against `POST /api/paste` and `GET /healthz` (use FastAPI's `TestClient`).

**Given** the launcher exists,
**When** I inspect `pyproject.toml`,
**Then** an optional dependency group `[project.optional-dependencies] web = ["fastapi", "uvicorn[standard]"]` exists with pinned versions,
**And** the frontend `package.json` pins React, Vite, and Tailwind versions,
**And** `jobhunter --help` shows only launcher flags (`--port`, `--no-browser`); no subcommand syntax is documented.

## Epic 2: Paste Pipeline Hardening & Artifact System

This epic turns the v0.1 spike into the real v1 pipeline that all drift checks plug into. It introduces the structured JD parser (must-haves, nice-to-haves, tone, seniority, red flags — FR12), source-board classification with board-specific signal extractors for Upwork (budget band, hourly vs fixed, screening questions — FR14) and OnlineJobs.ph (rate range, role type — FR15), and JD red-flag surfacing on the staged-package summary (FR16). It promotes the Upwork proposal to a first-class artifact type with its own prompt template — separate from the cover letter, not a variant — and wires per-board artifact-set selection (FR19, FR20). It introduces the canonical-CV tagging schema (FR2) and the "high-impact" flag (FR3) — the drift check that uses high-impact ships in Epic 4, but the schema lands here so the source-of-truth file is stable before the checks attach. It stands up the single internal `POST /api/paste` endpoint (FR7), authenticated by a shared token from `.env` for non-loopback callers, as the contract the n8n flows (Epic 7) will later call. It introduces prompt-template versioning (FR21), the per-application metadata sidecar file (FR38) capturing JD source, parsed fields, prompt-template versions, and cost-to-produce, per-request LLM token logging (FR39), the `GET /api/stats` aggregation endpoint surfaced on the Dashboard (FR40, Story 2.12), and the `config.yaml` separation of tunables from secrets (FR42). It also ships the first two production-quality web surfaces: the Settings & Canonical CV editor (Story 2.13 / FR47) and the JD Pipeline & Tailoring viewer (Story 2.14 / FR48). Cross-cutting "never logs into user platform accounts" stance (FR11) is codified here because this is the epic that defines what ingest is allowed to do.

### Story 2.1: Canonical CV tagging schema and high-impact flag

As a solo developer,
I want to tag individual canonical-CV entries with relevance labels and mark certain entries as high-impact,
So that downstream tailoring and drift checks can route the right entries to the right JDs and protect my best lines from being silently dropped.

**Acceptance Criteria:**
**Given** my canonical CV is a JSON Resume schema document on disk **When** I add a `tags` array (e.g. `["node", "typescript", "fintech"]`) to any `work`, `projects`, or `skills` entry **Then** the pipeline reads the tags on every run with no re-import step.
**And** the schema extension is documented in the repo (a sample `canonical-cv.json` shows tag and high-impact usage).

**Given** a canonical-CV entry has `"highImpact": true` set **When** the pipeline loads the canonical CV **Then** entries flagged high-impact are surfaced as a distinct collection available to downstream checks (the Epic 4 content-loss check consumes this; no behavior change to tailoring in this story).
**And** entries without the flag default to `highImpact: false`.

**Given** the canonical CV is malformed JSON or violates the JSON Resume base schema **When** the pipeline starts **Then** the pipeline exits with a non-zero code and a human-readable error pointing to the offending entry.
**And** the pipeline never silently coerces missing tags into empty strings — tags absent means tags absent.

### Story 2.2: config.yaml separation of tunables from secrets

As a solo developer,
I want all tunable behavior (drift-check thresholds, prompt-template paths, cost cap, output directory, JD red-flag floors) in a `config.yaml`, separate from secrets in `.env`,
So that I can tune the system without touching code and without risking committing secrets.

**Acceptance Criteria:**
**Given** I run any pipeline command **When** the system starts **Then** it loads `config.yaml` from the repo root for tunables and `.env` for secrets, and never reads secrets from `config.yaml`.
**And** `config.yaml` is checked in with sensible defaults; `.env` is `.gitignore`'d; `.env.example` is checked in with placeholder values only.

**Given** I change `cost.monthly_cap_usd` in `config.yaml` from 25 to 10 **When** I re-run the pipeline **Then** the new cap takes effect on the next run with no code change and no redeploy.
**And** the per-app cost ceiling (`cost.per_app_max_usd`, default `0.25`) lives here and is read on every run.

**Given** `config.yaml` is missing a required key **When** the pipeline starts **Then** it fails fast with a message naming the missing key, rather than silently defaulting.

### Story 2.3: Structured JD parser

As a solo developer,
I want the system to parse each pasted JD into structured fields — must-haves, nice-to-haves, tone, seniority, and red flags,
So that tailoring and drift checks operate on stable, inspectable data rather than re-prompting the LLM with raw text every step.

**Acceptance Criteria:**
**Given** I paste a JD via the browser textarea (which POSTs to `POST /api/paste`) **When** the parser runs **Then** it emits a structured JSON object containing at minimum `must_haves[]`, `nice_to_haves[]`, `tone`, `seniority`, and `red_flags[]`, and this object is persisted to the per-application metadata sidecar.
**And** the parse completes within the paste-mode 90-second end-to-end SLO budget (NFR1) — the parse step itself is bounded so it does not starve the tailoring step.

**Given** the parse JSON is produced **When** any downstream step (tailoring, drift checks, red-flag surfacing) needs JD data **Then** it reads from the parsed object, not from the raw JD text.

**Given** the LLM parse call exceeds the per-call timeout (default 60s per NFR3) **When** the timeout fires **Then** the package fails cleanly with an explanatory verdict (`parse_timeout`) and the failure is recorded in the metadata sidecar.

**Given** a JD is being parsed **When** the parse step runs **Then** the parse is performed only on JD text that the user (or a configured ingest flow) supplied — the parser never fetches the JD from a logged-in Upwork or LinkedIn session (FR11), and the test suite has at least one assertion that no platform-auth HTTP client is imported in the parse path.

### Story 2.4: Source-board classifier

As a solo developer,
I want the parser to classify the source board (Upwork, OJ.ph, LinkedIn, other) and tag the parsed JD,
So that board-specific signal extractors and the artifact-set selector know what kind of posting they are looking at.

**Acceptance Criteria:**
**Given** I paste a JD **When** the classifier runs **Then** the parsed object includes a `source_board` field with one of `upwork`, `onlinejobs_ph`, `linkedin`, or `other`.
**And** classification uses cheap heuristics first (URL hints, characteristic phrases, header patterns) before any LLM call, so common cases do not cost a token.

**Given** the paste-mode CLI accepts an explicit `--source` flag **When** the flag is set **Then** the explicit value overrides the heuristic classification and is recorded in metadata.

**Given** the classifier cannot confidently identify the board **When** classification resolves to `other` **Then** the pipeline still runs end-to-end (generic CV + cover letter artifact set) and logs the unknown classification to metadata for later tuning.

### Story 2.5: Upwork-specific signal extraction and red flags

As a solo developer who freelances on Upwork,
I want the parser to extract Upwork-specific signals — budget band, hourly vs fixed-price, and screening questions — and surface budget-floor red flags,
So that my Upwork-tailored output addresses screening questions explicitly and I never waste a proposal on a posting below my budget floor.

**Acceptance Criteria:**
**Given** an Upwork JD is being parsed **When** the Upwork signal extractor runs **Then** it populates `signals.upwork.budget_band`, `signals.upwork.pricing_type` (`hourly`|`fixed`|`unknown`), and `signals.upwork.screening_questions[]` when those fields are present in the JD.
**And** missing fields are returned as `null` rather than fabricated.

**Given** `config.yaml` has `red_flags.upwork.budget_floor_usd_hourly: 25` and `red_flags.upwork.budget_floor_usd_fixed: 500` **When** the parsed JD's budget falls below the configured floor **Then** a red flag entry (`budget_below_floor`) is added to `red_flags[]` and surfaced on the staged-package summary (FR16).

**Given** the JD contains vague-scope language (configurable signal phrases in `config.yaml`) **When** parsing completes **Then** a `vague_scope` red flag is added.

**Given** screening questions are extracted **When** an Upwork proposal is later generated **Then** the proposal template receives the screening questions as input and is expected to address them (the prompt template enforces this in Story 2.7).

### Story 2.6: OnlineJobs.ph-specific signal extraction

As a Filipino remote-worker peer (and the author, who applies to OJ.ph postings),
I want the parser to extract OJ.ph-specific signals — stated rate range and role type — and respect a configurable rate floor,
So that OJ.ph postings get tailored with the right tone and I never spend tokens on listings below my floor.

**Acceptance Criteria:**
**Given** an OJ.ph JD is being parsed **When** the OJ.ph signal extractor runs **Then** it populates `signals.onlinejobs_ph.rate_range` (e.g. `{"min": 800, "max": 1200, "currency": "USD", "period": "monthly"}`) and `signals.onlinejobs_ph.role_type` (e.g. `full_time`, `part_time`, `gig`) when present.
**And** missing fields are returned as `null`, not fabricated.

**Given** `config.yaml` has `red_flags.onlinejobs_ph.rate_floor_usd_monthly: 600` **When** the parsed rate falls below the floor **Then** a `rate_below_floor` red flag is added to `red_flags[]` and surfaced on the staged-package summary.

**Given** an OJ.ph JD is classified **When** the artifact-set selector runs (Story 2.8) **Then** the OJ.ph board produces a CV + cover-letter package (not an Upwork proposal).

### Story 2.7: Upwork proposal as a first-class artifact type

As a solo developer who freelances on Upwork,
I want the Upwork proposal generated from its own dedicated, length-bounded, conversational prompt template — not a cover-letter variant,
So that my Upwork output reads like a real Upwork proposal (short, screening-question-aware, JD-phrasing-aware) rather than a generic cover letter.

**Acceptance Criteria:**
**Given** the artifact-set selector chooses Upwork-proposal for the package **When** the proposal is generated **Then** it uses a distinct prompt template file (`prompts/upwork_proposal.v{N}.md`) — not the cover-letter template — and the chosen template path and version string are recorded in the per-application metadata.

**Given** the Upwork proposal template is invoked **When** the proposal is generated **Then** the output is length-bounded (default max 250 words, configurable in `config.yaml`) and the bound is enforced on the rendered artifact — if the LLM returns more, the artifact fails cleanly with an `over_length` verdict rather than being silently truncated.

**Given** the parsed JD includes `signals.upwork.screening_questions[]` **When** the proposal is generated **Then** the template receives the questions as structured input and the rendered proposal addresses each one (verified by a smoke check that each screening question's keywords appear at least once in the proposal).

**Given** the proposal is generated **When** the per-app cost is computed **Then** the proposal generation contributes to the per-application cost budget (NFR4, `< $0.25` end-to-end) and the run aborts before generation if the monthly cap (FR43) is already breached.

### Story 2.8: Per-board artifact-set selector

As a solo developer,
I want the system to automatically pick which artifacts to produce (CV+cover-letter, Upwork proposal, or both) based on the JD's classified source board,
So that I never have to remember to pass a flag and I never get an Upwork proposal generated for a LinkedIn role.

**Acceptance Criteria:**
**Given** the parsed JD has `source_board: upwork` **When** the selector runs **Then** the package produced is `{cv, upwork_proposal}` — no cover letter.
**And** for `source_board: linkedin` the package is `{cv, cover_letter}`.
**And** for `source_board: onlinejobs_ph` the package is `{cv, cover_letter}`.
**And** for `source_board: other` the package defaults to `{cv, cover_letter}`.

**Given** the CLI accepts a `--artifacts` override flag (e.g. `--artifacts cv,cover_letter,upwork_proposal`) **When** the flag is set **Then** the explicit list overrides the per-board default and the override is recorded in metadata.

**Given** the selected artifact set is committed **When** each artifact is generated **Then** it is written to `./out/<slug>/<artifact-type>.md` and the metadata sidecar lists which artifact types were produced for this application.

### Story 2.9: Prompt-template versioning

As a solo developer,
I want every prompt template stored as a versioned file in the repo, with the version string recorded in per-application metadata,
So that I can A/B prompt revisions safely and correlate output quality with template version when I review my stats.

**Acceptance Criteria:**
**Given** a prompt template file lives at `prompts/<artifact>.v{N}.md` (e.g. `prompts/cv.v3.md`) **When** the pipeline loads the template **Then** the version string `v3` is extracted from the filename (or from a frontmatter `version:` field) and made available to the metadata writer.

**Given** `config.yaml` has `prompts.cv: prompts/cv.v3.md` **When** I want to try a new revision **Then** I can change the path to `prompts/cv.v4.md` without touching code, and the new version flows through to metadata on the next run.

**Given** an application is generated using a set of templates **When** the per-application metadata is written **Then** the metadata's `prompt_templates` object contains one entry per artifact (e.g. `{"cv": "v3", "upwork_proposal": "v2"}`).

**Given** a template referenced in `config.yaml` does not exist on disk **When** the pipeline starts **Then** it fails fast with a clear error naming the missing template path, before any LLM call is made.

### Story 2.10: Per-application metadata sidecar and per-request cost logging

As a solo developer,
I want every generated package to write a structured JSON metadata sidecar capturing the JD source, parsed fields, drift-verdict placeholders, prompt-template versions, and total cost-to-produce, with per-request LLM token usage logged from the first call onward,
So that `GET /api/stats` can aggregate without re-parsing markdown and so no LLM call is ever unaccounted for.

**Acceptance Criteria:**
**Given** a pipeline run completes (pass or fail) **When** the metadata writer runs **Then** `./out/<slug>/metadata.json` exists and contains at minimum: `slug`, `source_board`, `jd_source` (e.g. `paste` | `n8n_upwork`), `parsed_jd` (the structured object from Story 2.3), `red_flags[]`, `artifacts_produced[]`, `prompt_templates{}`, `drift_verdicts{}` (placeholders `pending` in this epic; populated by Epics 3–5), `override` (boolean + reason, default `false`), and `cost{}` (total USD + per-call breakdown).

**Given** any LLM call is made **When** the call returns **Then** a per-request log entry captures `model`, `input_tokens`, `output_tokens`, `usd_cost`, and `purpose` (e.g. `jd_parse`, `tailor_cv`), and the entry is appended to the metadata sidecar's `cost.calls[]` array.

**Given** the per-application cost target is `$0.25` end-to-end (NFR4) **When** total cost is computed across all calls for one application **Then** the value is written to `cost.total_usd` and a boolean `cost.exceeded_per_app_target` is set when the per-app cap is breached.

**Given** the monthly hard cap (`cost.monthly_cap_usd`, FR43) would be breached by the next call **When** the pre-call cap check runs **Then** the pipeline refuses to make the call (NFR15) and writes a `cap_breached` verdict to metadata; the cap check is in the path before every LLM call.

**Given** a crash interrupts the pipeline mid-run **When** the run resumes or is inspected **Then** the partial metadata sidecar is still readable on disk (durable-on-disk per NFR14) and the state at crash is recoverable.

### Story 2.11: Internal POST /ingest endpoint with shared-token auth

As a solo developer,
I want the paste pipeline exposed behind a single internal `POST /ingest` endpoint, authenticated by a shared token from `.env`,
So that both the human CLI and the future n8n scheduled flows (Epic 7) call the same code path through the same contract, and a misconfigured n8n instance cannot post junk into the pipeline.

**Acceptance Criteria:**
**Given** the system is running **When** a client POSTs to `/ingest` with header `Authorization: Bearer <token>` matching `INGEST_TOKEN` in `.env` and a JSON body matching the JD-paste shape (`{"jd_text": "...", "source_board": "upwork"|null, "metadata": {...}}`) **Then** the endpoint runs the full pipeline (parse → classify → tailor → write artifacts → write metadata) and returns `{"slug": "...", "status": "passed"|"held"|"failed", "metadata_path": "..."}`.

**Given** a request arrives with a missing or mismatched bearer token **When** the auth check runs **Then** the endpoint returns HTTP 401 and the request never reaches the pipeline.

**Given** the request body fails JSON schema validation (e.g. `jd_text` missing or empty) **When** validation runs **Then** the endpoint returns HTTP 400 with a structured error and the request never reaches the LLM.

**Given** the browser JD-paste textarea (Story 1.6 / FR48) submits a JD **When** the frontend POSTs to the FastAPI app **Then** it hits the same `POST /api/paste` endpoint this story defines — there is exactly one code path that runs the pipeline, not two; n8n callers (Epic 7) and the browser frontend share the same handler. The shared-token check applies to non-loopback origins; browser-origin requests from `127.0.0.1` are accepted without the token header (`DECISIONS.md` §6 — no auth in v1).
**And** the endpoint never logs into any third-party platform account on behalf of the user (FR11); it accepts pre-fetched JD text only.

**Given** the endpoint receives a valid request **When** the pipeline runs **Then** the paste-mode 90-second end-to-end latency target (NFR1) is respected for the synchronous response path on the chosen LLM provider's standard tier.

### Story 2.12: Stats API + Dashboard stats card

As a solo developer,
I want a `GET /api/stats` endpoint that aggregates per-application metadata into rolling cost-per-application, drift-catch rate, override rate, and a 30-application interview-conversion window, plus a Dashboard stats card on the home surface that renders it,
So that the project's defining KPIs are always visible in the browser and I never have to grep markdown to know how the tool is doing.

**Context.** Reframed 2026-05-23 from `jobhunter stats` CLI to web-only (`DECISIONS.md` §6). Aggregation logic stays the same — it just moves behind an HTTP endpoint, and the rendering moves into the Dashboard surface from Epic 6 (this story ships the card; Epic 6 owns the broader Dashboard composition).

**Acceptance Criteria:**

**Given** at least one application's metadata sidecar exists in `./out/`,
**When** the frontend requests `GET /api/stats`,
**Then** the backend returns JSON with `applications_total`, `cost_per_app_avg_usd`, `cost_per_app_p95_usd`, `monthly_spend_usd`, `drift_catch_rate` (`packages_held / packages_total`), `override_rate` (`overrides / packages_held`), and `interview_conversion_rate_30app` (rolling-30-application window when ≥ 30 applications exist; otherwise the response includes the current `n` and `"insufficient_data": true`).

**Given** the request includes query params,
**When** the frontend issues `GET /api/stats?since=2026-04-01` or `GET /api/stats?board=upwork`,
**Then** the aggregation is filtered to the matching applications.

**Given** the per-app cost target is `$0.25` (NFR4),
**When** the endpoint returns,
**Then** the response includes a `"cost_regression_window": true|false` flag set true if `cost_per_app_avg_usd > 0.25` so the frontend can highlight the regression without re-computing it.

**Given** application metadata records `interview_reached: true|false` (a user-settable field the author updates when a screen happens),
**When** stats are computed,
**Then** `interview_conversion_rate_30app` reflects the rolling-30 window and is the single number that maps to the brief's primary success metric.

**Given** the endpoint runs,
**When** it reads metadata sidecars,
**Then** it never re-parses markdown artifacts (per NFR22) — all aggregation reads from the structured metadata sidecars only,
**And** no database or other persistence layer is introduced (`DECISIONS.md` §6).

**Given** the Dashboard surface owned by Epic 6 mounts,
**When** the user opens `/` in the browser,
**Then** a stats card renders the four primary KPIs (avg cost-per-app, monthly spend, drift-catch rate, interview-conversion rate),
**And** the card uses design tokens from `design.md` (no ad-hoc hex/pixel values),
**And** the regression flag visibly colors the cost card when set (FR40).

### Story 2.13: Settings & Canonical CV editor surface

As a solo developer (the author),
I want a browser editor for the canonical CV that preserves the JSON Resume schema, the `tags` field, and the `highImpact` flag, and that writes changes back to the canonical-CV file on disk,
So that I can adjust canonical-CV entries from the browser instead of hand-editing JSON when I notice a missing skill mid-review — and Epic 2's tagging + high-impact-flag work has a surface from day one.

**Context.** Was Epic 8.3 under the old hybrid architecture. Folded into Epic 2 by the 2026-05-23 pivot (`DECISIONS.md` §6) because this surface uses Story 2.1's tagging schema + high-impact flag directly — shipping them as one vertical slice is cleaner than carrying a UI epic to the end.

**Acceptance Criteria:**

**Given** Story 2.1 (canonical-CV tagging schema + high-impact flag) is done and Story 1.6 (FastAPI scaffold) is in place,
**When** the frontend requests `GET /api/canonical-cv`,
**Then** the backend invokes `jobhunter.canonical_cv.read_canonical_cv()` (the only reader contract — `DECISIONS.md` §2) and returns the parsed JSON Resume document,
**And** the document round-trips losslessly: tags, high-impact flags, and JSON Resume v1.0.0 fields are all preserved.

**Given** the editor surface is loaded at `/settings`,
**When** the page renders,
**Then** it matches the layout of `design_guidelines/stitch-export/html/02-settings-canonical-cv.html`,
**And** all sections of the canonical CV (basics, work, education, skills, projects) are editable inline with per-entry tag and high-impact-flag controls (FR2, FR3),
**And** all design tokens come from the Tailwind config built off `design.md` (FR47).

**Given** edits are made,
**When** the user clicks Save,
**Then** the frontend POSTs the full document to `PUT /api/canonical-cv`,
**And** the backend validates the payload against the vendored `schemas/jsonresume-v1.0.0.json` schema before writing,
**And** on validation failure the backend returns `422` with the failing JSON Pointer path(s) and the file on disk is unchanged,
**And** on success the backend writes the new document atomically (write-to-temp + rename) and returns `200`.

**Given** the canonical-CV file is modified out-of-band (e.g. the user edits it in their editor),
**When** the editor surface is reloaded,
**Then** the read-fresh contract from `DECISIONS.md` §2 holds — the new contents appear with no caching.

### Story 2.14: JD Pipeline & Tailoring surface — staged-package viewer

As a solo developer (the author),
I want a per-package detail page that shows the JD, the tailored CV, the tailored cover letter (or Upwork proposal), and the package metadata side-by-side, plus a "Tailor a new JD" entry point,
So that I can review a single tailoring run without flipping between four files, and the JD-paste flow from Story 1.6 has a real production-quality surface instead of the minimal walking-skeleton textarea.

**Context.** Was Epic 8.4 under the old hybrid architecture. Folded into Epic 2 by the 2026-05-23 pivot (`DECISIONS.md` §6) because this surface consumes Epic 2's structured JD parser (Story 2.3), Upwork-proposal artifact (Story 2.7), per-board artifact-set selector (Story 2.8), and metadata sidecars (Story 2.10) — shipping them together as one vertical slice avoids carrying a UI epic to the end.

**Acceptance Criteria:**

**Given** Stories 2.3, 2.7, 2.8, 2.10 are done and Story 1.6 is in place,
**When** the frontend requests `GET /api/package/<slug>`,
**Then** the backend reads `./out/<slug>/`'s artifacts (JD text, tailored CV markdown, tailored cover letter markdown OR Upwork proposal markdown depending on board, `package.metadata.json`) and returns a JSON document with each artifact's contents and metadata,
**And** the route returns `404` for slugs that do not exist on disk.

**Given** the page is loaded at `/packages/<slug>`,
**When** it renders,
**Then** the layout matches `design_guidelines/stitch-export/html/04-jd-pipeline-tailoring.html`,
**And** the JD, tailored CV, and cover letter (or Upwork proposal) are rendered as markdown using a vetted library (no `dangerouslySetInnerHTML` on raw model output),
**And** the package metadata sidebar shows source board (FR13), parsed JD fields (FR12), Upwork-specific signals where applicable (FR14), prompt-template versions (FR21), and cost-per-request (FR39),
**And** all design tokens come from `design.md` (FR48).

**Given** the JD-paste flow,
**When** the user pastes a JD into the textarea on the home surface and submits,
**Then** the request hits `POST /api/paste` (Story 1.6 / FR6),
**And** on success the browser navigates to `/packages/<slug>` for the freshly staged package (the home textarea is preserved as a fast-entry path; the dedicated JD pipeline surface is for review),
**And** the route returns `404` for slugs that do not exist on disk — no broken layout on race conditions.

**Given** the package's metadata indicates a held state (Epic 3/4/5 drift fail, lands later),
**When** the page renders,
**Then** an "Approve override" action button is visible but disabled with a tooltip "Drift override available after Epic 6 ships" (cross-epic dependency — the button activates when Story 6.4's override endpoint lands).

## Epic 3: Fabrication Drift Check

The headline moat — the check that makes Job Hunter structurally different from every shipping competitor, and the one the brief insists ships first among the drift checks. For each tailored CV, every asserted skill or claim must trace to a real entry in the canonical CV. The traceability check is structural — string match plus a semantic-equivalence threshold on canonical-CV entries — not an LLM grading another LLM. A failed trace fails the package; the offending claim, its location in the tailored output, and the reason it failed traceability are written to the per-application metadata file (FR22, FR23, FR24). This is the first epic that produces a "held" package, so it also establishes the held-package pattern that epics 4, 5, and 6 build on: artifacts are written to disk on fail (so the author can read them), but no notification fires. The LLM provider for v1 (Anthropic, OpenAI, or local) is finalized in this epic's first story per PO direction — the decision hinges on which provider's tracing best supports the structural claim-matching this check requires. If the structural check turns out too brittle to ship clean, the documented fallback (per PRD risk mitigation) is a hybrid: structural matching for the easy cases, plus a targeted LLM double-check for hard semantic-equivalence cases only.

### Story 3.1: Finalize LLM Provider and Build Atomic Claim Extractor

As a solo developer building the fabrication drift check,
I want to lock in the v1 LLM provider via a written decision artifact and then build a claim extractor that decomposes the tailored CV and cover letter into atomic, addressable claims,
So that every subsequent drift check has a stable provider contract and a deterministic input shape (one claim per assertion) to match against the canonical CV — instead of trying to match free-form prose blobs.

**Precondition:** Epic 2's canonical-CV tagging schema (FR2) and the JSON Resume working-assumption schema must already exist on disk; the extractor reads canonical-CV entry boundaries to know what "atomic" looks like.

**Acceptance Criteria:**

**Given** Anthropic, OpenAI, and a local-model option are all candidate providers per the PRD,
**When** I evaluate each against the four PO-stated criteria (cost-per-app under $0.25, no-training data-handling terms per NFR10, structured/JSON output reliability for claim extraction, and quality of traces for structural matching),
**Then** a decision artifact is written to `_bmad-output/decisions/llm-provider.md` capturing the chosen provider, the model name, the per-1K-token input/output prices used in the cost math, the rejected alternatives with one-line rationale each, and a "revisit if" clause naming the specific conditions that would trigger reopening the decision,
**And** the chosen provider's model name, base URL, and API key environment variable are all wired into `config.yaml` and `.env.example` so a provider switch is a config change (per NFR16) and not a code rewrite.

**Given** the LLM provider decision is locked in and the canonical CV is readable from disk,
**When** the claim extractor is invoked on a tailored CV markdown file,
**Then** it emits a structured `claims.json` array in which every element has the shape `{ claim_id, claim_type, claim_text, source_artifact, line_number }` where `claim_type` is one of `role`, `metric`, `skill`, `tool`, `responsibility`, or `accomplishment`,
**And** each role bullet, each numeric metric, each named skill, each named tool, and each accomplishment statement appears as its own atomic claim — verified by running the extractor on a fixture tailored CV containing at least 3 roles, 5 skills, and 2 metrics and confirming the claim count is at least 10.

**Given** the same claim extractor is run on a tailored cover letter,
**When** the cover letter contains assertions about experience, skills, or accomplishments,
**Then** each assertion is extracted as its own claim with `source_artifact: "cover_letter"` and a valid `line_number`,
**And** non-assertive prose (greetings, closings, JD restatements, opinion phrases) is not extracted as claims — verified by a fixture cover letter where the expected claim count is documented in the test and the extractor matches it within +/- 1.

**Given** any LLM call made during extraction,
**When** the call completes (success, failure, or timeout per NFR3),
**Then** per-request token usage and dollar cost are logged to the per-application metadata file (consistent with FR39 from Epic 2),
**And** the extractor respects the configurable per-call timeout from `config.yaml` and fails the package with verdict `extraction_timeout` rather than hanging.

---

### Story 3.2: Structural Matcher with Claim-to-Source-CV Traceability

As a solo developer who needs the fabrication check to be deterministic and defensible,
I want every extracted claim to be matched against the canonical CV (JSON Resume schema entries) via structural matching, producing a per-claim trace,
So that the check's pass/fail verdict is auditable — a recruiter or peer reviewing the output can see exactly which canonical-CV entry sourced each claim, rather than trusting an LLM's vibes.

**Acceptance Criteria:**

**Given** a populated `claims.json` from Story 3.1 and the canonical CV in JSON Resume schema on disk,
**When** the structural matcher runs,
**Then** it produces `package.drift.json` at `./out/<slug>/package.drift.json` containing a top-level `fabrication_check` object with the shape `{ verdict: "pass" | "fail", claims_total, claims_sourced, claims_unsourced, traces: [...], unsourced_claims: [...] }`,
**And** every entry in `traces` has the shape `{ claim_id, claim_text, matched_canonical_entry_id, match_method: "exact_string" | "substring" | "semantic", match_score }` linking the tailored-output claim to its source-CV entry.

**Given** the matcher is processing a single claim,
**When** an exact case-insensitive string match exists against any canonical-CV entry's text or tag field,
**Then** the claim is recorded as sourced with `match_method: "exact_string"` and `match_score: 1.0`,
**And** when no exact match exists but the claim text is a substring of (or contains) a canonical-CV entry text, the claim is recorded as sourced with `match_method: "substring"`,
**And** when neither exact nor substring matches exist, the claim is handed to the semantic-equivalence step defined in Story 3.3.

**Given** the matcher has finished processing all claims,
**When** at least one claim has no successful match (exact, substring, or semantic),
**Then** `fabrication_check.verdict` is `"fail"` and `unsourced_claims` contains at least one entry with `{ claim_id, claim_text, source_artifact, line_number, reason }` per FR24,
**And** the package is held — the staged markdown artifacts are still written to `./out/<slug>/` per FR34, but no GChat notification fires (per FR33; the wiring of the notification itself lands in Epic 6, so for now the matcher's contract is "emit verdict and unsourced_claims to disk and exit non-zero").

**Given** the matcher has finished processing all claims,
**When** every single claim has a successful match,
**Then** `fabrication_check.verdict` is `"pass"`, `claims_unsourced` is `0`, and the `unsourced_claims` array is empty,
**And** the per-application metadata file (FR38) records `drift.fabrication: "pass"` with the path to `package.drift.json` for auditability.

**Given** the matcher reads the canonical CV,
**When** the canonical CV file is the JSON Resume schema working-assumption from Epic 1,
**Then** the matcher reads `work[].highlights[]`, `skills[].keywords[]`, `projects[].highlights[]`, and `education[]` entries as the universe of sourceable entries,
**And** the canonical-CV entry IDs referenced in `traces[].matched_canonical_entry_id` are stable across runs (derived from a deterministic hash of section + index + entry text) so re-runs produce diffable drift files.

---

### Story 3.3: Semantic-Equivalence Threshold for Tolerated Paraphrase

As a solo developer who wants the fabrication check to tolerate honest paraphrase but reject embellishment,
I want claims that fail exact and substring matching to go through a semantic-equivalence check with an explicit, configurable threshold,
So that "led the team" -> "led the engineering team" passes (same fact, different wording) while "led the team" -> "led a 3-person engineering team" fails (the team size is fabricated, not present in the canonical CV).

**Acceptance Criteria:**

**Given** a claim that did not match exact or substring matching in Story 3.2,
**When** the semantic-equivalence step runs,
**Then** the system computes a similarity score in `[0.0, 1.0]` between the claim text and each candidate canonical-CV entry using one of two configurable methods declared in `config.yaml` under `fabrication.semantic_method`: `"embedding_cosine"` (computed via the locked-in LLM provider's embeddings endpoint) or `"rule_based"` (token-overlap Jaccard plus stemming),
**And** the chosen method, the configured threshold value (default `0.82` for `embedding_cosine`, default `0.65` for `rule_based`), and the rationale for the default are recorded in `_bmad-output/decisions/llm-provider.md` (extending the Story 3.1 artifact) so the threshold is a documented decision, not a magic number.

**Given** a claim is evaluated against the canonical CV via semantic equivalence,
**When** the highest similarity score across all candidate entries is at or above the configured threshold,
**Then** the claim is recorded as sourced with `match_method: "semantic"` and the actual `match_score` (so the author can later inspect borderline cases),
**And** when the highest score is below the threshold, the claim is recorded as unsourced with `reason: "semantic_below_threshold (score=<x>, threshold=<y>)"` so the gap is visible.

**Given** the embellishment guard,
**When** a claim contains a numeric quantifier (team size, dollar amount, percentage, headcount, year span) that does not appear in the matched canonical-CV entry,
**Then** even if the textual similarity is above threshold, the claim is recorded as unsourced with `reason: "quantifier_not_in_source"` and the specific quantifier token is captured in the `unsourced_claims` entry,
**And** this rule is verified by a fixture pair where the canonical CV says "led the engineering team" and the tailored output says "led a 3-person engineering team" — the test asserts `verdict: "fail"` with `reason` matching `quantifier_not_in_source`.

**Given** the documented hybrid fallback in the PRD risk-mitigation section,
**When** the structural and semantic steps both fail to source a claim but the claim type is `skill` or `tool` (the easier cases),
**Then** the system does NOT invoke a third LLM-as-judge pass in v1 — it fails the claim cleanly,
**And** an inline `# TODO(hybrid-fallback):` comment in the matcher code references the PRD's hybrid-fallback option so future-Dave can wire it in if v1 over-flags in real use.

---

### Story 3.4: Held-Package Pattern with Hard-Fail Policy and 7-Day Retention

As a solo developer who needs a fabrication-fail package to be recoverable for manual review but never auto-delivered,
I want the held-package pattern formalized — artifacts written to disk, no notification, a metadata sidecar capturing exactly which claims failed and where, and a default 7-day retention after which held packages are discarded,
So that fabrication-fail packages do not leak to the user via accidental notification, but the author can still inspect and (in Epic 6) eventually override them, and stale held packages do not pile up on disk forever.

**Acceptance Criteria:**

**Given** the structural matcher (Story 3.2) or semantic check (Story 3.3) emits `fabrication_check.verdict: "fail"`,
**When** the pipeline finishes,
**Then** the package is in HELD state: all tailored markdown artifacts are present at `./out/<slug>/` per FR34, a `package.held.json` sidecar is written at `./out/<slug>/package.held.json` with `{ held_at, held_by_check: "fabrication", failed_claims: [...], retention_expires_at, recoverable: true }`,
**And** `failed_claims[]` mirrors `unsourced_claims[]` from `package.drift.json` and additionally pins each failed claim to a precise location `{ artifact_path, line_number, column_start, column_end }` so the author can jump to it in their editor.

**Given** a package is in HELD state,
**When** the pipeline exits,
**Then** the Google Chat notification (FR31, owned by Epic 6) is NOT sent — verified by asserting that the held-state branch does not invoke the notification module at all (rather than invoking it and suppressing it, to keep the no-notification contract structural),
**And** the per-application metadata file (FR38) records `drift.fabrication: "fail"`, `held: true`, `held_path: "./out/<slug>/package.held.json"` so a future `GET /api/queue` (Epic 6, FR35) can enumerate held packages by reading metadata only.

**Given** held packages accumulate over time,
**When** any pipeline run starts,
**Then** before doing any LLM work, the pipeline scans `./out/` for `package.held.json` sidecars whose `retention_expires_at` is in the past (default: 7 days after `held_at`, configurable in `config.yaml` under `fabrication.held_retention_days`) and discards those packages by removing the `./out/<slug>/` directory entirely,
**And** a one-line audit entry per discarded package is appended to `./out/_held-audit.log` with `{ slug, held_at, discarded_at, failed_claims_count }` so discards are not silent.

**Given** the hard-fail policy,
**When** the fabrication check fails for any reason (unsourced claim, quantifier mismatch, extraction timeout, matcher error),
**Then** the package is held — there is no "soft fail" or "warn-only" mode in v1; the verdict is binary,
**And** the manual override path (FR36, owned by Epic 6) is the ONLY way a held fabrication-fail package can be released — verified by asserting that no code path in Epic 3 promotes a HELD package to PASSED.

### Story 3.5: Drift Check Diagnostics surface — fabrication section

As a solo developer (the author),
I want a browser drift diagnostics page for each package that visualizes the fabrication-check findings with claim→source traceability — the JSON drift report rendered as a navigable surface,
So that the structured `package.drift.json` document Stories 3.1–3.4 produce is genuinely readable instead of a wall of JSON, and the diagnostics surface from Stitch screen 05 lands incrementally (fabrication section now, content-loss in 4.4, keyword-stuffing in 5.4).

**Context.** This story was Epic 8.5 in the prior hybrid architecture. Per the 2026-05-23 pivot (`DECISIONS.md` §6), the diagnostics surface is built incrementally — one drift section per epic — so each epic ships a complete vertical slice (backend logic + UI surface) instead of carrying a UI epic to the end.

**Acceptance Criteria:**

**Given** Stories 3.1–3.4 (fabrication drift + held pattern) are done and the FastAPI scaffold from Story 1.6 is in place,
**When** the frontend requests `GET /api/package/<slug>/drift`,
**Then** the backend returns the parsed `./out/<slug>/package.drift.json` (with the fabrication section populated; other drift sections may be absent until Epics 4 and 5 land),
**And** the route returns `404` for packages with no drift report on disk (e.g. Epic 1 walking-skeleton runs).

**Given** the page is loaded at `/packages/<slug>/drift`,
**When** it renders,
**Then** the overall layout matches `design_guidelines/stitch-export/html/05-drift-check-diagnostics.html`,
**And** the fabrication section lists each failed claim with its location in the tailored output and a "no source entry found in canonical CV" reason (FR24),
**And** if the drift report contains no fabrication failures, the section renders an empty pass state matching the design,
**And** sections for content-loss and keyword-stuffing render as "pending — not yet implemented" placeholders until Stories 4.4 and 5.4 land (so the page is renderable end-to-end now without crashing on missing keys),
**And** all design tokens come from `design.md` (FR49, fabrication slice).

**Given** a failed claim has any candidate canonical-CV entries (string-match near-misses),
**When** the user hovers/clicks the claim,
**Then** the UI surfaces those near-misses inline (no navigation away),
**And** uses the focus/active states defined in `design.md`.

**Given** the JD Pipeline & Tailoring surface from Story 2.14 is rendering a held package,
**When** the user clicks "View drift diagnostics",
**Then** the SPA navigates to `/packages/<slug>/drift`,
**And** the URL is bookmarkable and reload-safe.

## Epic 4: Content-Loss Drift Check

Catches the "AI cut your best line" failure mode that the brief identifies as the second drift dimension. The canonical-CV tagging schema (FR2) and the high-impact flag (FR3) from Epic 2 are the inputs; this epic builds the check on top of them. For each tailored output, the system verifies that canonical-CV entries flagged as high-impact appear in the tailored output when the JD's parsed must-have or nice-to-have requirements call for them (FR25). When a high-impact, relevant entry is dropped, the package is held, and the per-application metadata records which entry was dropped along with the JD requirement it would have addressed (FR26, FR27) — so the author has actionable signal, not just a fail verdict. This epic ships second among the drift checks per the non-negotiable build order; the fabrication check (Epic 3) must be stable first because it is the only check whose failure makes output structurally unsendable.

### Story 4.1: High-impact relevance check against JD must-haves and nice-to-haves

As the solo developer who built this tool,
I want the pipeline to verify that every canonical-CV entry flagged as high-impact and relevant to the JD's parsed requirements appears in the tailored output (or carries an explicit, logged omission rationale),
so that the AI cannot quietly drop my strongest wins on the way to a tailored package.

**Precondition (hard):** Epic 2's high-impact tagging schema is in place. Specifically, the canonical CV (JSON Resume schema with the working-assumption fallback to minimal custom YAML per Epic 1) exposes a per-entry `high_impact: true|false` flag (FR3) and per-entry `tags: [...]` (FR2). The structured JD parser (FR12) already emits `must_haves: [...]` and `nice_to_haves: [...]` as discrete arrays. If either upstream contract is missing, this story is blocked and cannot start.

**Acceptance Criteria**

- **AC1 — Relevance anchoring is deterministic and structural.**
  - Given a canonical-CV entry with `high_impact: true` and `tags: ["typescript", "node"]`,
  - And a parsed JD whose `must_haves` contains `"typescript"` (case-insensitive normalized match) or whose `nice_to_haves` contains `"typescript"`,
  - When the content-loss check runs,
  - Then the entry is classified as `relevant_to_jd: true` and is added to the "must-appear" set for this run.
  - No LLM call is made to decide relevance — the matcher is rule-based (default) or embedding-distance with an explicit cutoff, per `config.yaml` (see Story 4.3).

- **AC2 — Presence verification in the tailored output.**
  - Given an entry in the "must-appear" set,
  - When the tailored markdown CV (`./out/<slug>/cv.md`), cover letter (`./out/<slug>/cover-letter.md`), and Upwork proposal (`./out/<slug>/proposal.md`) artifacts written by Epic 1/2 are scanned,
  - Then the check passes for that entry if a substring of the canonical-CV entry's normalized text, or a semantic-equivalent passage above the configured threshold, appears in at least one artifact.
  - The match is anchored to the canonical-CV entry's primary text field (JSON Resume `highlights[]` bullets, `summary`, or `name`/`position` depending on entry type) — not to its tags.

- **AC3 — Explicit omission rationale path.**
  - Given a tailoring step that intentionally dropped a high-impact entry,
  - When the tailoring step writes its trace to `./out/<slug>/tailoring.trace.json` with a `dropped_entries[]` array where each item is `{ "entry_id": "<id>", "reason": "irrelevant_to_jd" }`,
  - Then the content-loss check reads that trace, treats those entries as having an explicit rationale, and does not fail solely on their absence.
  - A `dropped_entries[]` item missing the `reason` field, or carrying an unknown reason code, is treated as a silent drop and fails the check.

- **AC4 — CLI exit code and held-package behavior.**
  - Given at least one high-impact, JD-relevant entry is silently absent (no rationale logged),
  - When `POST /api/paste` runs end-to-end,
  - Then the content-loss check exits with the per-check fail signal (non-zero internal verdict) and the package is held per the Epic 3 held-package pattern (artifacts still written to `./out/<slug>/`, no notification fires).
  - Given all high-impact JD-relevant entries are present or have logged rationales,
  - Then the content-loss check returns `pass` and the pipeline proceeds to the next check (keyword-stuffing in Epic 5, or notification in Epic 6 once that lands).

- **AC5 — No LLM-as-judge.**
  - Given the check is running,
  - Then it makes zero LLM calls of its own. It consumes only: the canonical CV file, the parsed JD JSON, the tailored markdown artifacts, and the tailoring trace.
  - This is verified by a smoke test asserting `0` new entries in the per-request token log (FR39) between the start and end of the content-loss check phase.

**Notes / scope guardrails**

- INVEST budget: 1–2 nights/weekends. The matcher is rule-based by default; embedding-distance is a configurable upgrade path landed in Story 4.3, not built here.
- Defaults skew conservative (high recall): if relevance is uncertain, the entry is treated as relevant and must appear — false positives the author overrides, not false negatives that lose wins silently.

---

### Story 4.2: Drop-detection diff and structured drift metadata in package.drift.json

As the solo developer reviewing held packages and tuning the check over time,
I want every content-loss run to persist a structured diff of preserved versus dropped high-impact entries (with reason codes) at a known JSON path,
so that I get actionable signal on what was lost and why, and so that `GET /api/stats` (FR40) can aggregate drop patterns across applications without re-parsing markdown (NFR22).

**Acceptance Criteria**

- **AC1 — Output file location and shape.**
  - Given any content-loss check run (pass or fail),
  - When the check completes,
  - Then a file is written to `./out/<slug>/package.drift.json`.
  - If the file already exists from the Epic 3 fabrication check, the content-loss check writes its results under the top-level key `content_loss`, without overwriting any sibling keys (e.g. `fabrication`).
  - The `content_loss` object has the following shape:
    ```
    {
      "verdict": "pass" | "fail",
      "check_version": "<semver string from config>",
      "ran_at": "<ISO-8601 timestamp>",
      "preserved_entries": [
        { "entry_id": "<id>", "matched_in": ["cv.md" | "cover-letter.md" | "proposal.md"], "match_type": "substring" | "semantic" }
      ],
      "dropped_entries": [
        { "entry_id": "<id>", "jd_requirements_addressed": ["<must-have-or-nice-to-have-string>", ...], "reason": "irrelevant_to_jd" | "silently_lost" }
      ]
    }
    ```

- **AC2 — Reason codes are an enumerated, fail-discriminating set.**
  - Given a drop with `reason: "irrelevant_to_jd"` (sourced from a logged rationale in `tailoring.trace.json` per Story 4.1 AC3),
  - Then this drop does not contribute to a fail; `verdict` can still be `pass`.
  - Given a drop with `reason: "silently_lost"` (the entry was JD-relevant, was high-impact, and was not present in any artifact and had no logged rationale),
  - Then `verdict` is `fail` and the package is held.
  - Any unrecognized reason string is treated as `silently_lost` and triggers fail. The enumerated set lives in `config.yaml` under `drift.content_loss.reason_codes` so new codes (e.g. `dropped_for_length`) can be added without code changes, per FR42 / NFR20.

- **AC3 — JD requirements addressed are captured per drop.**
  - Given a high-impact entry with `tags: ["typescript", "fintech"]` that matched the JD's must-have `"typescript"`,
  - When that entry is recorded under `dropped_entries[]`,
  - Then `jd_requirements_addressed` contains `"typescript"` (the exact normalized string from the JD parser's `must_haves` / `nice_to_haves` arrays).
  - This satisfies FR27 — the author can read `package.drift.json` and see exactly which JD requirement is now unanswered in the tailored output.

- **AC4 — Idempotency and re-run behavior.**
  - Given a previous `package.drift.json` exists for this slug,
  - When the content-loss check re-runs,
  - Then the `content_loss` key is replaced wholesale (not merged at the entry level); preserved/dropped arrays from previous runs do not bleed into the new run.
  - Sibling keys at the top level (e.g. `fabrication` from Epic 3) are preserved unchanged.

- **AC5 — Stats command can consume the file unchanged.**
  - Given `GET /api/stats` (FR40) is run against an `./out/` directory containing multiple slugs,
  - When it walks `package.drift.json` files,
  - Then it can compute drop-catch-rate (count of `silently_lost` drops / total applications) and reason-code distribution without parsing any markdown.
  - A smoke test loads two synthetic `package.drift.json` files and asserts the aggregator produces a stable, schema-valid summary.

- **AC6 — Held-package wiring.**
  - Given `verdict: "fail"` in the `content_loss` block,
  - When the pipeline checks whether to hold the package,
  - Then the package is held per the Epic 3 pattern: artifacts remain on disk (FR34), no GChat ping fires (FR33 — wired in Epic 6, stubbed for now as a no-op that respects the held flag).
  - The held verdict is also reflected in the per-application metadata sidecar (FR38) so `GET /api/queue` (FR35, Epic 6) can later list the failure reason without re-running the check.

**Notes / scope guardrails**

- INVEST budget: 1–2 nights/weekends.
- This story is the persistence half of the check; Story 4.1 is the logic half. They are intentionally split so Story 4.1 can ship and prove the matcher works against fixtures, then Story 4.2 hardens the disk format.

---

### Story 4.3: Configurable relevance threshold and matcher mode in config.yaml

As the solo developer who will tune this check after running it against 20–30 real applications,
I want the "what counts as relevant" decision and the "what counts as a presence match" decision to live in `config.yaml`, with conservative defaults,
so that I can tighten or loosen the check based on real-world override-rate data without redeploying code (NFR20).

**Acceptance Criteria**

- **AC1 — Config keys exist with documented defaults.**
  - Given a fresh `config.yaml`,
  - When the content-loss check loads its config,
  - Then the following keys are read from `drift.content_loss.*`:
    ```
    drift:
      content_loss:
        relevance_matcher: "tag_overlap"        # one of: "tag_overlap" | "keyword_overlap" | "embedding_distance"
        tag_overlap_min: 1                       # min count of overlapping tags between entry.tags and (must_haves + nice_to_haves) to mark relevant
        keyword_overlap_pct: 0.20                # used when relevance_matcher == "keyword_overlap"
        embedding_distance_max: 0.35             # used when relevance_matcher == "embedding_distance"; cosine distance cutoff
        presence_matcher: "substring"            # one of: "substring" | "semantic"
        presence_semantic_threshold: 0.80        # cosine similarity cutoff when presence_matcher == "semantic"
        reason_codes: ["irrelevant_to_jd", "silently_lost"]
    ```
  - These defaults are the conservative-high-recall defaults: `tag_overlap_min: 1` flags any single-tag overlap as relevant; `presence_matcher: "substring"` requires concrete textual presence.

- **AC2 — Switching matcher mode does not require a code change.**
  - Given a user sets `relevance_matcher: "embedding_distance"` and provides a working embeddings client,
  - When the content-loss check runs,
  - Then it computes embedding distance between each high-impact entry's primary text and the JD's `must_haves + nice_to_haves` concatenated, and treats entries with distance ≤ `embedding_distance_max` as relevant.
  - Given the embeddings client is not configured but `embedding_distance` mode is selected,
  - Then the check exits with a non-zero verdict and a clear error string in `package.drift.json` (`"verdict": "fail", "error": "embedding matcher selected but no embeddings client configured"`) — it does not silently fall back to a less strict matcher.

- **AC3 — Defaults are conservative (high recall) and documented inline.**
  - Given the default config ships in the repo,
  - When the author reviews `config.yaml`,
  - Then each key under `drift.content_loss` has a one-line comment explaining the trade-off (e.g. `# lower = more flags, higher recall; raise after 20+ apps if overrides dominate`).
  - This makes the tuning loop legible to a solo author returning to the config months later.

- **AC4 — Threshold changes are reflected in `package.drift.json` for traceability.**
  - Given the check runs with a non-default threshold,
  - When `package.drift.json` is written,
  - Then a `config_snapshot` sub-object under `content_loss` captures the effective `relevance_matcher`, `presence_matcher`, and the relevant numeric threshold for this run.
  - This lets the author correlate `verdict` changes with config changes when reviewing historical drift logs — closing the loop that NFR20 / NFR21 set up for prompt-template versioning.

- **AC5 — Cost-cap and no-LLM-call guarantees are preserved.**
  - Given any matcher mode is selected,
  - Then the content-loss check makes zero LLM completion calls (Story 4.1 AC5 still holds).
  - Embedding calls, when `embedding_distance` mode is on, are counted in the per-request token log (FR39) and respect the hard monthly spend cap (FR43, NFR15) — the cap check happens before the embeddings call is made.

**Notes / scope guardrails**

- INVEST budget: 1 night/weekend. The story is intentionally narrow: config plumbing + the embedding-distance mode as the upgrade path. The substring/tag-overlap default does not require an embeddings client and is the happy path for v1.
- This story is optional per the epic plan — if Story 4.1 and 4.2 land with hard-coded conservative defaults and the matcher proves good enough in real use, this story can be deferred to v1.1. Including it now keeps the "tunable not redeployable" stance honest from day one.

### Story 4.4: Drift Check Diagnostics surface — content-loss section

As a solo developer (the author),
I want the drift diagnostics page (live since Story 3.5) extended with a content-loss section that lists dropped high-impact entries and the JD requirements they would have addressed,
So that the diagnostics surface keeps growing in lockstep with each new drift dimension, and Epic 4's `package.drift.json.content_loss` block becomes legible in the browser instead of a JSON read.

**Context.** Was Epic 8.5 (content-loss portion) under the prior hybrid architecture. Folded into Epic 4 per the 2026-05-23 pivot (`DECISIONS.md` §6) so the content-loss check ships as one vertical slice — logic + UI together.

**Acceptance Criteria:**

**Given** Stories 4.1–4.2 (high-impact relevance + drop-detection drift metadata) are done and Story 3.5 (drift diagnostics surface with fabrication section) is live,
**When** the frontend requests `GET /api/package/<slug>/drift` and the response includes a `content_loss` block,
**Then** the page at `/packages/<slug>/drift` renders a populated content-loss section replacing the placeholder Story 3.5 shipped,
**And** each dropped high-impact entry is listed with its source canonical-CV identifier, the JD requirement(s) it would have addressed (must-have vs nice-to-have label), and the relevance-matcher mode + threshold used for the run (from Story 4.2's `config_snapshot`),
**And** the section matches the layout of the content-loss portion of `design_guidelines/stitch-export/html/05-drift-check-diagnostics.html` (FR49, content-loss slice).

**Given** the package passed the content-loss check,
**When** the section renders,
**Then** an empty pass state is shown matching the design (not a missing/broken layout),
**And** the rest of the diagnostics page (fabrication, sidebar) is unaffected.

**Given** the user clicks a dropped high-impact entry,
**When** the UI responds,
**Then** the canonical-CV source entry is highlighted inline (same interaction pattern Story 3.5 uses for fabrication near-misses) so the author can see what was lost.

## Epic 5: Keyword-Stuffing Drift Check

The third drift dimension. ATS systems are universal (97.8% of F500), but recruiter-side AI detection now actively rejects over-stuffed outputs — the brief flags this as the #1 modern recruiter tell. This epic measures density and placement of JD-derived keywords against configurable thresholds in `config.yaml` (FR28): no keyword repeats above the per-section limit, no paragraphs that read like keyword dumps (FR29). Offending keywords, their density measurements, and their locations in the tailored output are written to the per-application metadata file (FR30), so the author can see exactly what tripped the check on override. Thresholds ship intentionally conservative per the PRD PO Assumptions (high recall, more flags — false positives the author overrides, rather than false negatives that quietly let stuffing through). With this epic complete, all three v1 drift checks (fabrication, content-loss, keyword-stuffing) are live and the package-held/package-passed verdict is meaningful — which is exactly what Epic 6's notification logic needs.

### Story 5.1: Keyword density measurement against per-keyword thresholds

As the solo developer running tailored packages through the pipeline,
I want every JD-derived must-have keyword counted and density-scored against a configurable per-keyword threshold,
so that recruiter-tells like "TypeScript appears 11 times in a one-page CV" are caught deterministically before a package can pass — without false-negative drift from vibes-based judgment.

**Acceptance Criteria**

Given a tailored CV markdown artifact at `./out/<slug>/cv.md` and a parsed JD with a `must_haves[]` list of keywords,
When the keyword-stuffing check runs,
Then the system tokenizes the tailored output (whitespace-and-punctuation split, lowercased, comment/frontmatter stripped), counts the occurrences of each must-have keyword (case-insensitive, whole-token match), and computes density as `(occurrences / total_tokens) * 100` expressed as a percentage per keyword.

Given the computed density for each must-have keyword,
When any keyword's density exceeds the configured `keyword_stuffing.max_density_pct` threshold in `config.yaml` (default: `1.5`, meaning 1.5%),
Then the system flags that keyword as a density violation and the check verdict for the package is `fail`.

Given the same density computation,
When any single must-have keyword's raw occurrence count exceeds the configured `keyword_stuffing.max_repetitions_per_artifact` threshold in `config.yaml` (default: `3`),
Then the system flags that keyword as a repetition violation and the check verdict is `fail`, independent of the density threshold.

Given the check runs over a tailored CV plus a tailored cover letter (or Upwork proposal, per board classification from Epic 2),
When density and repetition are computed,
Then thresholds are evaluated per artifact file separately — a keyword appearing twice in `cv.md` and twice in `cover-letter.md` is not summed into one violation of "max 3 repetitions."

Given `config.yaml` does not specify the keyword-stuffing thresholds,
When the check runs,
Then the system uses the conservative defaults `max_density_pct: 1.5` and `max_repetitions_per_artifact: 3`, and these defaults are documented in the checked-in `config.yaml.example`.

Given the check completes with one or more density or repetition violations,
When the pipeline writes per-application metadata,
Then `./out/<slug>/package.drift.json` contains a `keyword_stuffing` object whose `density_violations[]` array includes one entry per violation with fields `keyword`, `artifact` (filename), `occurrences`, `total_tokens`, `density_pct`, and `threshold_breached` (one of `max_density_pct` or `max_repetitions_per_artifact`), and the `verdict` field is `"fail"`.

Given the check completes with no violations on any artifact,
When the pipeline writes per-application metadata,
Then the `keyword_stuffing` object's `density_violations[]` is `[]`, `dump_paragraph_locations[]` is `[]`, and `verdict` is `"pass"`.

Given the check is invoked via the pipeline,
When the keyword density computation runs end-to-end on a typical 600-token tailored CV with a 12-keyword must-have list,
Then it completes in deterministic time using only token counting and dict lookups — no LLM call is made by this check.

---

### Story 5.2: Dump-paragraph and comma-run placement detection

As the solo developer,
I want the classic ATS-tell anti-pattern detected — a "skills dump" paragraph where JD keywords appear without sentence context — using deterministic rule-based detection,
so that an output that passes per-keyword density but still reads like a keyword pile-up at the bottom of the CV gets caught; the *recruiter* on the other end never sees a paragraph that signals "AI-tailored, not personalized."

**Acceptance Criteria**

Given a tailored output artifact at `./out/<slug>/cv.md` (or `cover-letter.md` or `upwork-proposal.md`) and the parsed JD's `must_haves[]` keyword list,
When the dump-paragraph detector runs,
Then the system splits the artifact into paragraphs (blank-line-delimited blocks, excluding markdown headings and list markers), and for each paragraph computes (a) its token count, (b) the count of tokens that are JD must-have keywords, and (c) the must-have-keyword token ratio.

Given a paragraph with at least `keyword_stuffing.dump_paragraph_min_tokens` tokens (default: `15`),
When the must-have-keyword token ratio exceeds `keyword_stuffing.dump_paragraph_max_keyword_ratio` (default: `0.30`, meaning more than 30% of tokens in the paragraph are JD must-haves),
Then the paragraph is flagged as a `keyword_dump_paragraph` and the verdict for the package is `fail`.

Given any paragraph in the tailored output,
When the detector finds a comma-separated run of `keyword_stuffing.comma_run_min_tokens` or more consecutive JD must-have keywords (default: `4`) — that is, a sequence like `"TypeScript, Node, Kubernetes, GraphQL, Postgres"` where the items between commas are all must-have keywords from the JD,
Then the run is flagged as a `comma_run_violation` and the verdict for the package is `fail`.

Given `config.yaml` does not specify the placement thresholds,
When the check runs,
Then the defaults are `dump_paragraph_min_tokens: 15`, `dump_paragraph_max_keyword_ratio: 0.30`, and `comma_run_min_tokens: 4`, and all three are documented in the checked-in `config.yaml.example`.

Given the placement detector finds one or more violations,
When the pipeline writes per-application metadata,
Then `./out/<slug>/package.drift.json` under the `keyword_stuffing` object contains a `dump_paragraph_locations[]` array, each entry with fields `artifact` (filename), `paragraph_index` (zero-based, after heading/list filtering), `kind` (one of `keyword_dump_paragraph` or `comma_run_violation`), `keyword_ratio` (for dump paragraphs, omitted for comma runs), `matched_keywords[]`, and `excerpt` (first 120 characters of the offending paragraph or run).

Given placement detection runs alongside the density check from Story 5.1,
When either check fails, the overall `keyword_stuffing.verdict` is `"fail"`,
Then a package that fails only placement (with all densities under threshold) is still held, and a package that fails only density (with no dump paragraphs) is still held — the two checks are OR-ed into the verdict, not AND-ed.

Given the dump-paragraph detector,
When it processes paragraphs containing only markdown list items (e.g. a bulleted skills list where each bullet is one keyword),
Then bullet-list blocks are still subject to the comma-run rule across the flattened items, because a five-bullet skills list of pure JD keywords is the same anti-pattern as a comma-separated dump-paragraph and must be caught.

Given the detector runs end-to-end,
When invoked on tailored artifacts,
Then it uses only string operations (tokenization, set membership, regex over comma-separated runs) and paragraph-position counting — no LLM call is made by this check.

---

### Story 5.3: Drift metadata writes and per-channel threshold overrides

As the solo developer,
I want the keyword-stuffing verdict and all violation details persisted into the same `package.drift.json` sidecar that Epics 3 and 4 already write to, with conservative defaults that can be overridden per channel in `config.yaml`,
so that (a) Epic 6's held-queue and override commands can read one structured file to surface failure reasons, and (b) Upwork proposals — which legitimately repeat JD phrasing because client screening questions force it — don't get drowned in false-positive holds without me being able to loosen the thresholds for that channel only.

**Acceptance Criteria**

Given a pipeline run on any artifact set (CV+cover-letter, Upwork proposal, or both),
When the keyword-stuffing check completes (whether pass or fail),
Then `./out/<slug>/package.drift.json` contains a top-level `keyword_stuffing` object alongside the `fabrication` (Epic 3) and `content_loss` (Epic 4) objects, with required keys `verdict` (`"pass"` or `"fail"`), `density_violations[]`, `dump_paragraph_locations[]`, `thresholds_applied` (the resolved threshold values used for this run), and `channel` (the JD's classified source board, e.g. `"upwork"`, `"linkedin"`, `"ojph"`, `"other"`).

Given `config.yaml` has a top-level `keyword_stuffing` block,
When the pipeline resolves thresholds for a run,
Then the global defaults are read from `keyword_stuffing.max_density_pct`, `keyword_stuffing.max_repetitions_per_artifact`, `keyword_stuffing.dump_paragraph_min_tokens`, `keyword_stuffing.dump_paragraph_max_keyword_ratio`, and `keyword_stuffing.comma_run_min_tokens`.

Given `config.yaml` has a `keyword_stuffing.channels.<board>` sub-block (e.g. `keyword_stuffing.channels.upwork`),
When the pipeline resolves thresholds for a run whose JD was classified as that board,
Then per-channel values shallow-merge over the global defaults — any key present in the channel block overrides the global value, any key absent falls back to the global default — and the resolved set is recorded in `thresholds_applied` in `package.drift.json`.

Given the package fails any drift check (fabrication from Epic 3, content-loss from Epic 4, or keyword-stuffing from this epic),
When the pipeline finishes,
Then the package is held per the established Epic 3 pattern: artifacts are still written to `./out/<slug>/`, `package.drift.json` is written with `verdict: "fail"` for the failing check(s), and no notification is sent (Epic 6 owns the notification side; this story only owns the metadata write contract).

Given the pipeline exit code contract,
When the keyword-stuffing check returns `fail` and is the only failing check,
Then the pipeline process exits with a non-zero status code consistent with the held-package convention established by Epic 3 (one exit code for "drift fail, package held," matching the existing convention — no new exit code introduced by this story).

Given `config.yaml.example` is checked into the repo,
When a new user copies it to `config.yaml`,
Then it documents the global `keyword_stuffing` defaults from Stories 5.1 and 5.2 verbatim, and includes a commented-out `channels.upwork` block showing how to loosen `max_repetitions_per_artifact` and `dump_paragraph_max_keyword_ratio` for that channel — without hard-coding looser Upwork values in the shipped defaults.

Given a previous pipeline run wrote `package.drift.json` for a slug,
When that slug is re-run (override or replay),
Then the file is overwritten, not merged — there is one authoritative `package.drift.json` per slug per latest run, and the freshness contract from FR4 (canonical CV read fresh each run) is mirrored for drift metadata.

### Story 5.4: Drift Check Diagnostics surface — keyword-stuffing section

As a solo developer (the author),
I want the drift diagnostics page extended with a keyword-stuffing section that shows per-keyword density bars against configured thresholds and flags offending sections,
So that the final drift dimension is legible in the browser — completing the diagnostics surface that Stories 3.5 and 4.4 built incrementally.

**Context.** Was the keyword-stuffing portion of Epic 8.5 under the prior hybrid architecture. Folded into Epic 5 per the 2026-05-23 pivot (`DECISIONS.md` §6) so the keyword-stuffing check ships as one vertical slice — logic + UI together. With this story, `design_guidelines/stitch-export/html/05-drift-check-diagnostics.html` is fully realized.

**Acceptance Criteria:**

**Given** Stories 5.1–5.3 (density measurement, placement detection, drift metadata writes + per-channel overrides) are done and Stories 3.5 + 4.4 (drift diagnostics surface with fabrication + content-loss sections) are live,
**When** the frontend requests `GET /api/package/<slug>/drift` and the response includes a `keyword_stuffing` block,
**Then** the page at `/packages/<slug>/drift` renders a populated keyword-stuffing section replacing the placeholder Story 3.5 shipped,
**And** each measured keyword is rendered as a density bar against its configured per-section threshold (from Story 5.3's `config_snapshot` — global defaults or per-channel overrides),
**And** sections flagged as dump-paragraphs (Story 5.2) are listed with their location in the tailored output,
**And** the section matches the layout of the keyword-stuffing portion of `design_guidelines/stitch-export/html/05-drift-check-diagnostics.html` (FR49, keyword-stuffing slice — completes FR49 fully).

**Given** the package passed the keyword-stuffing check,
**When** the section renders,
**Then** an empty pass state is shown matching the design,
**And** the rest of the diagnostics page (fabrication, content-loss, sidebar) is unaffected.

**Given** the package was run on a channel with per-channel overrides (Story 5.3),
**When** the keyword-stuffing section renders,
**Then** the effective threshold for each keyword is shown, and a small "(override applied for channel: <board>)" label appears next to each keyword whose threshold differs from the global default — so the author can see threshold drift between runs without grepping config.

## Epic 6: Notifications & Held-Package Queue

The user's daily-driver surface and the moment of truth for the pipeline. When a package passes all three drift checks (Epics 3–5), the system POSTs to a configured Google Chat incoming webhook (FR31) with a one-line fit summary, the source board, and the path to the staged markdown package (FR32). When any drift check fails, the package is held — silently, no notification — and the markdown artifacts are still written to disk so the author can read them (FR33, FR34). The web surface closes the loop: the **Dashboard** (Story 6.3 / Stitch screen 01, FR46) lists held packages with their failure reasons (`GET /api/queue` / FR35) and composes Story 2.12's stats card and the recent-verdicts table into the home page; the **Approve action** (Story 6.4 / `POST /api/override/<slug>` / FR36, FR51) releases a held package, with the override logged as structured metadata in the per-application file (boolean plus reason, not free-text — per PRD PO Assumptions) so override-rate becomes a measurable signal. Single channel only — email digest and push notifications are explicitly v2 per the brief. With Epic 6 complete, v1 is functionally usable end-to-end via the browser, which is the brief's definition of the MVP being real.

### Story 6.1: GChat webhook notification on pass

As the solo developer building Job Hunter, I want a Google Chat ping every time a package clears all three drift checks, so my daily-driver surface is "check GChat, open the file, edit, submit" and I never have to poll a directory to find what's ready.

**Acceptance Criteria**

AC1 — Webhook URL is loaded from `.env`, never committed
- **Given** the project repository
- **When** I inspect `.env.example` and `.gitignore`
- **Then** `.env.example` contains a placeholder line `GCHAT_WEBHOOK_URL=https://chat.googleapis.com/v1/spaces/...` with no real URL
- **And** `.gitignore` contains `.env`
- **And** `git check-ignore .env` exits with code `0` confirming `.env` is ignored
- **And** the runtime reads `GCHAT_WEBHOOK_URL` from `.env` via the existing config loader (no hardcoded URL anywhere in source)

AC2 — Pass verdict triggers a single webhook POST with the contracted payload
- **Given** a JD has been run through the pipeline and all three drift checks (fabrication, content-loss, keyword-stuffing) have verdict `pass` in the per-application metadata sidecar
- **When** the pipeline reaches the notification stage
- **Then** exactly one HTTPS POST is made to `GCHAT_WEBHOOK_URL`
- **And** the JSON payload contains: a one-line fit summary, the JD title, the source board (`upwork` | `onlinejobs_ph` | `linkedin` | `other`), the absolute path to `./out/<slug>/`, the total cost-to-produce in USD from the metadata sidecar, and a `file://` link to the staged package directory
- **And** the HTTP response is `2xx`
- **And** the pipeline exit code is `0`

AC3 — Webhook failure does not lose the package or block the pipeline
- **Given** a passing package and a `GCHAT_WEBHOOK_URL` that is temporarily unreachable (e.g. HTTP 502, network timeout, DNS failure)
- **When** the notification stage runs
- **Then** the POST is retried with exponential backoff up to 3 attempts (delays approximately 1s, 2s, 4s)
- **And** if all retries fail, the failure is logged to stderr with the response status (or error class) and the package path
- **And** the staged artifacts under `./out/<slug>/` remain untouched on disk
- **And** the pipeline exits with code `0` because the package itself succeeded (notification failure is non-fatal)
- **And** the metadata sidecar records `notification.status: "delivery_failed"` so I can re-notify or inspect later

AC4 — Notification points to a file I open; the tool never auto-submits
- **Given** any passing package
- **When** I receive the GChat message
- **Then** the message body contains the local file path and an `file://` or `vscode://` link that opens the package directory in my editor
- **And** the payload contains no submission URL, no board-side API call, no Upwork/LinkedIn endpoint reference
- **And** the message text makes it explicit the human still needs to review and submit (e.g. "Ready for your review — submit when satisfied")

---

### Story 6.2: Silent hold on any drift-check fail

As the solo developer, I want failing packages held quietly on disk with no GChat ping, so my notification channel stays high-signal and I check the held queue on my own schedule when I'm ready for triage.

**Acceptance Criteria**

AC1 — Fail verdict on any drift check skips the webhook entirely
- **Given** a JD has been run through the pipeline and at least one drift check (fabrication, content-loss, or keyword-stuffing) has verdict `fail` in the per-application metadata sidecar
- **When** the pipeline reaches the notification stage
- **Then** zero HTTPS POSTs are made to `GCHAT_WEBHOOK_URL`
- **And** the pipeline exit code is `2` (held), distinct from `0` (passed) and `1` (pipeline error)
- **And** no message of any kind appears in the configured Google Chat space

AC2 — Held packages land in `./out/_held/<slug>/` with full artifacts and the drift report
- **Given** a failing package with slug `acme-senior-backend-2026-05-19`
- **When** the hold stage runs
- **Then** the directory `./out/_held/acme-senior-backend-2026-05-19/` exists
- **And** it contains every tailored markdown artifact produced before the fail (cv.md, cover-letter.md or proposal.md, etc.) so I can read what was generated
- **And** it contains the per-application metadata sidecar (JSON or YAML) with `drift_verdicts` populated for all three checks (each one `pass` or `fail` with reasons per Epics 3–5)
- **And** it contains a human-readable `drift-report.md` summarizing which check failed, the offending claims/entries/keywords, and their locations in the tailored output

AC3 — Pass/fail contract is documented and enforced
- **Given** the codebase
- **When** I read the notification module's docstring (or its config schema)
- **Then** the contract is stated explicitly: `pass → notify on GChat; fail → hold quietly under ./out/_held/<slug>/, no notification`
- **And** the same contract is reflected in a one-paragraph note in `config.yaml` near the notification settings
- **And** there is no code path that posts to the webhook when any drift verdict is `fail`

AC4 — Held packages survive a crash and are not double-staged
- **Given** the pipeline is mid-write to `./out/_held/<slug>/` when the process is killed (`kill -9`)
- **When** I re-run the pipeline on the same JD
- **Then** the new run detects the existing slug directory and either resumes cleanly or writes to a sibling directory (`<slug>-1/`) — it does not silently overwrite the previous attempt
- **And** the held-queue listing (Story 6.3) shows the package(s) present on disk without duplication

---

### Story 6.3: Dashboard surface + queue API — held packages, recent verdicts, interview rate

As the solo developer, I want a browser Dashboard that tells me how many packages are waiting, what the most recent verdicts were, and where my rolling interview-conversion rate sits, so I have a single page to answer "what does Job Hunter want from me right now."

**Context.** Reframed 2026-05-23 from `jobhunter status` CLI to web-only (`DECISIONS.md` §6). This story owns the **Dashboard surface** — Stitch screen 01 (`design_guidelines/stitch-export/html/01-dashboard.html`) — and the backend queue API. It composes with Story 2.12's stats card (KPIs) and Story 6.4's Approve action (override) into the single home page of the app.

**Acceptance Criteria**

AC1 — `GET /api/queue` returns held + recent state from disk
- **Given** the FastAPI scaffold from Story 1.6 is in place
- **When** the frontend issues `GET /api/queue`
- **Then** the backend reads `./out/_held/` and the per-application metadata sidecars directly (no database — `DECISIONS.md` §6)
- **And** the response body is a JSON document with `held_count` (integer count of directories under `./out/_held/`), `recent` (array of the last 10 packages held or passed, most recent first; each element has `{slug, source_board, verdict, timestamp}` where `verdict` is one of `pass`, `held:fabrication`, `held:content-loss`, `held:keyword-stuffing`)
- **And** the endpoint is read-only: no file under `./out/`, `./out/_held/`, or `./out/_overridden/` is created, modified, moved, or deleted by any path serving this request

AC2 — Dashboard surface renders the Stitch dashboard layout
- **Given** Story 6.3 is shipped and the user opens `http://127.0.0.1:8765/` in a browser
- **When** the page renders
- **Then** the layout matches `design_guidelines/stitch-export/html/01-dashboard.html` (sidebar nav + status-count cards + recent-packages table)
- **And** all design tokens (colors, typography scale, spacing, border-radius) come from the Tailwind config built off `design_guidelines/stitch-export/design.md` — no ad-hoc hex codes or pixel values (FR46)
- **And** the held-count card and the recent-packages table are populated from `GET /api/queue`
- **And** Story 2.12's stats card is mounted in the position shown by the Stitch mockup (already shipped — Story 6.3 only composes it onto this surface)

AC3 — Empty queue renders an empty state
- **Given** `./out/_held/` does not exist or is empty
- **When** the user opens `/`
- **Then** the held-count card shows `0` and the recent-packages table renders an empty state matching the design (no broken layout, no JS error)
- **And** a one-line hint reads "No applications yet — paste a JD on the home surface to start" (link points to the JD-paste textarea from Story 1.6 / Story 2.14)

AC4 — Clicking a held package navigates to the package detail surface
- **Given** the recent-packages table is populated
- **When** the user clicks a held package row
- **Then** the SPA navigates to `/packages/<slug>` (the JD Pipeline & Tailoring surface from Story 2.14)
- **And** the URL is bookmarkable and reload-safe

---

### Story 6.4: Override API + Approve action — release a held package with structured metadata

As the solo developer, I want an "Approve" action on the Dashboard (and the JD Pipeline detail page) that lets me release a held package only after I have explicitly stated my reason AND acknowledged the drift report, so override becomes a measurable signal (not a free-text shrug) and I can tune drift thresholds later based on real override patterns.

**Context.** Reframed 2026-05-23 from `jobhunter override <slug>` CLI to web-only (`DECISIONS.md` §6). This story ships the `POST /api/override/<slug>` endpoint that the Dashboard "Approve" button and the JD Pipeline detail page both call. The validation contract (reason + ack-drift, both required) survives the pivot — the difference is the entrypoint.

**Acceptance Criteria**

AC1 — Override endpoint requires both structured fields; defaults are not allowed
- **Given** a held package at `./out/_held/acme-senior-backend-2026-05-19/`
- **When** the frontend POSTs to `/api/override/acme-senior-backend-2026-05-19` with an empty body or missing fields
- **Then** the endpoint returns `422 Unprocessable Entity` with a JSON body naming both required fields: `reason` (non-empty string) and `ack_drift` (strict boolean)
- **And** the held package is not moved
- **And** if only one of the two fields is present, the response still returns `422` and names the missing field

AC2 — `reason` is non-empty; `ack_drift` is strict boolean
- **Given** any held slug
- **When** the frontend POSTs `{"reason": "", "ack_drift": true}`
- **Then** the endpoint returns `422` rejecting the empty reason
- **When** the frontend POSTs `{"reason": "valid reason", "ack_drift": "maybe"}`
- **Then** the endpoint returns `422` and names `true` and `false` as the only accepted values for `ack_drift`
- **And** the JSON-body boolean is the only accepted form (no string coercion)

AC3 — A valid override moves the package and stamps structured metadata
- **Given** a held package at `./out/_held/acme-senior-backend-2026-05-19/`
- **When** the frontend POSTs `{"reason": "drift was on adjacent-tool phrasing I actually know", "ack_drift": true}` to `/api/override/acme-senior-backend-2026-05-19`
- **Then** the endpoint returns `200 OK` with a JSON body confirming `{"slug": "...", "overridden": true, "moved_to": "./out/_overridden/..."}`
- **And** the directory `./out/_held/acme-senior-backend-2026-05-19/` no longer exists
- **And** the directory `./out/_overridden/acme-senior-backend-2026-05-19/` exists with all original artifacts intact
- **And** the metadata sidecar inside the overridden package contains a structured `override` block with at minimum: `override.applied: true`, `override.reason: "<the string>"`, `override.ack_drift: true|false`, `override.timestamp: <ISO8601>`
- **And** the `override` block is structured fields, not a free-text comment dump — `GET /api/stats` (Story 2.12) can aggregate override-rate without re-parsing prose

AC4 — Override never posts to GChat and never submits anywhere
- **Given** a valid override request
- **When** the handler runs
- **Then** zero HTTPS POSTs are made to `GCHAT_WEBHOOK_URL`
- **And** zero requests are made to any Upwork, LinkedIn, or OnlineJobs.ph endpoint (FR44 / FR51 — structurally enforced)
- **And** the response body includes a one-line note reminding the user that the package is ready for manual review and submission (e.g. `"Overridden. Open ./out/_overridden/<slug>/ and submit when ready."`)
- **And** a unit test asserts that this handler's call graph contains zero `httpx`/`requests`/`urllib` calls to non-loopback hosts

AC5 — Unknown slug returns 404
- **Given** there is no directory `./out/_held/does-not-exist/`
- **When** the frontend POSTs to `/api/override/does-not-exist` with a valid body
- **Then** the endpoint returns `404 Not Found`
- **And** the response body names the missing slug and points to `GET /api/queue` to list available held packages
- **And** no directories are created or modified

AC6 — Approve action wires from both Dashboard and JD Pipeline detail
- **Given** Stories 6.3 (Dashboard surface) and 2.14 (JD Pipeline detail) are shipped and a held package exists
- **When** the user clicks "Approve" on either surface
- **Then** a confirmation modal asks for `reason` (text field) and `ack_drift` (checkbox the user must tick)
- **And** clicking Submit POSTs to `/api/override/<slug>` with the structured body
- **And** on `200` the UI optimistically removes the package from the held list and surfaces the success state
- **And** on `404` or `422` the modal stays open and shows the structured error inline

---

### Story 6.5: Held-package TTL with auto-discard

As the solo developer, I want held packages older than a configurable TTL to be auto-discarded with a log entry, so the held queue does not rot into hundreds of stale directories I will never triage.

**Acceptance Criteria**

AC1 — TTL is configurable in `config.yaml`, defaulting to 7 days
- **Given** the project's `config.yaml`
- **When** I inspect the notification / queue section
- **Then** there is a key `held_package_ttl_days` with a default value of `7`
- **And** the value is read at runtime — changing it does not require a code change
- **And** setting it to `0` disables auto-discard entirely (the queue is kept forever)

AC2 — Discard sweep runs on each pipeline invocation and is idempotent
- **Given** the held queue contains `./out/_held/old-slug/` whose metadata sidecar `created_at` is 8 days ago, and `./out/_held/fresh-slug/` whose `created_at` is 1 day ago, and `held_package_ttl_days: 7`
- **When** the next pipeline run starts (any handler that touches the queue, e.g. `POST /api/paste` or a scheduled flow ingest)
- **Then** `./out/_held/old-slug/` is removed from disk
- **And** `./out/_held/fresh-slug/` is untouched
- **And** running the same sweep again immediately produces no further changes (idempotent)

AC3 — Each discard is logged with enough detail for after-the-fact audit
- **Given** a discard sweep that removes one or more packages
- **When** the sweep completes
- **Then** for each discarded slug a line is appended to `./out/_discarded.log` (or equivalent durable log) containing at minimum: ISO8601 timestamp, slug, source board, drift-fail reason from the sidecar, and the `created_at` of the discarded package
- **And** the log file is plain text or newline-delimited JSON so I can grep it later
- **And** no notification fires for the discard (silent — matches the silent-hold contract from Story 6.2)

AC4 — Overridden and passed packages are never auto-discarded
- **Given** packages under `./out/_overridden/<slug>/` and `./out/<slug>/` that are older than the TTL
- **When** the discard sweep runs
- **Then** none of those directories are touched
- **And** only `./out/_held/<slug>/` directories are subject to the TTL

## Epic 7: Automated Job Ingestion (n8n Scheduled Flows)

The second front door. Sequenced last in v1 per the non-negotiable build order, because the ingest layer is the most fragile and ToS-sensitive part of the system and the rest of v1 must work without it. Hosting-agnostic flows (n8n self-hosted, n8n cloud, or Make.com / equivalent — author's call at build time) poll three sources and POST each JD to the same internal `POST /ingest` endpoint (FR7, from Epic 2) that the human CLI already uses. Three source flows: Upwork search results (FR8), OnlineJobs.ph listings (FR9), and the user's own LinkedIn Job Alert email inbox (FR10) — LinkedIn is parsed from official Job Alert emails only, never crawled, which is the deliberate design that keeps the author's income-bearing LinkedIn account safe. The flows live in n8n's own state, not in the core repo; the only contract between n8n and the core is the inbound JD endpoint with its shared-token auth (NFR18, NFR19 — already standing from Epic 2). If a source breaks tomorrow, paste mode still works, which is the safety net for income-critical use.

### Story 7.1: Endpoint integration and shared-token auth for n8n flows

As the solo developer building Job Hunter,
I want every n8n flow in this epic to POST JDs to my core pipeline's internal `POST /ingest` endpoint using a single shared-secret bearer token loaded from `.env`,
so that the human CLI and all scheduled flows go through one contract, one auth check, and one body shape — and so I have a hosting-agnostic baseline I can reuse for the three channel flows that follow.

**Acceptance Criteria**

**AC1 — Shared `.env` token convention is documented and a sample flow can authenticate**

- Given my core pipeline (from Epic 2) is running locally and accepts authenticated calls at `POST /ingest`,
- And the shared-secret token is stored in `.env` under the key `INGEST_SHARED_TOKEN` and `.env` is `.gitignore`'d (FR41 already in force),
- When I configure an n8n `HTTP Request` node with header `Authorization: Bearer ${INGEST_SHARED_TOKEN}` and `Content-Type: application/json`,
- Then a minimal hand-fired n8n test execution against `POST /ingest` returns `HTTP 200` (or `202`) for a well-formed payload,
- And the same call without the bearer header returns `HTTP 401`,
- And the token value never appears in the n8n flow JSON export I check into version control.

**AC2 — Canonical JSON contract for `/ingest` is fixed and documented**

- Given the n8n flows are channel adapters and must all post the same body shape,
- When any flow in this epic POSTs to `/ingest`,
- Then the JSON body contains exactly these top-level fields: `source` (one of `"upwork"`, `"onlinejobs_ph"`, `"linkedin_email"`), `jd_text` (the raw JD body as plain text/markdown), `url` (the canonical job-posting URL or the email's job-link URL), and `discovered_at` (ISO-8601 UTC timestamp set by the n8n flow at fetch time),
- And the contract is captured in a short reference doc (or README block in the repo) that lives next to the endpoint code from Epic 2 so future channel flows can copy it,
- And a malformed payload (missing `source` or `jd_text`) returns `HTTP 400` with a machine-readable error key.

**AC3 — FR11 is explicitly named: no n8n flow in this epic may log into a job board**

- Given FR11 forbids logging into the user's Upwork, OnlineJobs.ph, or LinkedIn accounts on the user's behalf,
- When I design any n8n flow in this epic (Stories 7.2, 7.3, 7.4),
- Then no flow contains credentials, OAuth tokens, session cookies, or any other login material for Upwork, LinkedIn, or OnlineJobs.ph,
- And no flow uses a browser-automation node (Puppeteer, Selenium, headless Chromium) against any of those three sites,
- And the LinkedIn ingest path is email-parse only (Story 7.4) — never a site fetch against `linkedin.com`,
- And this FR11 rule is written verbatim into a comment block at the top of every flow export in the repo's `n8n/` reference folder.

**AC4 — Hosting-agnostic: the same flow JSON runs under self-hosted n8n and n8n cloud**

- Given the PRD defers the n8n hosting decision (self-hosted vs n8n cloud vs Make.com / equivalent) to me at build time,
- When I import the reference flow JSON into a fresh self-hosted n8n instance,
- Then it runs without modification beyond setting environment variables (`INGEST_SHARED_TOKEN`, `INGEST_BASE_URL`),
- And when I import the same JSON into n8n cloud, the same is true,
- And no flow node depends on filesystem paths, local-only binaries, or self-hosted-only features (e.g. `Execute Command` node) — only HTTP, IMAP Email Read, Cron, and standard transform nodes are used.

---

### Story 7.2: Upwork scheduled search flow

As the solo developer,
I want a scheduled n8n flow that polls Upwork's public search results (RSS or public listing pages, no login) on a configurable cron, dedupes by URL hash, and POSTs each new JD to my `/ingest` endpoint using the shared-secret contract from Story 7.1,
so that Upwork JDs matching my saved search land in the held-package queue overnight without me logging in or running any crawler against an authenticated session.

**Acceptance Criteria**

**AC1 — Cron-triggered polling against Upwork's public RSS / public listing pages only**

- Given Upwork exposes public search results via RSS (and public listing pages reachable without login),
- And FR11 (reinforced from Story 7.1) forbids logging into Upwork,
- When the n8n `Cron` trigger node fires on its configured schedule (default `0 */6 * * *` — every 6 hours, configurable per flow parameter),
- Then the flow fetches from the public Upwork RSS / public listing URL via an `HTTP Request` node with no Upwork session cookie, no Upwork OAuth token, and no Upwork login credentials,
- And the search query (e.g. `"remote senior backend"`) is a configurable flow-level parameter so I can edit it without touching node internals,
- And if the public source is unreachable or returns non-200, the flow logs the error and exits cleanly without crashing the n8n instance.

**AC2 — Per-URL dedup so the same JD is not re-ingested across runs**

- Given Upwork search results overlap across polling intervals,
- When the flow processes each item in the fetched feed,
- Then each item's canonical URL is hashed (SHA-256 of the normalized URL) and checked against a persisted dedup store — either an n8n `Static Data` / `Workflow Static Data` slot, a small SQLite-backed n8n node, or a key-value store local to the n8n instance,
- And items whose URL hash already exists in the store are dropped without POSTing,
- And items whose URL hash is new are POSTed to `/ingest` and their hash recorded,
- And the dedup store survives n8n restarts (i.e. not just in-memory for the run).

**AC3 — Each new Upwork JD is POSTed to `/ingest` using the Story 7.1 contract**

- Given the contract from Story 7.1 (AC2),
- When a new (non-dedup'd) Upwork item is processed,
- Then the flow POSTs to `${INGEST_BASE_URL}/ingest` with `Authorization: Bearer ${INGEST_SHARED_TOKEN}` and JSON body `{ "source": "upwork", "jd_text": "<raw RSS description / listing body as plain text>", "url": "<canonical job URL>", "discovered_at": "<ISO-8601 UTC now>" }`,
- And `HTTP 200`/`202` from `/ingest` marks the item as successfully ingested (hash recorded),
- And `HTTP 4xx`/`5xx` from `/ingest` does NOT record the hash, so the item is retried on the next cron tick.

**AC4 — Hosting-agnostic and FR11-compliant by inspection**

- Given the flow must run under self-hosted n8n AND n8n cloud (Story 7.1 AC4),
- When I import the flow JSON into either hosting target,
- Then the only environment variables required are `INGEST_BASE_URL`, `INGEST_SHARED_TOKEN`, and `UPWORK_SEARCH_QUERY`,
- And the flow export contains no Upwork credentials, no session cookies, no OAuth blocks, and no browser-automation nodes,
- And a code-review checklist item at the top of the flow JSON re-states: "FR11: this flow MUST NOT log into Upwork. Public RSS / public listing pages only."

---

### Story 7.3: OnlineJobs.ph listings flow

As the solo developer,
I want a scheduled n8n flow that polls OnlineJobs.ph's public listings (no login) on a configurable cron, dedupes by URL hash, and POSTs each new JD to `/ingest` using the same shared-secret contract,
so that OJ.ph postings land in the held-package queue using the exact same pattern as the Upwork flow — different channel, same plumbing.

**Acceptance Criteria**

**AC1 — Cron-triggered polling against OJ.ph public listings only (FR11 reinforced)**

- Given OnlineJobs.ph exposes publicly browsable job listings without login,
- And FR11 (reinforced from Story 7.1) forbids logging into OnlineJobs.ph,
- When the n8n `Cron` trigger fires on its configured schedule (default `0 */6 * * *`, configurable per flow parameter),
- Then the flow fetches OJ.ph's public listing URL via an `HTTP Request` node with no OJ.ph session cookie and no OJ.ph login credentials,
- And the search query / category filter (e.g. `"full-stack-programming"`) is a configurable flow-level parameter,
- And if OJ.ph returns non-200 or is unreachable, the flow logs and exits cleanly.

**AC2 — Per-URL dedup using the same hashing approach as Story 7.2**

- Given the dedup pattern from Story 7.2 (AC2) is the canonical pattern for this epic,
- When the flow processes each listing in the fetched page,
- Then each listing's canonical URL is SHA-256-hashed and looked up against a persisted dedup store (same store type as Story 7.2, scoped per-flow so Upwork and OJ.ph hashes don't collide semantically),
- And already-seen hashes are dropped,
- And new hashes are POSTed and recorded,
- And the dedup store survives n8n restarts.

**AC3 — Each new OJ.ph JD is POSTed to `/ingest` using the Story 7.1 contract**

- Given the canonical JSON contract from Story 7.1 (AC2),
- When a new OJ.ph listing is processed,
- Then the flow POSTs to `${INGEST_BASE_URL}/ingest` with `Authorization: Bearer ${INGEST_SHARED_TOKEN}` and JSON body `{ "source": "onlinejobs_ph", "jd_text": "<listing body as plain text>", "url": "<canonical listing URL>", "discovered_at": "<ISO-8601 UTC now>" }`,
- And `HTTP 200`/`202` marks the listing as successfully ingested,
- And non-2xx leaves the URL hash unrecorded so the next cron tick retries.

**AC4 — Hosting-agnostic and FR11-compliant by inspection**

- Given the flow must run under self-hosted n8n AND n8n cloud (Story 7.1 AC4),
- When I import the flow JSON into either hosting target,
- Then the only environment variables required are `INGEST_BASE_URL`, `INGEST_SHARED_TOKEN`, and `OJPH_SEARCH_QUERY`,
- And the flow export contains no OJ.ph credentials, no session cookies, and no browser-automation nodes,
- And the flow JSON includes a top-of-file comment restating: "FR11: this flow MUST NOT log into OnlineJobs.ph. Public listings only."

---

### Story 7.4: LinkedIn Job Alert email parser flow

As the solo developer,
I want a scheduled n8n flow that polls a dedicated Gmail/IMAP inbox for LinkedIn Job Alert emails, extracts each job-posting link and JD snippet from the email body, dedupes by email message-id (and per-link URL hash), and POSTs each new JD to `/ingest` using the shared-secret contract,
so that LinkedIn jobs reach the held-package queue exclusively via parsing LinkedIn's own outbound Job Alert emails — and never via crawling LinkedIn.com, which would put my income-bearing LinkedIn account at risk.

**Acceptance Criteria**

**AC1 — IMAP poll against a dedicated inbox; NO LinkedIn site fetches anywhere in the flow**

- Given the brief and PRD (FR10, NFR12) require that LinkedIn ingest be email-parse only,
- And FR11 plus the no-platform-login rule from Story 7.1 explicitly forbid logging into linkedin.com,
- When the n8n `IMAP Email Read` trigger node polls the configured Gmail/IMAP inbox on its schedule (default every 15 minutes, configurable),
- Then it pulls only messages whose `From:` matches LinkedIn's Job Alert sender pattern (e.g. `jobalerts-noreply@linkedin.com`) and whose `Subject:` matches the LinkedIn Job Alert subject pattern,
- And no node in the flow makes an HTTP request to any `linkedin.com` URL (verified by inspecting the flow JSON),
- And no node holds a LinkedIn cookie, OAuth token, or password.

**AC2 — Parser handles LinkedIn's actual Job Alert email template structure**

- Given LinkedIn Job Alert emails contain multiple job-posting blocks per email, each with a job title, company, location snippet, and a tracking URL that resolves to the canonical job posting,
- When the flow parses an email body (HTML and/or plain-text part),
- Then it extracts each job block as a separate record with: the displayed job title, company, the LinkedIn job-posting URL (or its tracking URL, captured as-is — resolution happens downstream in the pipeline), and the surrounding snippet text as `jd_text`,
- And if the email contains zero parsable job blocks (e.g. template changed), the flow logs a "template-drift" warning and skips the email without crashing,
- And the parser is implemented in an n8n `Code` (Function) node or `HTML Extract` node so it's editable when LinkedIn changes the template.

**AC3 — Dual dedup: per email message-id AND per extracted job URL**

- Given the same job can appear in multiple Job Alert emails over multiple days,
- When the flow processes an email,
- Then the email's RFC 5322 `Message-ID` header is hashed and recorded so the same email is not re-parsed if re-fetched,
- And each extracted job URL is SHA-256-hashed and checked against the same kind of persisted dedup store used in Stories 7.2 / 7.3 (scoped to `linkedin_email`),
- And a job URL already seen is dropped silently without POSTing,
- And a new job URL is POSTed and its hash recorded.

**AC4 — Each new LinkedIn job is POSTed to `/ingest` using the Story 7.1 contract**

- Given the canonical JSON contract from Story 7.1 (AC2),
- When a new (non-dedup'd) job block is extracted,
- Then the flow POSTs to `${INGEST_BASE_URL}/ingest` with `Authorization: Bearer ${INGEST_SHARED_TOKEN}` and JSON body `{ "source": "linkedin_email", "jd_text": "<extracted snippet text>", "url": "<extracted job URL>", "discovered_at": "<ISO-8601 UTC of email receipt>" }`,
- And `HTTP 200`/`202` marks the job as successfully ingested,
- And non-2xx leaves the URL hash unrecorded so the next IMAP poll re-attempts.

**AC5 — Hosting-agnostic; LinkedIn-site-crawl forbidden by inspection**

- Given the flow must run under self-hosted n8n AND n8n cloud (Story 7.1 AC4),
- When I import the flow JSON into either hosting target,
- Then the only environment variables required are `INGEST_BASE_URL`, `INGEST_SHARED_TOKEN`, `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD` (Gmail app-password for the dedicated inbox), and `IMAP_PORT`,
- And a code-review checklist comment at the top of the flow JSON restates: "FR10 + FR11 + NFR12: LinkedIn ingest is email-parse ONLY. This flow MUST NOT fetch any linkedin.com URL. Site crawling is forbidden — ToS landmine and account-suspension risk against the author's income-bearing LinkedIn account.",
- And the inbox used is a dedicated Gmail account separate from the author's primary LinkedIn-registered email, so the polling credentials are isolated from anything tied to the author's LinkedIn login.

### Story 7.5: Job Alerts & Automated Scans surface

As a solo developer (the author),
I want a browser view of the n8n-flow status — last run timestamp, success/failure, count of JDs ingested per flow — so I can see whether my automated front door is healthy without SSHing into the n8n host or opening the n8n UI.

**Context.** Was Epic 8.6 under the prior hybrid architecture. Folded into Epic 7 per the 2026-05-23 pivot (`DECISIONS.md` §6) so the n8n ingest layer ships as one vertical slice — backend logic + UI surface together.

**Acceptance Criteria:**

**Given** Stories 7.1–7.4 (n8n shared-token auth + Upwork/OJ.ph/LinkedIn flows) are done and the FastAPI scaffold from Story 1.6 is in place,
**When** the frontend requests `GET /api/scans`,
**Then** the backend returns a JSON document with one entry per flow (Upwork search, OnlineJobs.ph listings, LinkedIn email parser) containing `{flow_name, last_run_timestamp, last_run_status, jds_ingested_count, last_error?}`,
**And** the backend never exposes inbox credentials, n8n auth tokens, IMAP passwords, or any value from `.env` to the frontend (only the operational telemetry).

**Given** the page is loaded at `/scans`,
**When** it renders,
**Then** the layout matches `design_guidelines/stitch-export/html/03-job-alerts-automated-scans.html`,
**And** each flow card shows last-run timestamp (relative + absolute on hover), status (pass/fail), JD count, and any error,
**And** all design tokens come from `design.md` (FR50).

**Given** a flow has never run (no n8n callbacks yet),
**When** the surface renders,
**Then** the flow card shows a "never run" empty state with a one-line hint that the n8n flow's `INGEST_BASE_URL` must point to `http://127.0.0.1:8765` for status callbacks to land.

**Given** the backend telemetry source is the per-application metadata sidecars + the n8n callback log,
**When** the endpoint runs,
**Then** no database or other persistence layer is introduced (`DECISIONS.md` §6) — telemetry is reconstructed from disk artifacts the n8n flows already produce.

