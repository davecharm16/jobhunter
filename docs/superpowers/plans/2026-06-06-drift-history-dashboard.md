# Drift History Master/Detail Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a master/detail drift history dashboard at `/drift` that shows all checked packages in a selectable list, aggregate bento metrics, and the full per-package drift detail — while adding Check ID + run timestamp to the detail header.

**Architecture:** Create a single new page `DriftHistoryPage.tsx` that fetches `/api/drift/history` for the master list and bento metrics, and `/api/package/{slug}/drift` lazily for the selected package's detail. The detail rendering reuses the private components already defined inside `DriftPage.tsx` — these will be extracted into a shared `DriftDetailPane.tsx` component in the same task so both `DriftPage` and `DriftHistoryPage` can import them without duplication. The existing `/packages/:slug/drift` route keeps using `DriftPage` (no redirect needed). Only the `<Routes>` block of `App.tsx` is touched.

**Tech Stack:** React 18, TypeScript, React Router v6, Tailwind CSS (design tokens via `tailwind.config.js`), no new npm deps.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `src/jobhunter/web/frontend/src/components/DriftDetailPane.tsx` | **Create** | Extracted shared drift detail renderer (types + FabricationContent + PlaceholderContent + TraceDiffList + DiffLegend + the full JSX body that DriftPage currently renders inline). Also adds the 05-8 Check ID/timestamp sub-header. |
| `src/jobhunter/web/frontend/src/DriftPage.tsx` | **Modify** | Replace its own inline render logic with `<DriftDetailPane>`. Shrinks to a thin data-fetching wrapper. |
| `src/jobhunter/web/frontend/src/DriftHistoryPage.tsx` | **Create** | Master/detail layout: history list (left), bento metrics (top), detail pane (main/right). |
| `src/jobhunter/web/frontend/src/App.tsx` | **Modify** | Add `import { DriftHistoryPage }` + one `<Route path="/drift" …>` in the existing `<Routes>` block only. |

---

## Task 1: Extract shared drift detail into `DriftDetailPane.tsx`

**Files:**
- Create: `src/jobhunter/web/frontend/src/components/DriftDetailPane.tsx`
- Modify: `src/jobhunter/web/frontend/src/DriftPage.tsx`

This task extracts the render-only pieces from `DriftPage.tsx` into a reusable component. The data-fetching and route shell stay in `DriftPage.tsx`.

### Key types to export from `DriftDetailPane.tsx`

The component receives a fully-loaded `DriftDocument` + the slug + optional `ranAt` timestamp. All types it needs are either imported from existing component files or redefined locally.

- [ ] **Step 1.1: Create `DriftDetailPane.tsx`**

Create `/Users/davecharmbulaquena/Desktop/job_hunter/src/jobhunter/web/frontend/src/components/DriftDetailPane.tsx` with this exact content:

