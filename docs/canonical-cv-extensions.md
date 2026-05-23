# Canonical-CV jobhunter extensions

Story 2.1 layers two **optional** per-entry fields onto the vendored JSON Resume v1.0.0 schema (`schemas/jsonresume-v1.0.0.json`). Both fields are valid on `work`, `projects`, and `skills` entries. Neither field is ever required and neither propagates downstream as a required field.

A worked example lives at `samples/canonical-cv-with-extensions.json`.

## `tags` — relevance labels (FR2)

- **Type.** Optional array of strings.
- **Semantics.** Free-form labels (e.g. `["node", "typescript", "fintech"]`) the JD-tailoring router will use to pick relevant entries per JD.
- **Absence rule.** Absent means absent. The reader does **not** coerce a missing `tags` array into `[]` or any other shape. Downstream code must use `entry.get("tags", [])` if it wants a default — the source-of-truth dict reflects the on-disk document verbatim.

## `highImpact` — protected entries (FR3)

- **Type.** Optional boolean.
- **Semantics.** `true` marks the entry as one the Epic 4 content-loss drift check must surface if it disappears from a tailored CV. `false` (or absent) means no special protection.
- **Default.** Absent is equivalent to `false`. The `high_impact_entries()` projection in `jobhunter.canonical_cv` returns only entries with `highImpact == true`; entries with `highImpact: false` and entries missing the field are both excluded.

## Validation behaviour

`jobhunter.canonical_cv.read_canonical_cv()` validates against the vendored JSON Resume schema (with the extensions above layered in) on every load. A malformed document raises `CanonicalCVMalformed` with the JSON Pointer path to the offending node — the pipeline exits cleanly rather than silently coercing.
