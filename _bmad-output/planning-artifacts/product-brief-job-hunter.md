---
title: "Product Brief: Job Hunter"
status: "complete"
created: "2026-05-17"
updated: "2026-05-17"
inputs: ["user brain dump", "web research synthesis"]
---

# Product Brief: Job Hunter

**Author:** dave
**Date:** 2026-05-17
**Status:** Complete v1

---

## Executive Summary

**Job Hunter** is the AI résumé tool that won't get you rejected.

Recruiters today reject AI-generated résumés faster than they read them — 33.5% of hiring managers say they can spot AI in under 20 seconds, and 62% reject AI-generated résumés that lack personalization. Mainstream auto-apply bots (LazyApply, Sonara, JobRight.ai) make this worse: they spray generic applications, stuff keywords, and fabricate experience, leaving candidates with a trail of damaged reputations and no interviews to show for it (one Sonara user logged 1 screen from ~700 auto-applies). The existing paid analyzers (Jobscan, Teal, Huntr) push all the tailoring work back to you and don't catch the failure modes that actually get applications rejected.

Job Hunter takes a job description — pasted in or pulled automatically from Upwork, OnlineJobs.ph, and LinkedIn via an n8n-style workflow — tailors a CV, cover letter, or Upwork proposal to that specific posting, and runs a **drift check** that verifies the output: no fabricated skills, no lost original wins, no unnatural keyword stuffing, and (in time) voice preserved. Only when the package passes does the system notify the user to review and submit. The author always presses send.

This is a build-it-yourself solution to a real personal pain, designed first for the author and shaped so other serious job seekers can adopt it. Why now: LLM inference has dropped ~10× in two years, making per-JD tailoring economical at cents per application; ATS systems are universal (97.8% of F500); and the backlash against spray-and-pray AI is in full swing. A quality-first, drift-checked, human-gated tool is precisely what the moment rewards.

## The Problem

Active job seekers — especially freelancers and remote workers using Upwork, OnlineJobs.ph, and LinkedIn — face four compounding pains:

1. **Time tax.** Tailoring a CV and cover letter to every posting takes 30–60 minutes per application. A serious applicant doing this nightly burns 10+ hours a week before a single submit.
2. **Generic applications get filtered.** ATS systems reject ~75% of resumes before a human sees them; 88% of employers say they lose qualified candidates to bad formatting. On Upwork, generic proposals are ignored by clients flooded with copy-paste pitches.
3. **Discovery gaps.** Good roles disappear in hours. Without continuous monitoring, candidates miss the postings they would have been strongest for.
4. **AI tools cause as many problems as they solve.** Current AI résumé tools hallucinate experience, strip the candidate's voice, and over-stuff keywords in ways recruiters now actively detect and reject. The candidate looks worse, not better.

The status quo for someone trying to job-hunt seriously is exhausting *and* underperforming. Existing paid tools either solve one slice expensively (Jobscan ~$50/mo just for ATS scoring; Teal+ $29/mo for tailoring without search; Huntr ~$20/mo for tracking) or solve the whole pipeline poorly (LazyApply, Sonara, JobRight.ai — high volume, low quality, real reputational risk with employers).

## The Solution

Job Hunter runs an end-to-end pipeline, but with a human-approval gate on the most important step: hitting submit.

**1. Two ways in — paste or scheduled workflow.**
   - **Paste-a-JD mode (always available):** the user drops a job description into the tool and the full pipeline runs against it. No crawler dependency, no ToS exposure, works for any board or even off-board postings someone forwarded by email or DMed in Slack.
   - **Scheduled-search mode (optional):** a cron-style AI workflow (n8n or equivalent — Make.com, Zapier, a self-hosted scheduler) watches Upwork, OnlineJobs.ph, and LinkedIn for postings matching the user's criteria (skills, role types, rate, remote/location) and feeds them into the same downstream pipeline. Using workflow-automation tooling (rather than hand-rolled scrapers) keeps the solo build budget realistic, lets sources be added/swapped without code changes, and isolates the most fragile/ToS-sensitive layer from the core tailoring pipeline. For LinkedIn specifically, ingesting the official Job Alert emails is preferred over crawling the site.

**2. JD analysis.** Each posting — pasted or pulled — is parsed: requirements, must-haves vs nice-to-haves, tone, seniority, red flags (low budget on Upwork, vague scope, etc.).

**3. CV and cover letter tailoring.** Using the user's canonical CV as the source of truth, the system generates a tailored CV and cover letter (or Upwork proposal) aligned to the JD's specific language and emphasis.