```tsx
/**
 * DriftDetailPane — shared drift detail renderer (05-1, 05-8).
 *
 * Extracted from DriftPage so DriftHistoryPage can reuse it without
 * duplicating the fabrication/content-loss/keyword-stuffing render tree.
 *
 * The 05-8 requirement (Check ID + run timestamp) is implemented here:
 * the caller passes `slug` (= check id) and `ranAt` (from content_loss.ran_at
 * or keyword_stuffing.ran_at — the most reliable timestamp in the drift doc).
 */

import { Link } from "react-router-dom";
import {
  DriftSection,
  type DriftVerdict,
} from "./DriftSection";
import {
  ContentLossSection,
  type ContentLossBlock,
} from "./ContentLossSection";
import {
  KeywordStuffingSection,
  type KeywordStuffingBlock,
} from "./KeywordStuffingSection";
import { SemanticTraceDiff } from "./SemanticTraceDiff";
import { DriftStatStrip } from "./DriftStatStrip";

// ---------------------------------------------------------------------------
// Types (mirror DriftPage.tsx wire shapes)
// ---------------------------------------------------------------------------

export type Trace = {
  claim_id: string;
  claim_text: string;
  matched_canonical_entry_id: string;
  match_method: "exact_string" | "substring" | "semantic";
  match_score: number;
  source_text: string | null;
};

export type UnsourcedClaim = {
  claim_id: string;
  claim_text: string;
  source_artifact: string;
  line_number: number;
  reason: string;
};

export type FabricationCheck = {
  verdict: "pass" | "fail";
  claims_total: number;
  claims_sourced: number;
  claims_unsourced: number;
  traces: Trace[];
  unsourced_claims: UnsourcedClaim[];
};

export type DriftDocument = {
  fabrication_check?: FabricationCheck;
  content_loss?: ContentLossBlock;
  keyword_stuffing?: KeywordStuffingBlock;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fabricationVerdict(doc: DriftDocument): DriftVerdict {
  const fab = doc.fabrication_check;
  if (!fab) return "unknown";
  return fab.verdict;
}

function contentLossVerdict(doc: DriftDocument): DriftVerdict {
  const cl = doc.content_loss;
  if (!cl) return "pending";
  return cl.verdict;
}

function contentLossSubtitle(doc: DriftDocument): string | undefined {
  const cl = doc.content_loss;
  if (!cl) return undefined;
  const preserved = cl.preserved_entries.length;
  const dropped = cl.dropped_entries.length;
  if (preserved === 0 && dropped === 0) return "No high-impact entries to verify";
  return `${preserved} preserved · ${dropped} dropped`;
}

function keywordStuffingVerdict(doc: DriftDocument): DriftVerdict {
  const ks = doc.keyword_stuffing;
  if (!ks) return "pending";
  return ks.verdict;
}

function keywordStuffingSubtitle(doc: DriftDocument): string | undefined {
  const ks = doc.keyword_stuffing;
  if (!ks) return undefined;
  const densityCount = ks.density_violations.length;
  const dumpCount = ks.dump_paragraph_locations.length;
  if (densityCount === 0 && dumpCount === 0) return "No keyword-stuffing signals";
  return `${densityCount} density · ${dumpCount} dump-paragraph${dumpCount === 1 ? "" : "s"}`;
}

/** Derive the best available run timestamp from the drift document. */
export function driftRunAt(doc: DriftDocument): string | null {
  return doc.content_loss?.ran_at ?? doc.keyword_stuffing?.ran_at ?? null;
}

/** Format an ISO timestamp for display, e.g. "27 May 2026, 05:13 UTC". */
function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Private sub-components
// ---------------------------------------------------------------------------

function DiffLegend() {
  return (
    <div className="flex items-center gap-stack-md text-label-md font-label-md text-on-surface-variant">
      <span className="flex items-center gap-stack-xs">
        <span className="inline-block w-3 h-3 rounded-sm bg-error-container border border-error/30" />
        <span>− removed</span>
      </span>
      <span className="flex items-center gap-stack-xs">
        <strong className="inline-block w-3 h-3 rounded-sm bg-[#dcfce7] border border-[#86efac]" />
        <span>+ added (bold)</span>
      </span>
    </div>
  );
}

function TraceDiffList({ traces }: { traces: Trace[] }) {
  return (
    <details className="group rounded-xl border border-outline-variant bg-surface-container-lowest overflow-hidden">
      <summary className="cursor-pointer list-none px-stack-md py-stack-sm bg-surface-container-low text-label-md font-label-md uppercase tracking-wider text-on-surface-variant focus:outline-none focus-visible:ring-2 focus-visible:ring-primary hover:text-primary group-open:text-primary flex items-center justify-between">
        <span>
          Trace evidence ({traces.length} claim{traces.length === 1 ? "" : "s"})
        </span>
        <span className="group-open:hidden">expand</span>
        <span className="hidden group-open:inline">collapse</span>
      </summary>
      <div className="flex flex-col gap-stack-md p-stack-md">
        <DiffLegend />
        {traces.map((trace) => (
          <div key={trace.claim_id} className="flex flex-col gap-stack-xs">
            <div className="flex flex-wrap items-center gap-stack-md text-label-md font-label-md text-on-surface-variant">
              <code className="font-mono text-on-surface truncate max-w-xs">
                {trace.claim_id}
              </code>
              <span className="uppercase tracking-wider">{trace.match_method}</span>
              <span className="uppercase tracking-wider">
                score: {trace.match_score.toFixed(3)}
              </span>
            </div>
            <SemanticTraceDiff
              claimText={trace.claim_text}
              sourceText={trace.source_text}
              traceId={trace.claim_id}
            />
          </div>
        ))}
      </div>
    </details>
  );
}

function FabricationContent({ check }: { check: FabricationCheck }) {
  if (check.verdict === "pass") {
    return (
      <div className="flex flex-col gap-stack-md">
        <div className="rounded-lg border border-outline-variant bg-surface p-stack-md flex flex-col gap-stack-xs">
          <p className="text-body-md font-body-md text-on-surface">
            No fabricated claims detected.
          </p>
          <p className="text-label-md font-label-md text-on-surface-variant">
            Every one of the {check.claims_total} extracted claim
            {check.claims_total === 1 ? "" : "s"} traces back to a canonical-CV entry.
          </p>
        </div>
        {check.traces.length > 0 && <TraceDiffList traces={check.traces} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-stack-md">
      <p className="text-body-md font-body-md text-on-surface-variant">
        {check.claims_unsourced} of {check.claims_total} claim
        {check.claims_total === 1 ? "" : "s"} could not be traced back to the canonical CV.
      </p>
      {check.unsourced_claims.length > 0 && (
        <>
          <DiffLegend />
          <ul className="flex flex-col gap-stack-sm">
            {check.unsourced_claims.map((claim) => (
              <li
                key={claim.claim_id}
                className="rounded-lg border border-error/40 bg-error-container/40 p-stack-md flex flex-col gap-stack-xs"
              >
                <div className="flex items-start justify-between gap-stack-md">
                  <p className="text-body-md font-body-md text-on-surface font-medium break-words">
                    {claim.claim_text}
                  </p>
                  <span className="shrink-0 text-label-md font-label-md text-on-error-container uppercase tracking-wider">
                    no source entry found
                  </span>
                </div>
                <div className="flex flex-wrap gap-stack-md text-label-md font-label-md text-on-surface-variant">
                  <span>
                    <span className="uppercase tracking-wider">Artifact:</span>{" "}
                    <code className="font-mono text-on-surface">{claim.source_artifact}</code>
                  </span>
                  <span>
                    <span className="uppercase tracking-wider">Line:</span>{" "}
                    <code className="font-mono text-on-surface">{claim.line_number}</code>
                  </span>
                  <span>
                    <span className="uppercase tracking-wider">Claim ID:</span>{" "}
                    <code className="font-mono text-on-surface">{claim.claim_id}</code>
                  </span>
                </div>
                <SemanticTraceDiff
                  claimText={claim.claim_text}
                  sourceText={null}
                  traceId={claim.claim_id}
                />
                <details className="group rounded-lg border border-outline-variant bg-surface-container-lowest mt-stack-xs">
                  <summary className="cursor-pointer list-none px-stack-md py-stack-sm text-label-md font-label-md uppercase tracking-wider text-on-surface-variant focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg hover:text-primary group-open:text-primary flex items-center justify-between">
                    <span>Near-miss detail</span>
                    <span className="text-label-md font-label-md group-open:hidden">expand</span>
                    <span className="text-label-md font-label-md hidden group-open:inline">collapse</span>
                  </summary>
                  <div className="px-stack-md pb-stack-md text-body-md font-body-md text-on-surface-variant">
                    <p>
                      <span className="uppercase tracking-wider text-label-md">Reason:</span>{" "}
                      <code className="font-mono text-on-surface">{claim.reason}</code>
                    </p>
                    <p className="mt-stack-xs italic">
                      Candidate canonical-CV near-misses will be surfaced here once
                      the matcher emits them (future enhancement to package.drift.json).
                    </p>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        </>
      )}
      {check.traces.length > 0 && <TraceDiffList traces={check.traces} />}
    </div>
  );
}

function PlaceholderContent({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-outline-variant bg-surface p-stack-md">
      <p className="text-body-md font-body-md text-on-surface-variant italic">{label}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

type Props = {
  /** The slug is the Check ID (05-8). */
  slug: string;
  /** Parsed drift document. */
  doc: DriftDocument;
  /**
   * When true, renders the breadcrumb nav + page-level header.
   * Set false when embedding inside DriftHistoryPage (it has its own header).
   */
  showPageHeader?: boolean;
};

export function DriftDetailPane({ slug, doc, showPageHeader = true }: Props) {
  const fabrication = doc.fabrication_check;
  const fabVerdict = fabricationVerdict(doc);
  const ranAt = driftRunAt(doc);

  return (
    <div className="flex flex-col gap-stack-lg">
      {/* 05-10: stat strip */}
      <DriftStatStrip
        fabrication={doc.fabrication_check}
        contentLoss={doc.content_loss}
        keywordStuffing={doc.keyword_stuffing}
      />

      {showPageHeader && (
        <header className="flex flex-col gap-stack-xs">
          <div className="flex items-center gap-stack-sm text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
            <Link to="/" className="hover:text-primary">Dashboard</Link>
            <span>/</span>
            <Link to={`/packages/${slug}`} className="hover:text-primary">{slug}</Link>
            <span>/</span>
            <span>Drift</span>
          </div>
          <h1 className="text-display font-display text-on-surface break-words">
            Drift Check Diagnostics
          </h1>
          <p className="text-body-lg font-body-lg text-on-surface-variant max-w-2xl">
            Per-claim traceability between the tailored output and your canonical CV.
          </p>
        </header>
      )}

      {/* 05-8: Check ID + run timestamp sub-header */}
      <div className="rounded-xl border border-outline-variant bg-surface-container-lowest px-stack-md py-stack-sm flex flex-wrap items-center gap-stack-md text-label-md font-label-md text-on-surface-variant">
        <span>
          <span className="uppercase tracking-wider">Check ID:</span>{" "}
          <code className="font-mono text-on-surface">{slug}</code>
        </span>
        {ranAt && (
          <>
            <span className="hidden sm:inline w-px h-4 bg-outline-variant" aria-hidden="true" />
            <span>
              <span className="uppercase tracking-wider">Run:</span>{" "}
              <time dateTime={ranAt} className="text-on-surface">{formatTimestamp(ranAt)}</time>
            </span>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 gap-stack-md">
        <DriftSection
          title="Fabrication"
          verdict={fabVerdict}
          subtitle={
            fabrication
              ? `${fabrication.claims_sourced}/${fabrication.claims_total} claims sourced`
              : undefined
          }
        >
          {fabrication ? (
            <FabricationContent check={fabrication} />
          ) : (
            <p className="text-body-md font-body-md text-on-surface-variant italic">
              No fabrication_check block present in the drift report.
            </p>
          )}
        </DriftSection>

        <DriftSection
          title="Content Loss"
          verdict={contentLossVerdict(doc)}
          subtitle={contentLossSubtitle(doc)}
        >
          {doc.content_loss ? (
            <ContentLossSection block={doc.content_loss} />
          ) : (
            <PlaceholderContent label="Content-loss block not present in this drift report." />
          )}
        </DriftSection>

        <DriftSection
          title="Keyword Stuffing"
          verdict={keywordStuffingVerdict(doc)}
          subtitle={keywordStuffingSubtitle(doc)}
        >
          {doc.keyword_stuffing ? (
            <KeywordStuffingSection block={doc.keyword_stuffing} />
          ) : (
            <PlaceholderContent label="Keyword-stuffing block not present in this drift report." />
          )}
        </DriftSection>
      </div>
    </div>
  );
}
```

