# LLM Provider Decision (Epic 3 Summary)

**Status.** Authority for this decision is `DECISIONS.md` §4. This artifact is an
Epic-3-specific evaluation summary written for Story 3.1 AC1 — it does NOT
override or duplicate §4; it captures the per-criterion evaluation against the
claim-extractor and structural-matcher workload, and pins the conditions that
would trigger reopening the decision for fabrication-drift work.

## Chosen provider

- **Provider:** Anthropic Claude via the official `anthropic` Python SDK.
- **Model:** `claude-haiku-4-5` (pinned in `src/jobhunter/llm_client.py` as
  `MODEL_NAME`).
- **API key env var:** `LLM_API_KEY` (wired in `.env.example`; loaded by
  `runtime_config.load_runtime_config`).
- **Per-call timeout env var:** `LLM_CALL_TIMEOUT_SECONDS` (default `60.0`
  matches NFR3; overridable per call via `config.yaml` —
  `fabrication.claim_extraction.timeout_seconds` for the Story 3.1 extractor).
- **Base URL:** SDK default. Switching providers (NFR-Integration) is a
  single-file rewrite of `llm_client.py` plus a `pyproject.toml` SDK pin
  change — no other module imports `anthropic` directly.

## Per-million-token pricing (used in cost math)

| Direction | Price (USD per 1M tokens) | Source |
|-----------|---------------------------|--------|
| Input  | `$1.00` (`INPUT_PRICE_PER_MTOK = Decimal("1.00")`)  | Pinned in `llm_client.py`, captured 2026-05-23 per DECISIONS §4 |
| Output | `$5.00` (`OUTPUT_PRICE_PER_MTOK = Decimal("5.00")`) | Pinned in `llm_client.py`, captured 2026-05-23 per DECISIONS §4 |

Per-call cost is computed as `Decimal(input_tokens) * INPUT_PRICE_PER_MTOK / 1e6
+ Decimal(output_tokens) * OUTPUT_PRICE_PER_MTOK / 1e6`, quantized to six
decimal places. Never `float` — see Story 1.5 AC3.

## Per-criterion evaluation (Epic 3)

The four PO-stated criteria from the PRD, scored for the Epic-3 workload
(atomic-claim extraction + structural matching + semantic check in Story 3.3):

1. **Cost-per-app < $0.25 (NFR-Cost).** A typical Epic-3 run adds 2–3
   `extract_claims` calls (one per produced artifact; ~1–3 KB markdown each)
   on top of the existing parse + tailor calls. Empirical envelope at
   pinned Haiku pricing lands under $0.01 per app even for the worst-case
   3-artifact set (cv + cover_letter + upwork_proposal). Headroom against
   the $0.25 target is ~25×.

2. **No-training data-handling terms (NFR10).** Anthropic's enterprise API
   terms exclude API inputs/outputs from model-training by default
   (verified 2026-05-23 per DECISIONS §4). Local-model alternatives also
   satisfy NFR10 by virtue of running on the user's machine, but lose on
   criterion 3 (see below).

3. **Structured / JSON output reliability for claim extraction.** This is
   the load-bearing criterion for Epic 3. The claim extractor uses the
   Anthropic tool-use API with
   `tool_choice={"type": "tool", "name": "emit_claims"}` so the model is
   forced to call the tool — free-form JSON in prose has a known parsing-
   failure mode that an atomic-claim extractor (potentially 10+ entries
   per artifact) would amplify. Tool-use schema enforces `claims[].claim_type
   ∈ {role, metric, skill, tool, responsibility, accomplishment}`, so a
   malformed `claim_type` is caught at the SDK boundary, not by our
   `_coerce_claim()` after the fact.

4. **Trace quality for structural matching (Story 3.2).** The semantic step
   (Story 3.3) uses the same provider's embeddings endpoint to keep the
   one-SDK constraint (NFR-Integration). Haiku's embedding-endpoint surface
   is documented and matches the tool-use API's auth/transport, so no
   second SDK pin is needed.

## Rejected alternatives

| Alternative | One-line rationale for rejection |
|---|---|
| **OpenAI `gpt-4o-mini`** (via the `openai` SDK) | Comparable cost and quality; rejected because there is no strong technical signal to prefer one over the other for this workload and v1 must carry exactly one LLM SDK pin (PRD NFR-Integration; DECISIONS §4). |
| **Local Llama variants** (`llama.cpp` / `ollama`) | Eliminates NFR10 risk by construction (no data leaves the machine), but adds a multi-GB binary dependency and slower wall-clock (~5–10× on first-byte for ~5 KB payloads), pushing per-call latency uncomfortably close to the 60s timeout. Rejected for v1; revisit if criterion 2 becomes a blocker (see "Revisit if" below). |
| **OpenAI `gpt-3.5-turbo`** | Cheaper still, but its structured-output reliability (criterion 3) is empirically weaker than Haiku 4.5's tool-use mode for multi-field schemas. Rejected on criterion 3. |

## Revisit if

This artifact (and the §4 decision it summarizes) must be reopened if any of
the following conditions hold. The first four conditions are inherited from
`DECISIONS.md` §4; the last two are Epic-3-specific.

1. Anthropic raises Haiku pricing > 2× during walking-skeleton or Epic-3 work
   or removes the model.
2. The chosen model fails the tool-use contract (malformed / missing
   tool-use response) at greater than ~5% of calls during smoke testing.
3. Epic 2's prompt-template versioning (Story 2.9) surfaces a feature gap
   that another provider closes (e.g. notably stronger structured-output
   mode, significantly cheaper tier for our payload shape).