**4. Drift check — the differentiator.** Before anything reaches the user, an automated review pass verifies four things, in order of v1 priority:
   - **No fabrication (v1, core).** Every claim in the tailored CV traces to a real entry in the source CV. Skills not in the original are not added. This is the only failure mode that makes output *unsendable*, so it ships first and has a concrete pass/fail (claim → source-traceability check).
   - **No content loss (v1).** Genuine wins and projects from the original CV survive the rewrite if they're relevant — measured by checking that high-impact entries from the canonical CV appear in tailored output.
   - **No keyword stuffing (v1.x).** Density and placement are natural. ATS-passable but not ATS-tell.
   - **Voice preserved (v2).** Tailored output reads in the candidate's tone, not generic AI prose. Deferred because "voice" lacks a crisp pass/fail and is a known tuning rabbit hole; addressed only after a hand-labeled eval set exists.

**5. Notify and review.** When a package passes drift check, the user is notified via email digest (batched), push (high-fit roles), and a Google Chat webhook (lightweight queue). The user opens the staged package, makes any final edits, and submits the application themselves.

The tool does the grunt work. The human keeps judgment and accountability.

## What Makes This Different

- **Drift check is the moat — and the headline.** No mainstream competitor verifies that tailored output is fabrication-free, content-preserving, and tone-natural. These are the *exact* failure modes that get AI résumés rejected in 2025–26. Job Hunter's tagline is the one peers will actually repeat: *"the AI résumé tool that won't get you rejected."*
- **Your account, your reputation, your submit button.** Every application is reviewed and submitted by the user — a feature, not a limitation. It's a quality posture, a reputational shield, and a legal posture: no auto-submit means no Indeed/LinkedIn ToS landmine and no account-ban risk (the same risk that has gotten LazyApply users blacklisted).
- **Works without depending on a crawler.** Paste any JD — from a board, a recruiter DM, a forwarded email — and get a tailored package. The paste path is always available and ToS-clean. The scheduled-search workflow (n8n / Make / equivalent) is an accelerator on top, not a single point of failure.
- **Built for the boards mainstream tools ignore.** Upwork proposals, OnlineJobs.ph postings, and LinkedIn roles are all first-class — including Upwork proposals as a distinct artifact, not a CV variant. US-centric incumbents under-serve these markets.
- **Cents per application, not $30/month.** Running on your own LLM API key, end-to-end cost is targeted under $0.25 per application. The author is building this because subscribing to inferior tools is the worse deal — and that cost story is the most persuasive line for peer adoption.

## Who This Serves

**Primary user — the author.** A working professional/freelancer doing serious, sustained job-hunting across Upwork, OnlineJobs.ph, and LinkedIn — all three as first-class channels. Each produces a different output artifact (Upwork proposal, OJ.ph application, traditional CV/cover letter), and the tool treats them accordingly rather than collapsing them into one format. Wants higher-quality applications at lower personal effort, and refuses to ship generic AI slop.

**Secondary users — peers who'd benefit from the same tool.** Freelancers and remote workers in similar markets (notably the PH remote-work scene around OnlineJobs.ph and Filipino Upwork freelancers) who feel the same pain and would adopt a working solution. Not a paid customer base — a shareable build.

**Explicit non-audience.** People who want to fire 500 applications a night. This product will be slower, more deliberate, and lower-volume by design.

## Success Criteria

**Primary metric: Interview conversion rate.** Percentage of submitted applications that reach a screen or interview, measured against the author's own baseline.

**Baseline measurement plan (pre-launch, 2–4 weeks):** Manually log every application the author sends today — count, hours spent, recruiter replies, screens reached. Aim for n ≥ 30 baseline applications before v1 cutover so the lift comparison is meaningful and not anecdote.

**Pre-committed target:** baseline screen rate × 2 over a rolling 30-application window post-launch. If after 8 weeks of real use the lift is < 25% over baseline, revisit assumptions or kill the project.

**Supporting signals:**
- Time-per-application drops from ~45 min to under 10 min of human review
- Fabrication drift check catches ≥ 1 substantive issue per ~10 generated packages (proves the check is doing real work, not theatre)
- Per-application LLM cost stays under $0.25
- Author actually keeps using it after the build phase ends (the truest signal)

**Anti-metric — explicitly NOT optimizing for:** applications submitted per week. Volume is not the goal.

## Scope

**v0.1 — Walking skeleton (week 1, must exist before anything else):**
A single script where the author pastes a JD, the system tailors a CV + cover letter against a **markdown/YAML canonical CV** (not PDF — version-controlled, diffable, no parser hell), and outputs a single markdown file the author opens in their editor to review and copy. No drift check, no notifications, no UI. If this doesn't save real time on a real application in week 1, the concept is wrong and bigger features won't fix it.