- [ ] **Step 1.2: Rewrite `DriftPage.tsx` to be a thin shell using `DriftDetailPane`**

Replace the entire content of `/Users/davecharmbulaquena/Desktop/job_hunter/src/jobhunter/web/frontend/src/DriftPage.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DriftDetailPane, type DriftDocument } from "./components/DriftDetailPane";

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; payload: DriftDocument }
  | { kind: "error"; status: number | null; message: string };

export function DriftPage() {
  const { slug } = useParams<{ slug: string }>();
  const [fetchState, setFetchState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    if (!slug) {
      setFetchState({ kind: "error", status: null, message: "missing_slug_in_route" });
      return;
    }
    setFetchState({ kind: "loading" });
    async function load() {
      try {
        const response = await fetch(`/api/package/${encodeURIComponent(slug!)}/drift`);
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          const message =
            typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          setFetchState({ kind: "error", status: response.status, message });
          return;
        }
        setFetchState({ kind: "ready", payload: body as DriftDocument });
      } catch (exc) {
        if (cancelled) return;
        setFetchState({ kind: "error", status: null, message: String(exc) });
      }
    }
    load();
    return () => { cancelled = true; };
  }, [slug]);

  if (fetchState.kind === "loading") {
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
        <p className="text-body-md font-body-md text-on-surface-variant">Loading drift report...</p>
      </div>
    );
  }

  if (fetchState.kind === "error") {
    const is404 = fetchState.status === 404;
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full flex flex-col gap-stack-md">
        <div className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
          {is404 ? (
            <>
              No drift report exists for package{" "}
              <code className="font-mono">{slug}</code>. This is normal for
              packages staged before the fabrication matcher landed (Epic 1 walking-skeleton runs).
            </>
          ) : (
            <>Failed to load drift report: {fetchState.message}</>
          )}
        </div>
        <div className="flex gap-stack-md">
          <Link to={`/packages/${slug ?? ""}`} className="text-primary underline text-body-md font-body-md">
            Back to package
          </Link>
          <Link to="/" className="text-primary underline text-body-md font-body-md">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
      <DriftDetailPane slug={slug!} doc={fetchState.payload} showPageHeader />
    </div>
  );
}
```