4. The Anthropic SDK becomes incompatible with the pinned Python 3.11+ runtime.
5. **Epic 3 specific:** the tool-use JSON-schema reliability for the
   claim-extraction prompt (`emit_claims` array with three required fields
   per entry) drops below 95% on a representative fixture corpus during
   Epic 3 smoke testing. The threshold is set so Story 3.4's hard-fail
   policy does not flip on noise.
6. **Epic 3 specific:** the structural matcher (Story 3.2) plus semantic
   step (Story 3.3) produces too many false-positive `unsourced` verdicts
   (> 5% on the author's own paste history) traceable to claim-extraction
   granularity. In that case the prompt-template revision route lands
   first; provider switch lands only if prompt revision fails to recover.

## Story 3.3: Semantic Equivalence

The semantic-equivalence step (`src/jobhunter/semantic_matcher.py`) replaces
the Story-3.2 no-match stub the structural matcher hands unmatched claims
to. Two methods are configurable under `fabrication.semantic_method`:

- **`rule_based`** — Jaccard similarity over lowercased, stemmed tokens
  with a small stopword set. Default threshold `0.65`. **This is the v1
  default.**
- **`embedding_cosine`** — Embedding-vector cosine similarity. Default
  threshold `0.82`. Reserved; raises `NotImplementedError` in v1 (see
  "Anthropic deviation" below).

### Chosen default: `rule_based` at threshold `0.65`

**Why rule_based.** The locked-in LLM provider (Anthropic, per §4 above)
does not currently expose an embeddings endpoint via the official Python
SDK — only message completions. Wiring `embedding_cosine` against the
locked-in provider would require adding a second SDK pin
(`voyageai`, `openai`-embeddings, or local sentence-transformers), which
the v1 dependency budget does not include and which contradicts the
single-SDK constraint (NFR-Integration). `rule_based` is dependency-free,
deterministic, and observable (scores are inspectable floats), so v1
ships it as the default while preserving `embedding_cosine` as a
configurable upgrade path with a clear `NotImplementedError` message
naming the required next step.

**Why Jaccard + an in-house stemmer.** Jaccard over tokens is the
simplest similarity that captures bag-of-words paraphrase ("led the
team" ↔ "led the engineering team" scores `0.667` against the canonical
"led the team", above threshold). The stemmer strips a small fixed set
of common suffixes (`ing`, `es`, `ed`, `ly`, `s`) so "shipped" and
"shipping" collide, but it is intentionally lossy and dependency-free —
no NLTK, no `snowballstemmer`. Determinism beats accuracy here: the
author can inspect a borderline score and reason about it without
re-running an opaque model.

**Why threshold `0.65`.** Picked by inspection against the spec's
fixture pairs and the Story 3.2 test corpus:

| Claim (tailored) | Canonical | Score | Quantifier guard | Verdict |
|---|---|---:|---|---|
| `led the engineering team` | `led the team` | `0.667` | OK | sourced (honest paraphrase) |
| `led a 3-person engineering team` | `led the team` | `0.500` | n/a (below threshold) | unsourced (`semantic_below_threshold`) |
| `led a 3-person engineering team` | `led the engineering team` | `0.750` | catches `3-person` | unsourced (`quantifier_not_in_source (quantifier=3-person)`) |
| `Built a FastAPI service` | `Designed and built a FastAPI service` | `0.750` | OK | sourced |
| `Shipped a JSON-schema-validated ingestion layer` | `Shipped a JSON-schema ingestion layer` | `0.600` | OK | unsourced (just below) |

`0.65` leaves a small honest-paraphrase corridor while the quantifier
guard handles the embellishment case from below independently of the
similarity score.

### Anthropic deviation (one-SDK constraint)

The Story 3.3 AC1 wording — "computed via the locked-in LLM provider's
embeddings endpoint" — does not hold in v1 because Anthropic does not
ship one. The deviation is handled by:

1. Implementing `embedding_cosine_similarity` as a function that raises
   `NotImplementedError` with a message naming the future work
   (`voyageai` / `openai` / local sentence-transformers).
2. Defaulting `config.yaml` to `rule_based` so a fresh install does not
   trip the `NotImplementedError`.
3. Pinning this rationale here so a future Dave does not silently flip
   the default back to `embedding_cosine` without wiring up a real
   embeddings provider first.

### Hybrid fallback (AC4) — not in v1

The PRD's risk-mitigation section calls out a hybrid LLM-as-judge
fallback for skill / tool claims after exact + substring + semantic all
fail. Story 3.3 AC4 explicitly defers it: the claim fails cleanly. An
inline `# TODO(hybrid-fallback):` comment in `semantic_matcher.py`
references the PRD option so a future story can wire it in.

### Revisit if

This Story-3.3 sub-decision must be revisited if any of:

1. The false-positive rate on `rule_based` exceeds ~5% on the author's
   own paste history (the same threshold §6 of the parent revisit list
   uses for claim-extraction). In that case the first lever is the
   stopword set + stemmer (tune in place); the second lever is wiring
   `embedding_cosine` against a real embeddings provider.
2. Anthropic ships an embeddings endpoint that satisfies criterion 4
   above. The `embedding_cosine` path then becomes a one-function
   implementation against the same `LLM_API_KEY` env var.
3. The user explicitly opts in via `pyproject.toml` to a separate
   embeddings dependency (`voyageai`, `openai`, or local
   sentence-transformers). At that point flip `config.yaml`'s default
   and implement `embedding_cosine_similarity` properly.
