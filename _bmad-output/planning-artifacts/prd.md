---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief-job-hunter.md
  - _bmad-output/planning-artifacts/product-brief-job-hunter-distillate.md
documentCounts:
  briefs: 2
  research: 0
  brainstorming: 0
  projectDocs: 0
workflowType: 'prd'
projectType: 'greenfield'
author: 'dave'
created: '2026-05-17'
classification:
  projectType: cli_tool_plus_workflow
  domain: career_tech_personal_productivity
  complexity: medium
  projectContext: greenfield
releaseMode: phased
---

# Product Requirements Document - Job Hunter

**Author:** dave
**Date:** 2026-05-17

## Executive Summary

Job Hunter is the AI résumé tool that won't get you rejected. It is a local-first, human-gated job-application assistant that takes a job description — pasted in or pulled automatically from Upwork, OnlineJobs.ph, and LinkedIn via an n8n-style workflow — tailors a CV, cover letter, or Upwork proposal against a markdown canonical CV under version control, and then runs an automated **drift check** that verifies the output has no fabricated experience, no lost original wins, and no unnatural keyword stuffing. Only packages that pass the drift check reach the user, who reviews the staged markdown in their editor and submits the application themselves. The tool never auto-submits.

The product targets a single primary user — the author, a solo developer working nights and weekends — and is shaped so peers (freelancers, PH remote workers, Filipino Upwork contractors) can adopt it later. It is explicitly not a VC SaaS pitch. The economic posture is "cents per application on your own LLM key" against subscription incumbents at $20–$50/month, and the quality posture is "drift-checked output that survives 2026-era recruiter AI fatigue." The headline is the moat: every PRD section reinforces the drift check, because that is the only mechanism that distinguishes Job Hunter from both the keyword-stuffing auto-appliers (LazyApply, Sonara, JobRight.ai) and the manual-tailoring analyzers (Jobscan, Teal+, Huntr).

### What Makes This Special

**The drift check is the moat AND the headline.** No mainstream competitor verifies that AI-tailored output is fabrication-free, content-preserving, and keyword-natural. These are the exact failure modes that get AI résumés rejected in 2025–26: 33.5% of hiring managers claim to spot AI in under 20 seconds, 19.6% would auto-reject AI-detected applications, and 62% of employers reject AI-generated résumés that lack personalization. Job Hunter's fabrication check is structural (claim-to-source-CV traceability), not LLM-as-judge vibes, which is why it can ship with a real pass/fail in v1 instead of waiting for an eval set.

**Your account, your reputation, your submit button.** Every application is reviewed and submitted by the user. This is a feature, not a limitation: it is a quality posture (no slop reaches recruiters), a reputational shield (no LinkedIn/Upwork ToS landmine), and a legal posture (no auto-apply means no platform-ban risk of the kind that has gotten LazyApply users blacklisted).

**Markdown canonical CV is a feature decision, not a technical limitation.** The source-of-truth CV lives in markdown/YAML in version control — diffable, mergeable, and free of the parser hell that consumes resume-tool roadmaps. Refusing to ingest PDF/docx is an intentional product stance.

**Built for the boards mainstream tools ignore.** Upwork, OnlineJobs.ph, and LinkedIn are all first-class channels. The Upwork proposal is a distinct artifact type with its own prompt template, not a cover-letter variant, because Upwork is a primary income channel for the author and his peers and is structurally under-served by US-centric incumbents.

**Cents per application, not $30/month.** End-to-end target is under $0.25 per application on the user's own LLM key, against incumbent subscriptions at Jobscan ~$50/mo, Teal+ $29/mo, Huntr ~$20/mo.

## Project Classification

- **Project Type:** Local CLI tool + workflow-automation flows (n8n/Make/equivalent). No web UI in v1. Runtime is a local script the author runs from his shell; outputs are markdown files he opens in his editor.
- **Domain:** Career tech / personal productivity / applied LLM tooling. Adjacent to HR-tech but candidate-side, which sidesteps most employer-side regulatory surface (NYC LL144, EU AI Act employer obligations).
- **Complexity:** Medium. The pipeline itself is plumbing (parse → tailor → check → notify). The complexity lives in the drift checks: structural claim traceability for fabrication, semantic match thresholds for content-loss, density and placement heuristics for keyword-stuffing. None of these are research-grade, but each requires careful eval and tuning to be trustworthy.
- **Project Context:** Greenfield. No existing code; product brief plus distillate are the only inputs. Build budget is solo nights/weekends, week-1 walking-skeleton constraint is hard.

## Success Criteria

### User Success

The single user-success question for v1 is: **does the author keep using Job Hunter after the build phase ends?** Tool abandonment by the author is the truest negative signal a personal-first product can receive. Concretely:

- The author can take a real Upwork posting from clipboard to submission-ready package in **under 10 minutes of human review time**, down from a current baseline of ~45 minutes of manual tailoring.
- The author reviews the staged markdown package and feels it is **closer to "send" than a generic ChatGPT output** — no hallucinated skills to delete, no missing wins to add back, no obvious keyword-stuffing to soften.
- The author feels safe submitting the output: no fear of "this AI résumé just torpedoed my reputation with this recruiter."
- Peers who try the tool (informally, v1.x at earliest) get a working install on their machine within an evening and submit at least one real application from it without filing a bug against the canonical-CV format.

### Business Success

There is no business in the conventional sense — this is a personal-build that may become shareable. "Business success" here means the project earns its build cost in the author's own job-search outcomes and credibility with peers.

- **Primary metric (pre-committed): Interview conversion rate = baseline × 2 over a rolling 30-application window.** "Interview" = the candidate reached a recruiter screen or hiring-manager call.
- **Baseline measurement plan:** 2–4 weeks pre-launch of manually logging every application sent today — count, hours spent, recruiter replies, screens reached. Target n ≥ 30 baseline applications before v1 cutover so the lift comparison is meaningful and not anecdote.
- **Kill criterion:** If, after 8 weeks of real post-launch use, the screen-rate lift is < 25% over baseline, the author revisits assumptions or kills the project. No "let's tune for another quarter" — the metric is pre-committed.
- **Supporting business signal:** at least one peer in the author's PH freelancer / OnlineJobs.ph / LinkedIn circle adopts the tool of their own volition by month 6 post-v1. Not a paid customer, just genuine adoption.

### Technical Success

- **Drift check earns its keep.** Fabrication drift check catches ≥ 1 substantive issue per ~10 generated packages, measured manually over the first 30 packages. Below this rate, the check is theatre. Above ~50%, the tailoring step is too aggressive and needs to be tuned down.
- **Per-application LLM cost < $0.25 end-to-end**, including JD parse, tailoring, all three drift checks, and any retry. Verified via per-request token logging from day one.
- **Hard monthly spend cap enforced on the LLM API key** with kill-switch, so a buggy evaluator loop cannot cost more than the monthly cap overnight.
- **Walking skeleton (v0.1) exists by end of week 1.** If it does not, the concept itself is suspect and bigger features are not built.
- **Secrets in `.env`, `.gitignore`'d.** Canonical CV in markdown in version control. Local-only storage default.

### Measurable Outcomes

