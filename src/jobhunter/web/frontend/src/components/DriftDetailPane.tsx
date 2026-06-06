/**
 * DriftDetailPane — shared drift detail renderer (05-1, 05-8).
 *
 * Extracted from DriftPage so DriftHistoryPage can reuse it without
 * duplicating the fabrication/content-loss/keyword-stuffing render tree.
 *
 * The 05-8 requirement (Check ID + run timestamp) is implemented here:
 * the caller passes `slug` (= check id) and the run timestamp is derived from
 * content_loss.ran_at or keyword_stuffing.ran_at — the most reliable
 * timestamp in the drift doc.
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