- [ ] **Step 1.3: Verify TypeScript compiles cleanly after extraction**

```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter/src/jobhunter/web/frontend && npm run build 2>&1 | tail -20
```

Expected: no type errors. If you see `Cannot find module './components/DriftDetailPane'`, check the file path.

- [ ] **Step 1.4: Commit**

```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter
git add src/jobhunter/web/frontend/src/components/DriftDetailPane.tsx src/jobhunter/web/frontend/src/DriftPage.tsx
git commit -m "refactor(drift): extract DriftDetailPane + add 05-8 check-id/timestamp sub-header"
```

---

## Task 2: Create `DriftHistoryPage.tsx` (master list + bento metrics + detail)

**Files:**
- Create: `src/jobhunter/web/frontend/src/DriftHistoryPage.tsx`

This page has three sections rendered in a two-column layout on large screens:
1. **Bento metrics** (top, full width) — computed from the history rows
2. **Recent Checks list** (left, scrollable) — one row per history entry, selectable
3. **Detail pane** (right, scrollable) — `DriftDetailPane` for the selected slug's drift doc

### Data shapes (from `/api/drift/history`)

```ts
type DriftVerdicts = {
  fabrication: string | null;
  content_loss: string | null;
  keyword_stuffing: string | null;
};

type HistoryRow = {
  slug: string;
  job_title: string | null;
  company_name: string | null;
  source_board: string | null;
  created_at: string | null;
  drift_verdicts: DriftVerdicts | null;
  held: boolean;
};
```