| Outcome | Target | Window | Source of measurement |
|---|---|---|---|
| Interview conversion rate (primary) | baseline × 2 | rolling 30-application window post-launch | Manual application log |
| Kill criterion lift | ≥ 25% over baseline | 8 weeks post-launch | Manual application log |
| Time-per-application (human review) | < 10 min | per package | Self-report timer |
| Fabrication drift catch rate | ≥ 1 issue per 10 packages | first 30 packages | Manual review of flagged claims |
| Per-application LLM cost | < $0.25 | per package end-to-end | Token logging |
| Author still using it | yes/no | 8 weeks post-launch | Self-honest answer |

**Anti-metric — explicitly NOT optimized for: applications submitted per week.** Volume is the failure mode of the competition; volume is not a goal here. A week where Job Hunter submits 8 strong applications beats a week where it submits 80 generic ones, every time.

**Confound watch:** interview-rate lift could come from selection effects (the tool surfaces higher-fit roles) rather than tailoring quality. To disentangle, the author also tracks (a) manual application-fit score before sending and (b) recruiter response rate alongside the headline screen rate.

## Product Scope

This product is delivered in phases. Phasing is in the product brief and is non-negotiable in order — the v0.1 walking skeleton must exist in week 1, and the v1 build sequence is fixed. Voice drift check and several other items are explicitly deferred to v2.

### Phase 0 (v0.1) — Walking Skeleton (Week 1)

A minimal end-to-end FastAPI app. The `jobhunter` command starts a server on `127.0.0.1:8765` that exposes `POST /api/paste`; a browser textarea (one minimal page, design-system shell only) lets the author drop in a JD, the backend tailors a markdown CV and a markdown cover letter against the canonical-CV YAML/markdown, writes them to `./out/<slug>/cv.md` and `./out/<slug>/cover-letter.md`, and surfaces the file paths in the browser. No drift check. No notifications. No queue. No tests beyond smoke. If this does not save real time on a real application in week 1, the concept is wrong and Phase 1 is not built. *(Originally framed as "a single CLI script"; revised on 2026-05-23 when the project pivoted to web-only architecture — see `DECISIONS.md` §6. The shipped Epic 1 work covers the core modules, and Story 1.6 lands the FastAPI port + minimal frontend scaffold.)*

### Phase 1 (v1) — MVP

Built in this exact order on top of Phase 0:

1. **Paste-a-JD pipeline hardening.** Structured JD parse (must-haves, nice-to-haves, tone, seniority, red flags, board-specific signals like Upwork budget bands). Canonical-CV schema decided (JSON Resume schema or minimal custom YAML). Per-artifact prompt templates wired up: traditional CV, cover letter, Upwork proposal.
2. **Upwork proposal as a first-class artifact type.** Short, conversational, length-bounded, answers client screening questions, references the JD's specific phrasing. Separate prompt template, separate output format. Treated as equal to CV+cover-letter, never as a variant.
3. **Fabrication drift check.** Every claim in the tailored CV must trace to a real entry in the source CV. Structural — string-match plus semantic-equivalence threshold on canonical-CV entries — not LLM-as-judge. This is the only check that makes output *unsendable* and ships first.
4. **Content-loss drift check.** High-impact entries from the canonical CV (flagged in the source) appear in the tailored output when the JD calls for them. Catches "the AI cut your best line."
5. **Keyword-stuffing drift check.** Density and placement of JD-derived keywords are within natural-text bounds; no keyword listed >N times per section, no dump-paragraphs. ATS-passable but not ATS-tell.
6. **Single notification channel: Google Chat webhook.** One HTTPS POST per passing package. Message includes path to staged markdown and a one-line summary of fit. No email digest, no push.
7. **Scheduled-search via n8n (or Make.com / equivalent).** n8n flows ingest Upwork search results, OnlineJobs.ph postings, and LinkedIn Job Alert emails, then POST each JD to the same paste-pipeline endpoint the human uses. LinkedIn ingest is **email-parsing of official Job Alerts only** — no site crawling.

### Phase 2 (v2 / post-MVP) — Growth

Pursued only after the author has run ≥ 30 real applications through v1, has 8 weeks of post-launch data, and the primary metric is trending positive.

- **Voice drift check.** Tailored output reads in the candidate's tone, not generic AI prose. Deferred because "voice" has no clean pass/fail, is a known tuning rabbit hole, and requires a hand-labeled eval set first.
- **Outcome learning loop.** Track which staged packages led to screens / interviews / offers and feed that back into tailoring (which phrasings convert, which JD shapes are worth more effort, which Upwork proposal angles win replies). Becomes a personal hit-rate optimizer that compounds with use — structurally impossible for generic SaaS to replicate.
- **Interview-prep handoff.** When a screen is booked, regenerate a tailored prep doc (likely questions, matching stories from the canonical CV, JD-specific talking points). Extends the pipeline one step past "submit."
- **Standalone drift-check CLI.** Ship the fabrication checker as a small standalone tool peers can run against any AI-tailored CV — including outputs from Teal, ChatGPT, Jobscan. Softer on-ramp for sharing and a credibility builder.
- **Email digest + push notifications.** Multi-channel after GChat webhook proves out as the daily-driver.
- **Peer packaging.** Install docs, sample canonical-CV templates, opinionated `.env.example`. Only after 30+ real applications by the author.

### Phase 3 (v3 / Vision) — 2–3 years out

- Optional hosted variant for non-technical users, priced to undercut existing players (cents-on-the-dollar of Jobscan/Teal), not to extract.
- Browser-extension auto-fill (not auto-submit) if the ToS landscape on Upwork/LinkedIn clarifies.
- Drift-check evaluator expansion to track the next generation of recruiter-side AI signals as they emerge.
- Multi-CV / multi-profile support (e.g. switching between "backend engineer" and "ML engineer" canonical CVs).

The core stance — quality over volume, human in the loop, no fabrication — does not change at any phase.

### Explicitly Out of Scope (v1)

- Voice drift check (v2 only, after eval set exists)
- PDF/docx canonical-CV ingest (markdown-only is a feature)
- Email digest and push notifications (GChat webhook is enough for a solo user)
- Browser auto-fill / one-click apply (ToS landmine, big build)
- Multi-CV / multi-profile support (single canonical CV in v1)
- Hosted / multi-tenant web UI with auth (local-only web UI bound to `127.0.0.1` **is** the v1 surface — see §"Web Application Surface" below; only the hosted multi-tenant variant remains v3+)
- CLI subcommand surface (`jobhunter paste/status/override/stats`) — the v1 surface is the web app; no parallel CLI is maintained (revised on 2026-05-23, see `DECISIONS.md` §6)
- Hosted SaaS billing, accounts, sign-in flows (local-only in v1)
- Packaging for non-technical peers (v2 conversation, only after 30+ real applications)

## User Journeys

Job Hunter is a single-user product in v1 — the author. There is no admin role, no support staff, no API consumer in the traditional SaaS sense. The "users" of the pipeline are the author in three distinct modes (paste, scheduled-search, review) plus the canonical CV itself as the system's source of truth that the author maintains over time. The journeys below are structured around the *occasions* the product is used, which is how solo-developer tools earn their keep.

*Note: the journey narratives below were written before the 2026-05-23 web-only pivot (see `DECISIONS.md` §6). References to `jobhunter paste`, `jobhunter status`, `jobhunter override` as CLI subcommands are obsolete — those interactions now happen in the browser. The underlying actions and the order of events are unchanged; only the entry surface flipped from terminal to browser. The FRs at §"Functional Requirements" are the load-bearing contract; the journeys here remain useful as occasion-based context.*

