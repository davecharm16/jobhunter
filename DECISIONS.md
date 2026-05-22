# Architectural Decisions — jobhunter

This file records the foundational, hard-to-reverse decisions that every later story inherits. New entries should be additive — do not silently rewrite history. If a decision is overturned, leave the original entry and add a follow-up entry below it referencing the trigger.

---

## 1. Runtime / Language

**Decision:** Python (>= 3.11).

**Rationale.** Per PRD line 357 ("Python or TypeScript are the leading candidates — both have mature LLM SDKs, good markdown tooling, and easy n8n integration. Final choice depends on which the author can move fastest in for a solo nights-and-weekends build"), the deciding factor is solo-build velocity. Python wins here for three concrete reasons relevant to this project: (a) the JSON Resume validation ecosystem (`jsonschema`) is first-class and zero-friction, with no build step between writing a script and running it; (b) downstream stories (Epics 3–5: atomic claim extraction, semantic equivalence, keyword density) lean on text-processing and NLP libraries where Python has the deeper free/local toolbox; (c) the v1 pipeline is sequential and runs locally on the author's machine — Node's async strengths buy nothing here, and Python's stdlib + `pathlib` makes the filesystem-only persistence model (no DB in v1) ergonomic.

**Rejected alternative.** TypeScript (Node >= 20) with `ajv` for schema validation. Rejected because it would add a build step (`tsc`) and a `dist/` directory to every smoke test for no payoff at this stage; the LLM SDK and n8n integration story is equally good in both, so velocity tiebreakers win.

**Revisit if:**
- The chosen LLM SDK becomes unreliable or significantly behind on features in Python compared to its TypeScript counterpart.
- n8n integration ergonomics (Epic 7) break down because the internal `/post-ingest` endpoint surface (Story 2.11) is materially easier to author in Node.
- The fabrication-drift work (Epic 3) needs a JS-only NLP library that has no Python equivalent.

---

## 2. Canonical-CV Schema

**Decision:** JSON Resume v1.0.0 as the working assumption.
Schema URL of record: `https://github.com/jsonresume/resume-schema/blob/v1.0.0/schema.json`.
The schema is **vendored** into the repo at `schemas/jsonresume-v1.0.0.json` so that validation runs offline (per PRD NFR13 — paste mode must always work, including without a network).

**Sample location.** The canonical CV lives at the repo root as `canonical-cv.json`. The path is exposed to all code through the single constant `CANONICAL_CV_PATH` defined in `src/jobhunter/config.py`. No code anywhere else in the repo may hard-code the path.

**Reader contract (FR4).** Exactly one function — `jobhunter.canonical_cv.read_canonical_cv()` — loads the canonical CV. It re-reads from disk on every invocation (no in-process or on-disk caching). All downstream stories (1.3, 1.5, 2.1, 2.3, 3.1, 3.2, 4.1, 5.1) consume the CV through this function.

**Fall-back criterion (verbatim).** Fall back to minimal custom YAML if JSON Resume cannot cleanly represent the `tags` and `highImpact` per-entry extensions required by Epic 2 Story 2.1 (FR2, FR3).

**Note on extensions.** Story 1.1's sample uses pure JSON Resume v1.0.0 with **no** extensions. The `tags` and `highImpact` per-entry fields land in Story 2.1; that story is the first chance the fall-back criterion above could trigger.

**Binary-format rejection (Story 1.3, FR5).** `read_canonical_cv()` rejects any path ending in `.pdf`, `.docx`, or `.doc` (case-insensitive) by raising `UnsupportedCanonicalCVFormat` **before** any read attempt. The decision is path-extension-only — no MIME detection, no `python-docx`/`pdfminer`/`pypdf` dependency — because parsing the binary formats is the opposite of what FR5 asks for. The canonical CV must stay a diffable text format (JSON today; markdown or YAML once the fall-back criterion above fires).

---

## 3. Revisit Triggers (cross-cutting)

A future story should reopen the decisions above (and prepend a new dated entry, not edit the originals) if **any** of the following hold:

- **Runtime/language:** a chosen SDK (LLM, n8n bridge) is materially worse or absent in the current runtime.
- **Schema:** Story 2.1 cannot cleanly extend JSON Resume with `tags` + `highImpact` at the entry level without resorting to schema escape hatches (e.g. `additionalProperties: true` everywhere, or stuffing JSON-in-strings).
- **Persistence model:** filesystem-only persistence (no DB) starts losing data or producing race conditions under the per-application `./out/<slug>/` write pattern from Story 1.5.

---

*Last updated: 2026-05-23 (Story 1.3 — binary-format rejection clause added under §2).*
