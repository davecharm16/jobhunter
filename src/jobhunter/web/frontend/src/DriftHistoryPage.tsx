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

function VerdictChip({ label, verdict }: { label: string; verdict: string | null }) {
  if (!verdict) return null;
  const isPass = verdict === "pass";
  const cls = isPass
    ? "bg-secondary-container text-primary border-primary/20"
    : "bg-error-container text-on-error-container border-error/40";
  return (
    <span
      className={`inline-flex items-center gap-stack-xs px-stack-xs py-[2px] rounded-full border text-label-md font-label-md uppercase tracking-wider ${cls}`}
    >
      <span className="opacity-70">{label}</span>
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

  const activeClass = "bg-secondary-container/50 border-primary/20";
  const idleClass = "border-transparent hover:bg-surface-container-low";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left p-stack-sm rounded-lg border transition-all flex flex-col gap-stack-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${isActive ? activeClass : idleClass}`}
      aria-current={isActive ? "true" : undefined}
    >
      <div className="flex items-start justify-between gap-stack-sm">
        <span className="text-body-md font-body-md font-semibold text-on-surface line-clamp-2">
          {label}
        </span>
        <span className="text-label-md font-label-md text-on-surface-variant shrink-0">
          {time}
        </span>
      </div>
      <div className="flex flex-wrap gap-stack-xs">
        {row.drift_verdicts && (
          <>
            <VerdictChip label="Fab" verdict={row.drift_verdicts.fabrication} />
            <VerdictChip label="Loss" verdict={row.drift_verdicts.content_loss} />
            <VerdictChip label="Kw" verdict={row.drift_verdicts.keyword_stuffing} />
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
            message:
              typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail),
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
    return () => {
      cancelled = true;
    };
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
          const message =
            typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          setDetailState({ kind: "error", slug: selectedSlug!, message });
          return;
        }
        setDetailState({ kind: "ready", slug: selectedSlug!, doc: body as DriftDocument });
      } catch (exc) {
        if (!cancelled)
          setDetailState({ kind: "error", slug: selectedSlug!, message: String(exc) });
      }
    }
    load();
    return () => {
      cancelled = true;
    };
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
          Review automated quality assessments for all tailored documents. Trace exact
          deviations between your canonical CV and the tailored output to ensure zero content
          hallucination.
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
              <h2 className="text-headline-md font-headline-md text-on-surface">
                Recent Checks
              </h2>
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
              <div className="flex-1 overflow-y-auto p-stack-xs flex flex-col gap-[2px] max-h-[600px]">
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
                  {detailState.message.includes("404") ||
                  detailState.message.includes("not_found") ? (
                    <>
                      No drift report exists for{" "}
                      <code className="font-mono">{detailState.slug}</code>. This package
                      predates the fabrication matcher.
                    </>
                  ) : (
                    <>Failed to load drift report: {detailState.message}</>
                  )}
                </div>
              </div>
            )}
            {detailState.kind === "ready" && (
              <div className="flex-1 overflow-y-auto p-stack-md max-h-[700px]">
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