### Aggregate metric computations

Given `rows: HistoryRow[]`:
- **Total Checks**: `rows.length`
- **Fabrication Alerts**: `rows.filter(r => r.drift_verdicts?.fabrication === "fail").length`
- **Avg Content Loss %**: content_loss is `"pass"` or `"fail"` (no percentage in the history row). Compute as the fraction of rows with `content_loss === "fail"`, formatted as `N/total fail` or express as percentage. Since the history endpoint only has verdict strings, use: `Math.round((failCount / total) * 100)` → `"N%"`. If no rows have content_loss data, show `"—"`.
- **Keyword Match %**: rows where `keyword_stuffing === "pass"` divided by rows that have keyword_stuffing data. Format as percentage. If no data, show `"—"`.

- [ ] **Step 2.1: Create `DriftHistoryPage.tsx`**

Create `/Users/davecharmbulaquena/Desktop/job_hunter/src/jobhunter/web/frontend/src/DriftHistoryPage.tsx`:

```tsx
/**
 * DriftHistoryPage — Story gaps 05-1, 05-2, 05-3.
 *
 * Master/detail drift history dashboard:
 *   - Bento grid of aggregate metrics (05-2)
 *   - Selectable Recent Checks list (05-1, 05-3)
 *   - Selected package drift detail via DriftDetailPane (05-8 from that component)
 *
 * Fetches /api/drift/history once on mount for the list + metrics.
 * Lazily fetches /api/package/{slug}/drift when selection changes.
 */

import { useEffect, useState } from "react";
import { DriftDetailPane, type DriftDocument } from "./components/DriftDetailPane";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DriftVerdicts = {
  fabrication: string | null;
  content_loss: string | null;
  keyword_stuffing: string | null;
};

type HistoryRow = {
  slug: string;
  job_title: string | null;
  company_name: string | null;
  source_board: string | null;
  created_at: string | null;
  drift_verdicts: DriftVerdicts | null;
  held: boolean;
};

type HistoryState =
  | { kind: "loading" }
  | { kind: "ready"; rows: HistoryRow[] }
  | { kind: "error"; message: string };

type DetailState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; slug: string; doc: DriftDocument }
  | { kind: "error"; slug: string; message: string };

// ---------------------------------------------------------------------------
// Aggregate metric helpers
// ---------------------------------------------------------------------------

type Metrics = {
  totalChecks: number;
  fabricationAlerts: number;
  avgContentLossDisplay: string;
  keywordMatchDisplay: string;
};

function computeMetrics(rows: HistoryRow[]): Metrics {
  const total = rows.length;
  const fabricationAlerts = rows.filter(
    (r) => r.drift_verdicts?.fabrication === "fail",
  ).length;

  const clRows = rows.filter((r) => r.drift_verdicts?.content_loss != null);
  const avgContentLossDisplay =
    clRows.length === 0
      ? "—"
      : `${Math.round(
          (clRows.filter((r) => r.drift_verdicts!.content_loss === "fail").length /
            clRows.length) *
            100,
        )}% fail`;

  const ksRows = rows.filter((r) => r.drift_verdicts?.keyword_stuffing != null);
  const keywordMatchDisplay =
    ksRows.length === 0
      ? "—"
      : `${Math.round(
          (ksRows.filter((r) => r.drift_verdicts!.keyword_stuffing === "pass").length /
            ksRows.length) *
            100,
        )}%`;

  return { totalChecks: total, fabricationAlerts, avgContentLossDisplay, keywordMatchDisplay };
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return mins <= 1 ? "just now" : `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function packageLabel(row: HistoryRow): string {
  if (row.job_title && row.company_name) return `${row.job_title} — ${row.company_name}`;
  if (row.job_title) return row.job_title;
  if (row.company_name) return row.company_name;
  return row.slug;
}