**v1 (MVP), built in this order on top of v0.1:**
1. **Fabrication drift check.** Claim-to-source-CV traceability. The only check that makes output unsendable, so it's the only one required in v1.
2. **Upwork-proposal pipeline as a first-class artifact** (not a cover-letter variant). Proposals are short, conversational, answer client screening questions — different shape, different prompt.
3. **Content-loss + keyword-stuffing checks.** Added once fabrication check is stable.
4. **Single notification channel: Google Chat webhook.** One HTTPS POST, no auth dance. Email digest and push deferred to v2.
5. **Scheduled-search via n8n (or equivalent workflow tool).** Set up source ingestion in n8n flows; flows post JDs into the paste pipeline via an internal endpoint. LinkedIn ingest via Job Alert email parsing, not site crawling. Only built after v1 #1–4 are real and used.

**Cost & ops budget (v1, non-negotiable):**
- Per-application LLM cost target: under $0.25 end-to-end
- Hard monthly spend cap with kill-switch on the API key
- Secrets in `.env`, `.gitignore`'d; canonical CV in markdown in version control
- Runtime: local script / local n8n instance — no hosted infra in v1

**Explicitly out of v1:**
- Voice drift check (no clean pass/fail — v2 with eval set)
- PDF/docx canonical-CV ingest (markdown-only; this is a feature, not a limitation)
- Email digest and push notifications
- Browser auto-fill / one-click apply
- Multi-CV / multi-profile support
- Web review UI with auth/state (just open the generated `.md` in your editor)
- Hosted SaaS / multi-tenant / billing
- Packaging for non-technical peers (v2 conversation, only after 30+ real applications)

## Vision

**One year out:** The author runs Job Hunter as part of their normal week, with measurable interview-rate lift, and a small circle of peers running their own instances. The drift check has caught enough real failures that "would I trust an unchecked AI résumé tool?" feels like a silly question. Three extensions of the v1 product are on the table — each natural, each leveraging artifacts the pipeline already produces:

- **Outcome learning loop.** Track which staged packages led to screens, interviews, and offers, and feed that signal back into tailoring. Which phrasings convert? Which JD shapes are worth more effort? Which Upwork proposal angles win replies? Over time, this turns Job Hunter from a tailoring tool into a personal hit-rate optimizer — a moat that compounds with use and is structurally impossible for generic SaaS to replicate.
- **Interview-prep handoff.** When a screen is booked, regenerate a tailored prep doc: likely questions, matching stories drawn from the canonical CV, JD-specific talking points. All the raw material already exists at submit time; this extends one step past "send" to capture the highest-leverage moment in the funnel.
- **Standalone drift-check CLI.** Ship the fabrication checker as a small standalone tool peers can run against *any* AI-tailored CV — including outputs from Teal, ChatGPT, or anyone else. It's a softer on-ramp for sharing, a credibility builder for the full project, and a way to publicly demonstrate the check is doing real work.

**Two-to-three years out:** If peer adoption grows organically, an optional hosted version for non-technical users — priced to undercut existing players, not extract from them. Browser-extension auto-fill becomes feasible once the legal/ToS landscape clarifies. Drift-check evaluators expand to detect the next generation of recruiter-side AI signals as they emerge. The core stance — quality over volume, human in the loop, no fabrication — does not change.

---

## Key Risks & Mitigations

- **Scraping ToS / account suspension.** Upwork especially aggressively bans automation, and the author's Upwork account is income-bearing. *Mitigation:* paste-a-JD mode is always available; scheduled-search uses n8n flows isolated from the author's logged-in accounts; LinkedIn ingest is via Job Alert emails, not site crawling; never auto-submit.
- **PII and confidentiality.** CVs, client-confidential JDs, and proposal content pass through third-party LLM APIs. *Mitigation:* prefer providers with no-training data-handling terms; redact identifiable client info before sending JDs upstream; default to local-only storage; if a hosted variant ever exists, GDPR/CCPA-compliant.
- **LLM-as-judge unreliability.** The drift check is itself an LLM, prone to the same hallucinations it polices. *Mitigation:* fabrication check is structural (claim-to-source string/semantic match), not vibes; subjective checks (voice) are deferred until a hand-labeled eval set exists.
- **Cost runaway.** A buggy loop in an evaluator can rack up real money overnight. *Mitigation:* hard monthly spend cap on the API key; per-request token logging from day one; per-application cost target ($0.25) tracked as a KPI.
- **Scope creep.** Solo nights/weekends build with a long feature list. *Mitigation:* v0.1 walking skeleton must exist in week 1; "shareable with peers" is a v2 conversation, not a v1 requirement; defer anything that doesn't move the screen-rate metric.
- **Confounded success metric.** Interview lift could be driven by selection effects (tool surfaces better-fit roles), not tailoring quality. *Mitigation:* track *application quality* (manual fit-score) and *response rate* alongside the headline metric to disentangle.