### Journey 1 — Primary user, happy path: Tuesday evening Upwork tailoring

**Persona.** Dave, the author. Mid-career engineer freelancing on Upwork with a day job and a side practice. Tuesday 9pm, kids asleep, one coffee in. Has a saved search of three Upwork postings he wants to apply to tonight before they get buried by morning EU bids.

**Opening scene.** Today, this is 90+ minutes of work — open each posting, re-read his CV, manually rewrite a tailored cover-and-proposal in Google Docs, double-check he didn't add "Kubernetes" because the JD said it (he hasn't touched K8s in 18 months), paste into Upwork, hit submit, do it twice more. He has skipped 3 of the 5 nights this would have happened in the past month because he was tired.

**Rising action.** He opens his terminal, runs `jobhunter paste`, drops the first Upwork JD on stdin, hits enter. The pipeline parses the JD, classifies it as an Upwork posting (board-specific signals: hourly budget, screening questions), pulls canonical-CV entries flagged with the relevant tags, generates a tailored markdown CV plus a separate Upwork-proposal artifact (short, conversational, answers the screening questions), and runs all three drift checks.

**Climax.** Fabrication drift fires. The tailored CV claims familiarity with a tool Dave has never used — the LLM picked it up from a JD bullet about adjacent tooling. The package is held back; Dave sees a GChat ping summarizing the catch. He re-runs with a tightened prompt or accepts the package minus the flagged line. Three minutes of his time, not 30.

**Resolution.** Within 25 minutes total (across three postings), all three packages are staged in `./out/`. Dave opens each `.md` in his editor, makes 1–3 manual edits per package, copies into Upwork, hits submit. He hits submit. He goes to bed. Tomorrow's metric: did any of the three lead to a reply? Logged.

**Capabilities revealed.**
- Paste-mode JD ingest from stdin
- JD parser with board-specific (Upwork) signal extraction
- Canonical CV with entry-level tags
- Per-artifact prompt templates (CV vs Upwork proposal)
- Fabrication drift check with structural traceability
- Content-loss + keyword-stuffing drift checks
- Single notification channel (GChat webhook)
- Staged markdown output the user opens locally
- Per-application token / cost logging

### Journey 2 — Primary user, scheduled discovery: Friday morning over coffee

**Persona.** Same Dave. Friday 8am. The n8n flows he set up two weeks ago have been running overnight against his saved searches on Upwork, OnlineJobs.ph, and his LinkedIn Job Alert inbox.

**Opening scene.** Three pings overnight in the Job Hunter GChat space. Each ping is one staged package: a one-line fit summary, the link/path to the staged markdown, the source channel. No noise — packages that failed drift never reached him.

**Rising action.** He opens the first package. It's a LinkedIn role (parsed from the official Job Alert email, not crawled). The tailoring captured a specific phrase from the JD that aligns with a real project he did last year — he wouldn't have spotted that fit pattern manually scrolling job boards. He edits two sentences in the cover letter for tone, then submits.

**Climax.** The second package is from OnlineJobs.ph. The tailored package looks fine, but Dave notices a red-flag the JD parser surfaced: the budget is two-thirds of his floor. He passes. The third package is a strong fit — he submits without edits.

**Resolution.** Three review-and-submits done in under 20 minutes, before his first standup. Two were postings he would never have seen in time without the scheduled search.

**Capabilities revealed.**
- n8n (or equivalent) scheduled flows posting JDs to the paste-pipeline endpoint
- Multi-channel ingest: Upwork search, OnlineJobs.ph, LinkedIn Job Alert email parsing
- Per-JD board classification + red-flag heuristics (Upwork budget bands, vague-scope detection, OJ.ph rate floors)
- GChat webhook notification with one-line fit summary and stage path
- Packages that fail drift do not notify (silent hold)

### Journey 3 — Primary user, edge case: drift check holds a package, author overrides

**Persona.** Same Dave. Sunday afternoon. A high-value posting he genuinely wants to apply to. The tailored package was flagged by the keyword-stuffing check — the JD repeated "TypeScript" 11 times and the tailored output mirrored that density.

**Opening scene.** GChat is silent. No ping. Dave opens the local Job Hunter queue manually (`jobhunter status`) and sees the held package with a `keyword-stuffing: fail` reason.

**Rising action.** He opens the staged package in his editor anyway — the artifact files are written even when drift fails. The check is right: there's a paragraph that reads like a keyword dump. He rewrites it himself in 90 seconds, marks the package `override` so the system logs the manual approval, and submits.

**Climax.** The override is logged in the per-application metadata file. Three weeks later, when Dave reviews his catch-rate stats, he can see that the keyword-stuffing check caught 8 issues across 30 applications, of which 2 he overrode manually — useful signal that the check is calibrated about right.

**Resolution.** The package is sent. The override is data, not a bug. Dave can tune the threshold later if overrides start dominating, which would mean the check is too aggressive.

**Capabilities revealed.**
- Drift checks write artifacts even on fail (the user can always read the output)
- Held-package queue listable from CLI
- Manual override path with logging
- Per-application metadata file capturing every drift-check verdict and override
- Tunable drift-check thresholds (config, not code change)

### Journey 4 — Primary user, maintenance: updating the canonical CV after a project ships

**Persona.** Same Dave. He just wrapped a 6-week consulting engagement and wants to add it to his canonical CV before the next round of applications.

**Opening scene.** He opens `canonical-cv.md` (or the YAML equivalent — schema decided at v1 build time) in his editor. It's the same file he commits to a private git repo every time he changes it. Diffable, mergeable, version-controlled.

**Rising action.** He adds a new entry under "Experience" with the role, dates, three bullet points, and the tags he uses to route entries (e.g. `node, typescript, leadership, fintech`). He commits.

**Climax.** Next time he runs `jobhunter paste` on a JD that calls for any of those tags, the new entry is in the candidate pool. No re-import, no re-parse, no PDF round-trip.

**Resolution.** This is what the markdown-canonical-CV stance buys him: zero ceremony to keep the source of truth current. Compare to the PDF/docx ingest path other tools force: re-upload, re-parse, hope the parser didn't lose section breaks.

**Capabilities revealed.**
- Canonical CV is plain markdown (or markdown+YAML frontmatter) in version control
- Canonical-CV entries carry tags used by the tailoring step
- No re-import or re-parse step exists — the tailoring pipeline reads the file fresh each run
- Markdown is the only accepted canonical-CV format (PDF/docx ingest rejected)

### Journey 5 — Peer (v1.x informal sharing): a freelancer friend tries the tool

**Persona.** A Filipino Upwork freelancer in Dave's circle, technical enough to clone a repo and run a CLI. Has heard Dave talking about his hit rate going up.

**Opening scene.** Dave shares the repo (private at first). The friend clones, copies `.env.example` to `.env`, drops in their LLM API key, replaces `canonical-cv.md` with their own, and runs `jobhunter paste` on a real Upwork JD that night.

**Rising action.** Their first run produces a tailored package that catches a fabrication on the first try — the LLM added a framework the friend hadn't used. They are surprised, in a good way. They had been about to submit a ChatGPT-tailored version of the same posting with that exact line in it.