// ---------------------------------------------------------------------------
// Bento metrics card
// ---------------------------------------------------------------------------

function BentoCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "good" | "bad";
}) {
  const valueClass =
    tone === "bad"
      ? "text-display font-display text-error"
      : tone === "good"
        ? "text-display font-display text-[#15803d]"
        : "text-display font-display text-on-surface";

  return (
    <div className="bg-surface border border-outline-variant rounded-xl p-stack-md flex flex-col gap-stack-sm">
      <span className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
        {label}
      </span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Verdict chip
// ---------------------------------------------------------------------------

function VerdictChip({ verdict }: { verdict: string | null }) {
  if (!verdict) return null;
  const isPass = verdict === "pass";
  const cls = isPass
    ? "bg-secondary-container text-primary border-primary/20"
    : "bg-error-container text-on-error-container border-error/40";
  return (
    <span
      className={`inline-flex items-center px-stack-xs py-[2px] rounded-full border text-label-md font-label-md uppercase tracking-wider ${cls}`}
    >
      {verdict}
    </span>
  );
}

// ---------------------------------------------------------------------------
// History list row
// ---------------------------------------------------------------------------

function HistoryListItem({
  row,
  isActive,
  onSelect,
}: {
  row: HistoryRow;
  isActive: boolean;
  onSelect: () => void;
}) {
  const label = packageLabel(row);
  const time = relativeTime(row.created_at);

  const activeClass =
    "bg-secondary-container/50 border-primary/20";
  const idleClass =
    "border-transparent hover:bg-surface-container-low";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left p-stack-sm rounded-lg border transition-all flex flex-col gap-stack-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${isActive ? activeClass : idleClass}`}
      aria-current={isActive ? "true" : undefined}
    >
      <div className="flex items-start justify-between gap-stack-sm">
        <span className="text-body-md font-body-md font-semibold text-on-surface line-clamp-2 text-left">
          {label}
        </span>
        <span className="text-label-md font-label-md text-on-surface-variant shrink-0">
          {time}
        </span>
      </div>
      <div className="flex flex-wrap gap-stack-xs">
        {row.drift_verdicts && (
          <>
            <VerdictChip verdict={row.drift_verdicts.fabrication} />
            <VerdictChip verdict={row.drift_verdicts.content_loss} />
            <VerdictChip verdict={row.drift_verdicts.keyword_stuffing} />
          </>
        )}
        {row.held && (
          <span className="inline-flex items-center px-stack-xs py-[2px] rounded-full border border-outline-variant bg-surface-container text-on-surface-variant text-label-md font-label-md uppercase tracking-wider">
            held
          </span>
        )}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function DriftHistoryPage() {
  const [historyState, setHistoryState] = useState<HistoryState>({ kind: "loading" });
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [detailState, setDetailState] = useState<DetailState>({ kind: "idle" });

  // Fetch history list on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/drift/history");
        const body = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          setHistoryState({
            kind: "error",
            message: typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail),
          });
          return;
        }
        const rows: HistoryRow[] = body.checks ?? [];
        setHistoryState({ kind: "ready", rows });
        // Default-select the newest (first) check
        if (rows.length > 0) {
          setSelectedSlug(rows[0].slug);
        }
      } catch (exc) {
        if (!cancelled) setHistoryState({ kind: "error", message: String(exc) });
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // Fetch drift detail when selection changes
  useEffect(() => {
    if (!selectedSlug) return;
    let cancelled = false;
    setDetailState({ kind: "loading" });
    async function load() {
      try {
        const res = await fetch(`/api/package/${encodeURIComponent(selectedSlug!)}/drift`);
        const body = await res.json();
        if (cancelled) return;
        if (!res.ok) {
          const message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          setDetailState({ kind: "error", slug: selectedSlug!, message });
          return;
        }
        setDetailState({ kind: "ready", slug: selectedSlug!, doc: body as DriftDocument });
      } catch (exc) {
        if (!cancelled) setDetailState({ kind: "error", slug: selectedSlug!, message: String(exc) });
      }
    }
    load();
    return () => { cancelled = true; };
  }, [selectedSlug]);

  const rows = historyState.kind === "ready" ? historyState.rows : [];
  const metrics = computeMetrics(rows);

  return (
    <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      {/* Page header */}
      <div>
        <h1 className="text-display font-display text-on-surface mb-stack-xs">
          Drift Checks History
        </h1>
        <p className="text-body-lg font-body-lg text-on-surface-variant max-w-2xl">
          Review automated quality assessments for all tailored documents. Trace exact deviations
          between your canonical CV and the tailored output to ensure zero content hallucination.
        </p>
      </div>

      {/* 05-2: Bento aggregate metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-stack-sm">
        <BentoCard label="Total Checks" value={metrics.totalChecks} />
        <BentoCard
          label="Fabrication Alerts"
          value={metrics.fabricationAlerts}
          tone={metrics.fabricationAlerts > 0 ? "bad" : "good"}
        />
        <BentoCard label="Avg Content Loss" value={metrics.avgContentLossDisplay} />
        <BentoCard label="Keyword Match" value={metrics.keywordMatchDisplay} />
      </div>

      {/* History loading/error */}
      {historyState.kind === "loading" && (
        <p className="text-body-md font-body-md text-on-surface-variant">Loading checks...</p>
      )}
      {historyState.kind === "error" && (
        <div className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
          Failed to load drift history: {historyState.message}
        </div>
      )}

      {/* 05-1 / 05-3: Master/detail split */}
      {historyState.kind === "ready" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-stack-md min-h-[600px]">
          {/* Left: Recent Checks list */}
          <aside className="lg:col-span-4 flex flex-col bg-surface border border-outline-variant rounded-xl overflow-hidden">
            <header className="px-stack-md py-stack-sm border-b border-outline-variant bg-surface-container-lowest flex items-center justify-between">
              <h2 className="text-headline-md font-headline-md text-on-surface">Recent Checks</h2>
              <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
                {rows.length} total
              </span>
            </header>
            {rows.length === 0 ? (
              <div className="flex-1 flex items-center justify-center p-stack-md">
                <p className="text-body-md font-body-md text-on-surface-variant italic">
                  No drift checks found. Run a tailoring job first.
                </p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-stack-xs flex flex-col gap-[2px]">
                {rows.map((row) => (
                  <HistoryListItem
                    key={row.slug}
                    row={row}
                    isActive={row.slug === selectedSlug}
                    onSelect={() => setSelectedSlug(row.slug)}
                  />
                ))}
              </div>
            )}
          </aside>

          {/* Right: Detail pane */}
          <main className="lg:col-span-8 flex flex-col bg-surface border border-outline-variant rounded-xl overflow-hidden">
            {detailState.kind === "idle" && (
              <div className="flex-1 flex items-center justify-center p-stack-md">
                <p className="text-body-md font-body-md text-on-surface-variant italic">
                  Select a check from the list.
                </p>
              </div>
            )}
            {detailState.kind === "loading" && (
              <div className="flex-1 flex items-center justify-center p-stack-md">
                <p className="text-body-md font-body-md text-on-surface-variant">
                  Loading drift report...
                </p>
              </div>
            )}
            {detailState.kind === "error" && (
              <div className="p-stack-md">
                <div className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
                  {detailState.message.includes("404") || detailState.message.includes("not_found") ? (
                    <>
                      No drift report exists for{" "}
                      <code className="font-mono">{detailState.slug}</code>. This package predates
                      the fabrication matcher.
                    </>
                  ) : (
                    <>Failed to load drift report: {detailState.message}</>
                  )}
                </div>
              </div>
            )}
            {detailState.kind === "ready" && (
              <div className="flex-1 overflow-y-auto p-stack-md">
                <DriftDetailPane
                  slug={detailState.slug}
                  doc={detailState.doc}
                  showPageHeader={false}
                />
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2.2: Verify TypeScript compiles cleanly**

```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter/src/jobhunter/web/frontend && npm run build 2>&1 | tail -20
```

Expected: zero type errors, zero warnings about missing modules.

- [ ] **Step 2.3: Commit**

```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter
git add src/jobhunter/web/frontend/src/DriftHistoryPage.tsx
git commit -m "feat(ui): DriftHistoryPage master/detail + 05-2 bento metrics (05-1,3)"
```

---

## Task 3: Wire `/drift` route in `App.tsx`

**Files:**
- Modify: `src/jobhunter/web/frontend/src/App.tsx` (Routes block only)

- [ ] **Step 3.1: Add the import and route**

In `App.tsx`, add `import { DriftHistoryPage } from "./DriftHistoryPage";` near the other page imports (line 8 area), then add `<Route path="/drift" element={<DriftHistoryPage />} />` inside the existing `<Routes>` block, directly after the `/scans` route:

The existing `<Routes>` block (lines 135–142) currently looks like:
```tsx
<Routes>
  <Route path="/" element={<DashboardPage />} />
  <Route path="/settings" element={<SettingsPage />} />
  <Route path="/packages/:slug" element={<PackagePage />} />
  <Route path="/packages/:slug/drift" element={<DriftPage />} />
  <Route path="/scans" element={<ScansPage />} />
  <Route path="*" element={<NotFound />} />
</Routes>
```

It should become:
```tsx
<Routes>
  <Route path="/" element={<DashboardPage />} />
  <Route path="/settings" element={<SettingsPage />} />
  <Route path="/packages/:slug" element={<PackagePage />} />
  <Route path="/packages/:slug/drift" element={<DriftPage />} />
  <Route path="/scans" element={<ScansPage />} />
  <Route path="/drift" element={<DriftHistoryPage />} />
  <Route path="*" element={<NotFound />} />
</Routes>
```

And add this import after line 9 (`import { DriftPage } from "./DriftPage";`):
```tsx
import { DriftHistoryPage } from "./DriftHistoryPage";
```

- [ ] **Step 3.2: Verify build passes**

```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter/src/jobhunter/web/frontend && npm run build 2>&1 | tail -20
```

Expected: clean build, dist/ output written with no TS errors.

- [ ] **Step 3.3: Final commit per task spec**

```bash
cd /Users/davecharmbulaquena/Desktop/job_hunter
git add src/jobhunter/web/frontend/src
git commit -m "feat(ui): drift history master/detail dashboard + aggregate bento metrics + check id/timestamp (05-1,2,3,8)"
```

Note: this is the required commit from the task spec. It will include the cumulative changes from all three tasks if you chose to squash, or you can keep the atomic commits from steps 1.4 and 2.3 and skip this step.

---

## Self-Review Checklist

**Spec coverage:**
- 05-1 (Recent Checks master list, one row per package, selectable): Task 2, `HistoryListItem` + `setSelectedSlug`.
- 05-2 (Bento aggregate metrics): Task 2, `BentoCard` grid with `computeMetrics()`.
- 05-3 (Selecting a row shows per-slug drift detail): Task 2, `selectedSlug` → detail fetch → `DriftDetailPane`.
- 05-8 (Check ID + run timestamp in detail header): Task 1, the "Check ID / Run" sub-header in `DriftDetailPane`, using `slug` + `driftRunAt(doc)`.
- Default-select newest check: `setSelectedSlug(rows[0].slug)` in mount effect.
- `/drift` route added, `/packages/:slug/drift` kept untouched.
- `DriftPage` still functional (thin wrapper using `DriftDetailPane`).
- No files outside the allowed set touched.

**Placeholder scan:** No TBD/TODO in the plan code blocks. All code is complete.

**Type consistency:**
- `DriftDocument` exported from `DriftDetailPane.tsx` and imported in both `DriftPage.tsx` and `DriftHistoryPage.tsx`.
- `driftRunAt` helper in `DriftDetailPane.tsx` matches its call site in the same file.
- `HistoryRow.drift_verdicts` has type `DriftVerdicts | null` — `computeMetrics` guards with `?? null` and `!= null` correctly.
- `DriftDetailPane` props: `slug: string`, `doc: DriftDocument`, `showPageHeader?: boolean` — all call sites pass compatible values.

All gaps covered, no placeholders, types consistent.