**Climax.** The friend submits the corrected package. Two weeks later, they tell Dave they got a reply.

**Resolution.** This is v1.x territory at the earliest, and it requires Dave to have hit ≥ 30 of his own applications first. But the moment described above is the proof point for the "shareable with peers" v2 conversation. No packaging effort is built into v1 for this.

**Capabilities revealed (v1, used unmodified):**
- `.env`-based config + `.gitignore`'d secrets
- Canonical CV is a single file the new user can swap in
- LLM provider is configurable per-user (API key in their env)
- No accounts, no auth, no SaaS surface — the tool runs on their machine

### Journey Requirements Summary

The journeys reveal seven capability clusters that the FR section turns into testable requirements:

1. **JD ingest** — paste mode (always available) + scheduled mode (n8n/equivalent) with multi-source ingest (Upwork, OnlineJobs.ph, LinkedIn-email)
2. **JD parsing** — structured extraction including board-specific signals and red flags
3. **Canonical CV** — markdown/YAML source of truth, version-controlled, tag-routable, no PDF/docx
4. **Tailoring** — per-artifact prompt templates (CV, cover letter, Upwork proposal as distinct first-class types)
5. **Drift check** — fabrication (v1), content-loss (v1), keyword-stuffing (v1); voice (v2)
6. **Notification + queue** — GChat webhook on pass, silent hold on fail, listable queue, manual override path
7. **Local outputs + observability** — markdown artifacts in `./out/`, per-application metadata + drift verdicts + cost logs, monthly cost cap

## Domain-Specific Requirements

The domain is **candidate-side career tech / applied LLM tooling** for a personal-use solo build that may later be shared informally. This is medium-complexity: there are real legal, ToS, and PII concerns, but the candidate-side stance sidesteps most of the heavy employer-side regulatory surface.

### Compliance & Regulatory

- **No employer-side AI hiring law exposure (v1).** NYC LL144, EU AI Act Annex III high-risk hiring obligations, and similar employer-side rules attach to *employers* using AI in hiring decisions. Job Hunter is candidate-side; the user is the candidate using AI to author their own application. These rules are not in v1 scope. *If* a hosted/multi-tenant variant is ever built (v3), this assumption must be revisited because hosting candidate AI tooling at scale may shift the analysis under some jurisdictions.
- **GDPR / CCPA.** The only personal data processed is the author's own — his canonical CV, his application history. Local-first storage default. No third-party data sharing. If a hosted variant is ever built, full compliance review required.
- **Platform ToS — Upwork, LinkedIn, OnlineJobs.ph.** Job Hunter never auto-submits and never logs into the user's platform accounts on the user's behalf. Scheduled-search flows in n8n run against publicly-visible search results (Upwork, OJ.ph) and against the user's own *email inbox* for LinkedIn Job Alerts — not against logged-in LinkedIn sessions. This is the deliberate design that keeps the income-bearing Upwork account safe.

### Technical Constraints

- **PII handling.** Canonical CV, parsed JDs, and tailored artifacts contain the author's PII and may contain client-confidential info from JDs (NDA-shaped postings, client names in OJ.ph posts). Mitigations: prefer LLM providers with no-training data-handling terms; redact identifiable client identifiers in JDs before sending upstream where feasible; default to local-only storage.
- **API key security.** All LLM provider keys and webhook URLs live in `.env`. `.env` is `.gitignore`'d. Sample `.env.example` checked in with placeholder values only.
- **Cost runaway protection.** Monthly hard spend cap on the LLM API key (configured at the provider portal, not just in code). Per-request token logging from day one. Per-application cost is a tracked KPI ($0.25 target).
- **Local-first runtime.** No hosted infra in v1. The author runs the CLI locally. The n8n instance is either self-hosted or runs on the author's preferred workflow-automation provider — his call, both work — but is *not* a hosted Job Hunter service.

### Integration Requirements

- **Outbound:** one LLM provider (Anthropic, OpenAI, or local — decided at v1 build time based on cost/quality of fabrication-check tracing). One outbound webhook (Google Chat).
- **Inbound (scheduled mode):** Upwork search ingest (via n8n flow scraping publicly visible results or via Upwork's RSS where available); OnlineJobs.ph ingest (n8n flow against public listings); LinkedIn Job Alert email ingest (n8n parsing of forwarded or polled Gmail/IMAP).
- **Internal interface:** the scheduled flows POST JDs to the same paste-pipeline endpoint the human uses interactively. One pipeline, two front doors.

### Risk Mitigations

| Risk | Mitigation |
|---|---|
| Platform ToS / account suspension | Paste-mode always available; never auto-submit; n8n flows isolated from the author's logged-in accounts; LinkedIn = email parse, not site crawl |
| Client-confidential JD content through third-party LLM | Prefer no-training providers; redact client identifiers where feasible; local-only storage default |
| LLM-as-judge unreliability for drift | Fabrication check is structural (claim-to-source-CV traceability), not LLM-as-judge; subjective checks (voice) deferred to v2 with eval set |
| Cost runaway from buggy evaluator loop | Hard monthly cap on API key + per-request token logging from day one + per-app cost KPI |
| Confounded success metric | Track manual fit-score and recruiter response rate alongside headline screen rate |
| Scope creep on solo build | v0.1 walking skeleton in week 1; "shareable" is v2 only; voice/PDF/web-UI explicitly cut |

## Innovation & Novel Patterns

### Detected Innovation Areas

Job Hunter is not a research project — every constituent technology (LLM-based tailoring, n8n flows, GChat webhooks, markdown CVs) is commodity in 2026. The innovation is in the *combination* and *posture*, not in any single component.

- **Structural fabrication drift check.** Mainstream AI-résumé tools either (a) don't check for fabrication at all (auto-appliers) or (b) check by re-prompting an LLM to grade the output (LLM-as-judge, which has the same hallucination class as the generation step). Job Hunter's fabrication check is *structural*: every claim in the tailored output must trace to a real entry in the canonical CV via string-match plus a semantic-equivalence threshold on canonical-CV entries. This is not an LLM grading another LLM; it is a deterministic-ish check anchored in a source-of-truth file the user maintains. As far as the author knows, no shipping competitor frames the check this way.
- **First-class Upwork proposal as a distinct artifact type.** Every other tool the author has used treats Upwork proposals as a "cover letter for Upwork." Upwork proposals are different: short, conversational, length-bounded, answer screening questions, reference the JD's specific phrasing. Treating them as a separate artifact with their own prompt template (not a CV variant) is a structural choice that lets the tool actually serve Upwork-primary users — which is most of the author's peer audience.
- **Markdown canonical CV as feature, not limitation.** The "we don't ingest PDFs" stance is rare among CV tools because PDF ingest is table-stakes in the broader market. For a personal/peer build, the inversion holds: markdown-only buys diffable history, mergeable edits, zero parser hell, and version-control-native workflows that engineers and technical freelancers already trust.
- **The pipeline has two front doors but one body.** Paste-mode and scheduled-search-mode both POST to the same internal endpoint. The fragile / ToS-sensitive ingest layer (n8n flows) is structurally isolated from the trusted core tailoring layer. The tool degrades gracefully: if all crawlers break tomorrow, the paste path still works, which is the safety net for income-critical use.

### Market Context & Competitive Landscape

The competitive landscape splits into three groups, each of which Job Hunter explicitly differentiates from:

- **Analyzers (Jobscan ~$50/mo, Teal+ $29/mo, Huntr ~$20/mo, ResumeWorded):** ATS scoring or tailoring, but push all work to the user; no continuous discovery; no drift / fabrication guardrails. Job Hunter does the tailoring *and* checks the output.
- **Auto-appliers (LazyApply, Sonara, JobRight.ai, LoopCV, AIApply):** volume sprayers. LazyApply has a Trustpilot rating of 2.4 stars; one Sonara user reported 1 screen per ~700 auto-applies; LinkedIn actively blacklists frequent automated submitters; JobRight.ai (Mar 2026) was publicly cited for keyword stuffing, phantom postings, and bad rewrites — the exact failure modes Job Hunter targets. Job Hunter is the structural opposite: low volume, high care, human submit.
- **Hybrid (Simplify Copilot + Huntr):** browser autofill plus Kanban tracker; user-initiated per role; no drift guardrails. Job Hunter does not auto-fill (ToS) and does not need a tracker UI in v1 (markdown files + git).

Market context (preserved for reference):

- Online recruitment SaaS market: ~$4.73B (2025) → $7.58B by 2034 (7% CAGR)
- Broader online recruitment platform market: ~$57.7B → $132B by 2032 (12.56% CAGR)
- 97.8% of F500 use a detectable ATS (Jobscan 2025); Workday parses ~39% of F500
- ATS rejects ~75% of resumes pre-human review; 88% of employers say bad ATS formatting loses qualified candidates
- 78% of applications now contain AI-generated content; the differentiation is shifting from "has AI" to "AI that doesn't get you rejected"

### Validation Approach

The innovation claims are validated empirically by the same metrics in Success Criteria:

- **Drift check earns its keep** if it catches ≥ 1 substantive fabrication issue per 10 packages over the first 30. If it never fires, the check is theatre; if it fires every time, the tailoring step is too aggressive and the prompt is tuned down.
- **The combination beats the components** if the author's interview conversion rate doubles over baseline within the rolling 30-application window. If the lift is < 25% at 8 weeks, the project is killed regardless of how clean the architecture looks.
- **Upwork-proposal-as-distinct-artifact** is validated by Upwork reply rate moving in the same direction as the headline screen-rate metric. If LinkedIn screens go up but Upwork replies don't move, the Upwork prompt template needs work.

### Risk Mitigation

- **If fabrication drift check is too unreliable to ship structurally**, fall back to a *hybrid*: structural claim-to-source-CV traceability for the easy cases (string match on canonical-CV entries) plus an LLM-double-check pass *only* for the hard cases (semantic equivalence). This is more expensive per app but keeps the v1 ship date.
- **If n8n / scheduled flows are too brittle**, the paste path is always available. Scheduled-search is sequenced last in v1 for exactly this reason.
- **If LLM provider costs don't fit the $0.25/app budget**, switch providers (decision deferred to v1 build time) or shorten prompt templates. The cost budget is non-negotiable; the implementation is.

## Project-Type Specific Requirements

### Project-Type Overview

Job Hunter is a **local single-user web app bound to `127.0.0.1`** plus an external workflow-automation surface (n8n / Make / equivalent). There is no mobile app, no API service for third parties, and no multi-tenant infrastructure in v1. The user interface in v1 is: a browser pointed at `http://127.0.0.1:8765`, the canonical CV file on disk (markdown/YAML, also editable through the Settings surface), and a Google Chat space receiving webhook pings. *(Revised on 2026-05-23 from a CLI-tool framing; see `DECISIONS.md` §6.)*

### Technical Architecture Considerations

- **Language / runtime.** Decided at v1 build time. Python or TypeScript are the leading candidates — both have mature LLM SDKs, good markdown tooling, and easy n8n integration. Final choice depends on which the author can move fastest in for a solo nights-and-weekends build.
- **Persistence.** Filesystem. Canonical CV is a markdown/YAML file in a git repo. Per-application outputs are markdown files in `./out/<slug>/`. Per-application metadata (drift verdicts, cost log, override flags) lives as JSON or YAML sidecar files next to the artifacts. No database in v1.
- **Configuration.** A single `.env` for secrets (LLM API key, GChat webhook URL, n8n endpoint token). A separate `config.yaml` for tunables (drift-check thresholds, prompt template paths, cost cap, output directory). `.env` is `.gitignore`'d; `config.yaml` may be checked in.
- **Application surface.** A single FastAPI app bound to `127.0.0.1:8765`. The `jobhunter` command boots the server (no subcommands). All user actions happen in a React + Vite + Tailwind frontend served by the same process. Tailwind config consumes design tokens from `design_guidelines/stitch-export/design.md`. Decision recorded in `DECISIONS.md` §6 (supersedes §1's CLI-first framing).
- **Internal "API."** The paste pipeline exposes a single internal endpoint (`POST /api/paste`) that accepts a JD payload (text + source + optional metadata) and runs the full pipeline. The browser textarea (FR48) calls this endpoint; the n8n flows call this endpoint. One pipeline, two clients.
- **LLM provider.** Single provider in v1. Anthropic, OpenAI, or a local model — chosen at build time based on cost/quality of structural fabrication-check tracing. The provider must support no-training data-handling terms.
- **Observability.** Per-request token logging (model, input tokens, output tokens, cost). Per-application metadata (drift verdicts, override flag, cost-to-produce). Both written to disk; aggregated by `GET /api/stats` and surfaced on the Dashboard (FR40, FR46).

### Implementation Considerations

- **Build sequence is non-negotiable.** v0.1 walking skeleton first (week 1). Then v1 in the exact order: paste pipeline hardening → Upwork proposal artifact → fabrication drift → content-loss drift → keyword-stuffing drift → GChat webhook → n8n scheduled flows. The author resists the temptation to parallelize.
- **Prompt templates are versioned files.** Each artifact type (CV, cover letter, Upwork proposal) has its own prompt template file in the repo. Templates are tagged with a version string that gets written into the per-application metadata so the author can correlate output quality with template revision.
- **Drift-check thresholds are config, not code.** Each check has a configurable threshold so the author can tune without redeploying. Defaults ship intentionally conservative (high recall, more flags); tuning loosens them based on real-application data.
- **No tests beyond smoke until v1.2.** v0.1 and the v1 build sequence ship with smoke tests only. A real eval set comes after 30 real applications produce labeled data. This is intentional — the eval set built before real use would be made-up examples, which is worse than no eval set.
- **n8n choice (self-hosted vs n8n cloud) is the author's call.** Both work. Self-hosted is cheaper and gives full control; cloud is faster to stand up. Either is fine for v1.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach: Problem-solving MVP, single primary user.** The MVP must demonstrably save the author real time and produce real interview lift on real applications. There is no "investor demo" stage. The MVP ships in two halves: a Week-1 walking skeleton that proves the concept works on a real application, then the v1 feature build that puts the drift check and scheduled discovery on top. The author is the only required user; peer adoption is v2 territory.

**Resource Requirements: One developer (the author), nights and weekends.** No designers, no copywriters, no DevOps. The single biggest scope risk is the author's own time, which is why the walking-skeleton constraint and the non-negotiable v1 build order exist — to prevent any single phase from sprawling into a month-long rabbit hole.

### MVP Feature Set (Phase 1, v1)

**Core User Journeys Supported in v1:**

- Journey 1 (Tuesday-evening Upwork tailoring) — paste-mode end-to-end
- Journey 2 (Friday-morning scheduled discovery) — scheduled-mode end-to-end, including LinkedIn Job Alert email ingest, Upwork search ingest, OJ.ph ingest
- Journey 3 (drift-check hold + override) — held-package queue, manual override, override logging
- Journey 4 (canonical-CV maintenance) — markdown source-of-truth, no re-import ceremony

Journey 5 (peer adoption) is *not* a v1 success criterion. The v1 capabilities used in Journey 5 (`.env`-based config, swappable canonical CV, per-user LLM key) exist by default, but no peer-packaging effort is included.

**Must-Have Capabilities (v1):**

1. Web app (FastAPI on `127.0.0.1` + React/Vite/Tailwind frontend) with a JD-paste textarea that runs the full pipeline end-to-end via `POST /api/paste`
2. JD parser that extracts structured fields including board-specific signals (Upwork budget bands, OJ.ph rate ranges)
3. Canonical CV in markdown/YAML, version-controlled, with entry-level tags
4. Three artifact types with separate prompt templates: traditional CV, cover letter, Upwork proposal
5. **Fabrication drift check** — claim-to-source-CV structural traceability (the headline)
6. **Content-loss drift check** — high-impact canonical-CV entries preserved when relevant
7. **Keyword-stuffing drift check** — density/placement within natural bounds
8. GChat webhook notification on pass; silent hold on fail; held queue listable on the Dashboard surface
9. Manual override path with logged metadata
10. n8n (or equivalent) scheduled flows ingesting Upwork search results, OJ.ph listings, and LinkedIn Job Alert emails into the same pipeline endpoint
11. Per-application metadata (drift verdicts, cost, override flag) on disk
12. Hard monthly spend cap on the LLM API key; per-request token logging from day one
13. Local-only storage; secrets in `.env`; `.gitignore` clean

### Post-MVP Features

**Phase 2 (v2, post-MVP):**

- Voice drift check (after eval set exists)
- Outcome learning loop (track screens → interviews → offers; feed back into tailoring)
- Interview-prep handoff (when a screen is booked, generate a tailored prep doc)
- Standalone drift-check CLI (ship the fabrication checker as a separable tool for peers and as a credibility builder)
- Email digest + push notifications (multi-channel after GChat proves out)
- Peer packaging (install docs, sample canonical-CV templates, opinionated `.env.example`)

**Phase 3 (v3, vision, 2–3 years out):**

- Optional hosted variant for non-technical users
- Browser-extension auto-fill (not auto-submit) if ToS landscape clarifies
- Drift-check evaluator expansion to track next-gen recruiter-side AI signals
- Multi-CV / multi-profile support

### Risk Mitigation Strategy

**Technical Risks:**

- *Structural fabrication check too brittle to ship.* Mitigation: hybrid fallback — structural traceability for easy cases plus targeted LLM double-check only for hard semantic-equivalence cases. Still cheaper than full LLM-as-judge.
- *LLM-as-judge unreliability bleeds into the v1 checks.* Mitigation: fabrication check is structural by design; subjective checks (voice) deferred to v2 with eval set.
- *n8n scheduled flows are brittle / scraping-fragile.* Mitigation: paste path is always available; scheduled-search is sequenced last in v1 so failure of this layer does not block the rest.
- *Cost runaway from a buggy evaluator loop.* Mitigation: hard monthly cap on the API key + per-request token logging + per-app cost KPI tracked from app #1.

**Market Risks:**

- *Recruiter-side AI detection keeps shifting; today's drift-clean output is tomorrow's tell.* Mitigation: drift checks live in config and prompts, not code, so they can be tuned without redeploying; v3 includes explicit "track next-gen detection signals" workstream.
- *Confounded success metric (selection effects vs tailoring quality).* Mitigation: track manual fit-score and recruiter response rate alongside the headline screen rate.

**Resource Risks:**

- *Solo nights-and-weekends build sprawls past 6 weeks.* Mitigation: hard week-1 walking-skeleton deadline; v1 build order is fixed; kill criterion at 8 weeks post-launch if metric does not move; "shareable with peers" is explicitly v2, not v1, to prevent packaging effort eating engineering time.
- *Author burns out before reaching the 30-application baseline.* Mitigation: baseline measurement is done in parallel with the v0.1 build, not as a separate phase. The author is logging applications anyway; making the log structured is the only extra cost.

## Functional Requirements

The Functional Requirements below are the binding capability contract for v1 (MVP). Items explicitly deferred to v2/v3 are noted but not enumerated as FRs. Every capability is testable, implementation-agnostic, and traces back to at least one user journey.

### Canonical CV Management

- FR1: Author can maintain their canonical CV as a single markdown/YAML file in a version-controlled directory.
- FR2: Author can attach tags to individual canonical-CV entries (e.g. `node, typescript, fintech`) to indicate which contexts each entry is relevant to.
- FR3: Author can mark canonical-CV entries as "high-impact" so the content-loss drift check protects them.
- FR4: System reads the canonical CV fresh on every pipeline run; no re-import or re-parse step exists.
- FR5: System rejects any attempt to ingest PDF or docx as a canonical-CV source.

### JD Ingest

- FR6: Author can paste a JD into the pipeline via the JD Pipeline & Tailoring surface (FR48) — a browser textarea that POSTs to `POST /api/paste` — and trigger the full tailoring + drift-check + notification pipeline.
- FR7: System exposes a single internal endpoint (`POST /api/paste` — the same handler invoked by the browser textarea above) that both the web UI and scheduled flows POST JDs to.
- FR8: Scheduled flows (n8n / Make / equivalent) can post JDs from Upwork search results into the pipeline endpoint.
- FR9: Scheduled flows can post JDs from OnlineJobs.ph listings into the pipeline endpoint.
- FR10: Scheduled flows can post JDs from parsed LinkedIn Job Alert emails into the pipeline endpoint.
- FR11: System never logs into the user's Upwork or LinkedIn account on the user's behalf.

### JD Parsing

- FR12: System parses each JD into structured fields including must-have requirements, nice-to-have requirements, tone, seniority, and red flags.
- FR13: System classifies the source board (Upwork, OJ.ph, LinkedIn, other) and applies board-specific signal extraction.
- FR14: System extracts Upwork-specific signals including budget band, hourly vs fixed-price, and screening questions, when present.
- FR15: System extracts OJ.ph-specific signals including stated rate range and role type.
- FR16: System surfaces JD red flags (e.g. budget below user-configured floor, vague-scope detection) on the staged package summary.

### Tailoring

- FR17: System generates a tailored markdown CV against the canonical CV for a given parsed JD.
- FR18: System generates a tailored markdown cover letter against the canonical CV for a given parsed JD.
- FR19: System generates a tailored Upwork proposal as a distinct artifact type with its own prompt template, separate from the cover letter.
- FR20: System selects the artifact set produced (CV+cover-letter vs Upwork proposal vs both) based on the JD's classified source board.
- FR21: Each prompt template is a versioned file in the repo, and the template version used is recorded in per-application metadata.

### Drift Check — Fabrication (v1, core)

- FR22: System verifies that every skill or claim asserted in the tailored CV traces to a corresponding entry in the canonical CV via structural matching (string match plus semantic-equivalence threshold).
- FR23: System fails the fabrication check if any tailored-output claim cannot be traced to a canonical-CV entry.
- FR24: System records each failed claim, its location in the tailored output, and the reason it failed traceability in per-application metadata.

### Drift Check — Content Loss (v1)

- FR25: System verifies that canonical-CV entries marked as "high-impact" appear in the tailored output when the JD's parsed requirements call for them.
- FR26: System fails the content-loss check if a high-impact, relevant entry was dropped.
- FR27: System records each dropped entry and the JD requirements it would have addressed in per-application metadata.

### Drift Check — Keyword Stuffing (v1)

- FR28: System measures density and placement of JD-derived keywords in the tailored output against configurable thresholds.
- FR29: System fails the keyword-stuffing check when density exceeds the configured per-section limits or when placement looks like a dump-paragraph.
- FR30: System records the offending keywords, density measurements, and locations in per-application metadata.

### Notification + Held-Package Queue

- FR31: System posts a notification to a configured Google Chat webhook when a package passes all drift checks.
- FR32: The GChat notification includes a one-line fit summary, the source board, and the path to the staged markdown package.
- FR33: System holds packages that fail any drift check without sending a notification.
- FR34: System writes the staged markdown artifacts to disk even when a package is held, so the user can read them.
- FR35: Author can list held packages and their failure reasons via the Dashboard surface (FR46), backed by `GET /api/queue`.
- FR36: Author can override a held package via the "Approve" action on the Dashboard surface (FR46/FR51), backed by `POST /api/override/<slug>`; the override is logged in per-application metadata.

### Output, Metadata, and Cost Observability

- FR37: System writes each generated package to `./out/<slug>/` as markdown artifacts (one file per artifact type).
- FR38: System writes a per-application metadata file (JSON or YAML) capturing JD source, parsed fields, drift verdicts, override flag if any, prompt-template versions, and total cost-to-produce.
- FR39: System logs per-request LLM token usage (model, input tokens, output tokens, dollar cost) from the first call onward.
- FR40: Author can view aggregated cost-per-application, drift-catch rate, and override rate on the Dashboard surface (FR46), backed by `GET /api/stats`.

### Configuration and Safety

- FR41: All secrets (LLM API keys, GChat webhook URLs, scheduled-flow tokens) live in `.env` and `.env` is `.gitignore`'d.
- FR42: All tunables (drift-check thresholds, prompt template paths, cost cap, output directory, JD-red-flag floors) live in a `config.yaml` separate from secrets.
- FR43: System enforces a configured hard monthly LLM spend cap and refuses to run when the cap is exceeded.
- FR44: System never auto-submits an application to any platform.

### Web Application Surface (web-only architecture; see DECISIONS.md §6, supersedes §5)

The product surface is a local-only single-user **web application**. There is no CLI subcommand surface — the `jobhunter` command boots a FastAPI server on `127.0.0.1` and (optionally) opens the browser. Every user action lives behind an HTTP endpoint + a frontend surface; FRs in this section apply to the app as a whole, and surface-by-surface FRs are scattered across the appropriate feature epics rather than carried as a separate epic. Design source of truth: `design_guidelines/stitch-export/` (frozen Stitch export, including `design.md` + 5 screen mockups).

- FR45: The `jobhunter` command (no subcommand) starts a FastAPI server bound to `127.0.0.1` (never `0.0.0.0`) on a default port `8765` that is overridable via `JOBHUNTER_WEB_PORT`, logs the URL to stderr, and best-effort opens the user's default browser. A startup check rejects any non-loopback bind host. There is no other CLI entrypoint.
- FR46: System presents a Dashboard surface showing the held-package queue, the rolling 30-application interview-conversion rate (from FR40), and the current per-month spend total (from FR43), matching the layout of `design_guidelines/stitch-export/html/01-dashboard.html`. (Owned by Epic 6.)
- FR47: System presents a Settings & Canonical CV surface that lets the author view and edit the canonical CV (FR1–FR3, including tags and high-impact flags) without leaving the browser, matching the layout of `design_guidelines/stitch-export/html/02-settings-canonical-cv.html`. (Owned by Epic 2.)
- FR48: System presents a JD Pipeline & Tailoring surface that lets the author paste a JD, trigger the pipeline (same path as FR6), and view the staged tailored artifacts (CV / cover letter / Upwork proposal — FR17–FR19), matching the layout of `design_guidelines/stitch-export/html/04-jd-pipeline-tailoring.html`. (Owned by Epic 2.)
- FR49: System presents a Drift Check Diagnostics surface that visualizes the fabrication, content-loss, and keyword-stuffing drift reports (FR22–FR30) per staged package — including per-claim source-traceability arrows, dropped high-impact entries with reason, and keyword-density heatmaps — matching the layout of `design_guidelines/stitch-export/html/05-drift-check-diagnostics.html`. (Built incrementally across Epics 3, 4, and 5 — one drift section per epic.)
- FR50: System presents a Job Alerts & Automated Scans surface that shows the status of scheduled n8n flows (FR8–FR10) — last-run timestamps, JDs ingested per flow, errors — matching the layout of `design_guidelines/stitch-export/html/03-job-alerts-automated-scans.html`. (Owned by Epic 7.)
- FR51: The Dashboard "Approve" action on a held package invokes the same override code path as `POST /api/override/<slug>` (FR36) and writes the same override metadata. The system never POSTs an application to any external job board (FR44 survives unchanged and is now structurally enforced — there is no second code path that could regress it).

### Explicitly Out of FR Scope in v1

- Voice drift check (v2)
- Outcome learning loop (v2)
- Interview-prep handoff (v2)
- Standalone drift-check CLI (v2)
- Email digest, push notifications (v2)
- Peer packaging / install docs (v2)
- Browser auto-fill (v3)
- Multi-CV / multi-profile (v3)
- Hosted / multi-tenant variant (v3)

## Non-Functional Requirements

Only the NFR categories that actually shape v1 are documented. Categories irrelevant to a local-first, single-user **web app bound to `127.0.0.1`** (e.g. concurrent-user scalability, multi-region availability, hosted accessibility compliance, public TLS termination) are intentionally omitted.

### Performance

- **End-to-end pipeline latency (paste mode):** under 90 seconds per JD from paste to staged package, including JD parse, tailoring of CV + cover letter (or Upwork proposal), and all three drift checks. Measured on the author's local hardware on the chosen LLM provider's standard tier.
- **End-to-end pipeline latency (scheduled mode):** no hard latency SLO. Scheduled flows run overnight; the user sees results in the morning. The constraint is throughput within the monthly cost cap, not per-JD latency.
- **Pipeline must not block on a single slow LLM call beyond a configurable per-call timeout** (default 60 seconds). Calls that time out fail the package cleanly with an explanatory verdict rather than hanging.

### Cost (treated as a first-class NFR because it is the project's defining economic posture)

- **Per-application LLM cost target: under $0.25 end-to-end**, including JD parse, tailoring, all three drift checks, and any single retry.
- **Hard monthly spend cap on the LLM API key**, enforced both at the provider portal (defense-in-depth) and in `config.yaml`. System refuses to run pipeline calls when the cap is breached.
- **Per-request token logging from the first call onward.** No call is unaccounted for.
- **Aggregated cost-per-application reported on the Dashboard surface (FR40, `GET /api/stats`)** so the KPI is always visible, not buried.

### Security and Privacy

- All secrets (LLM API key, GChat webhook URL, scheduled-flow auth tokens) in `.env`; `.env` is `.gitignore`'d.
- Sample `.env.example` is checked in with placeholder values only.
- Canonical CV, parsed JDs, tailored artifacts, and per-application metadata are stored on the user's local filesystem only. No cloud sync in v1.
- LLM provider selected for v1 must offer no-training data-handling terms.
- Client-confidential JD content (client names, NDA-shaped descriptions) is redacted before being sent upstream where feasible. Where redaction is not feasible, the user is responsible for deciding whether to run that JD through the pipeline at all.
- The system never auto-submits applications, never logs into user platform accounts, and never crawls LinkedIn (LinkedIn ingest is email parsing of official Job Alerts only).

### Reliability

- **Paste mode is the always-available path.** If scheduled flows, GChat webhook, or any other accessory subsystem is broken, paste mode must still produce a staged package.
- **Held-package queue is durable on disk.** A crash mid-pipeline does not lose a JD that was accepted by the ingest endpoint.
- **Cost-cap enforcement is non-bypassable** by the application logic; the cap check happens before any LLM call is made.

### Integration

- **Outbound LLM provider:** one provider at a time in v1 (provider choice deferred to build time). Switching providers must be a config change, not a code rewrite — model name, base URL, and API key all configurable.
- **Outbound notification:** Google Chat incoming webhook URL (one). Webhook URL is configurable.
- **Inbound JD endpoint:** a single internal endpoint (`POST /api/paste`) accepting JD payloads from both the web UI's browser textarea and from scheduled flows. The endpoint is authenticated by a shared token from `.env` (for n8n callers) so a misconfigured n8n instance cannot post junk into the pipeline; browser-origin requests are scoped by the localhost binding (no auth header required from `127.0.0.1`).
- **n8n / workflow tool:** self-hosted or cloud, author's choice. Flows are not part of the core code repo; they live in n8n's own state. The contract between n8n and the core is the inbound JD endpoint, nothing more.

### Maintainability

- **Drift-check thresholds, prompt templates, and red-flag floors are configuration**, not code. The author can tune behavior without redeploying.
- **Prompt templates are versioned files** with version strings recorded in per-application metadata so the author can correlate output quality with template revisions.
- **Per-application metadata is structured (JSON or YAML)** so the `GET /api/stats` endpoint (FR40) can aggregate without re-parsing markdown.

### Web Server Constraints (web-only architecture; see DECISIONS.md §6, supersedes §5)

- **Binding:** Server binds to `127.0.0.1` only — never `0.0.0.0`. A startup check rejects any non-loopback bind host. No LAN exposure default. If a `--bind` flag is added later, the default must remain loopback.
- **Auth:** No authentication in v1 (single-user, single-machine). No login screen, no session cookies. If auth is ever added, that needs a fresh ADR entry.
- **No outbound submission:** The "Approve" action invokes the only override code path that exists; it never POSTs an application to any external job board. FR44 (no auto-submit) survives unchanged and is structurally enforced — there is no second code path to regress it.
- **No new persistence layer:** Backend reads `sprint-status.yaml` + per-package sidecar JSON directly. No DB, no Redis, no separate state store.
- **One LLM SDK:** All tailoring still goes through `src/jobhunter/llm_client.py`. The web layer does not introduce new LLM call paths.
- **Design source of truth:** Tailwind config and component code derive design tokens from `design_guidelines/stitch-export/design.md`. No ad-hoc hex codes or pixel values in component source. Re-export from Stitch and overwrite the directory if the source design changes; never hand-edit inside `stitch-export/`.
- **Startup target:** `jobhunter` cold-start to first paint under 3s on the author's machine.
- **No CLI subcommand surface:** `jobhunter` takes no arguments other than launcher flags (e.g. `--port`). Subcommand syntaxes like `jobhunter paste`, `jobhunter status`, `jobhunter override`, `jobhunter stats` are explicitly not supported in v1 — those workflows are accessed via the browser surfaces (FR46–FR50) and their underlying endpoints.

### Out of Scope (NFR)

- Multi-user concurrency: this is a single-user local web app bound to `127.0.0.1` in v1.
- High-availability / multi-region: there is no hosted service.
- LAN / WAN exposure of the web UI: localhost-only in v1. Hosted multi-tenant variant is v3+.
- WCAG / Section 508 accessibility: the v1 local web UI is single-user on the author's own machine, so formal accessibility certification is not in scope. (Sensible defaults — keyboard nav, semantic HTML, sufficient contrast from the Stitch design system — should still be honored.)
- GDPR / CCPA programmatic compliance features: the only personal data is the author's own; full compliance review is revisited only if a hosted variant ships.

## PO Assumptions

The following decisions were defensible PM-level calls made where the distillate was silent or deferred-to-build-time. Each is recorded for traceability so the next phase (epics + stories) can revisit any that turn out to be wrong.

- **Project type classification.** Classified as "Local single-user web app + workflow-automation flows." (Originally classified as "Local CLI tool + workflow-automation flows" — revised on 2026-05-23 when the project pivoted to web-only architecture; see `DECISIONS.md` §6.) The distillate calls it "local script" with n8n flows but does not pick a formal project type from the BMAD CSV. Local-web-app-plus-workflow is the closest honest fit under the current architecture.
- **Domain classification.** Classified as "career_tech_personal_productivity / applied LLM tooling." Adjacent to HR-tech but candidate-side. Complexity rated medium (not low) because of the LLM-drift-check tuning surface and the platform-ToS surface.
- **Release mode = phased.** The brief defines v0.1 → v1 → v2 → v3 as explicit phases with a non-negotiable order. This is a phased delivery, not a single release.
- **Internal endpoint as the integration contract between the web UI and n8n.** The brief says scheduled flows "post JDs into the paste pipeline via an internal endpoint." This PRD specifies that endpoint as `POST /api/paste` — the *single* contract between every ingest path (browser textarea, n8n flows) and the core, with a shared auth token from `.env` for n8n callers and localhost-origin trust for the browser. (Revised on 2026-05-23 to drop the "or a CLI subcommand" alternative — see `DECISIONS.md` §6.)
- **Per-application latency SLO (paste mode: < 90s).** The brief sets a 10-minute *human-review* time budget but no machine-latency SLO. 90 seconds is a defensible target for a 3-call pipeline (parse + tailor + checks) on standard LLM tiers; tune at build time.
- **Drift-check thresholds default conservative (high recall, more flags).** The brief implies this stance ("catches ≥ 1 issue per 10 packages") but does not explicitly say defaults skew toward over-flagging. This PRD makes the stance explicit so v1 ships with false positives the author overrides, rather than false negatives that quietly let fabrications through.
- **Override flag is structured metadata, not a free-text comment.** The brief mentions human override implicitly; this PRD names it as a logged boolean plus reason field in per-application metadata so override-rate becomes a measurable signal.
- **Two-half MVP framing (walking skeleton + v1 build).** The brief explicitly carves out v0.1 and v1. The PO assumption here is that both halves together constitute the "MVP" for Phase 1 in BMAD terms, rather than naming v0.1 as a separate phase. This is a labeling choice, not a scope change.
