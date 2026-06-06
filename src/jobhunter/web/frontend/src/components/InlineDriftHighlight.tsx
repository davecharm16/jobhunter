import { useEffect, useRef, useState } from "react";
import { MarkdownRenderer, type HighlightSpan } from "./MarkdownRenderer";

/**
 * A sourced claim: the LLM paraphrased something from the canonical CV but
 * the original text is available for comparison.
 */
export type DriftTrace = {
  claim_id: string;
  claim_text: string;
  source_text: string | null;
};

type TooltipState = {
  claimText: string;
  sourceText: string | null;
  /** Viewport-relative position of the highlighted span */
  anchorRect: DOMRect;
} | null;

type Props = {
  /** Raw markdown source to render */
  source: string;
  /**
   * Drift traces (both sourced & unsourced) to highlight inline.
   * When empty/undefined the component falls back to plain MarkdownRenderer.
   */
  traces: DriftTrace[] | undefined;
};

/**
 * Convert drift traces to HighlightSpan[] for MarkdownRenderer.
 * Deduplicates by claim_text (case-insensitive) to avoid redundant spans.
 */
function tracesToSpans(traces: DriftTrace[]): HighlightSpan[] {
  const seen = new Set<string>();
  const spans: HighlightSpan[] = [];
  for (const trace of traces) {
    const key = trace.claim_text.toLowerCase().trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    spans.push({
      kind: trace.source_text !== null ? "drift-sourced" : "drift-fabrication",
      matchText: trace.claim_text,
      claim_text: trace.claim_text,
      source_text: trace.source_text,
    });
  }
  return spans;
}

/**
 * Renders a markdown artifact with inline drift highlights. Each matched
 * claim_text gets a coloured `<mark>` span; hovering/focusing it shows a
 * tooltip with "Canonical said / Claimed" content.
 *
 * Design reference: 04-jd-pipeline-tailoring.html — error-container+dashed
 * underline for fabrications; primary-fixed+solid underline for sourced claims.
 *
 * All highlights are rendered as React elements via MarkdownRenderer —
 * no DOM mutation, no TreeWalker, no useLayoutEffect injection. This prevents
 * the NotFoundError crash that occurred when React tried to reconcile text
 * nodes that had been mutated by the previous DOM-injection approach.
 */
export function InlineDriftHighlight({ source, traces }: Props) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);
  const spans: HighlightSpan[] = traces && traces.length > 0
    ? tracesToSpans(traces)
    : [];

  // Close tooltip on Escape
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setTooltip(null);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  function handleMarkActivate(span: HighlightSpan, anchorRect: DOMRect) {
    if (span.kind === "drift-sourced" || span.kind === "drift-fabrication") {
      setTooltip({
        claimText: span.claim_text,
        sourceText: span.source_text,
        anchorRect,
      });
    }
  }

  return (
    <div className="relative">
      <MarkdownRenderer
        source={source}
        highlightSpans={spans}
        onMarkActivate={handleMarkActivate}
      />

      {tooltip && (
        <DriftTooltip
          tooltip={tooltip}
          onClose={() => setTooltip(null)}
        />
      )}
    </div>
  );
}

/* ── Tooltip overlay ─────────────────────────────────────────────────────── */

type DriftTooltipProps = {
  tooltip: NonNullable<TooltipState>;
  onClose: () => void;
};

function DriftTooltip({ tooltip, onClose }: DriftTooltipProps) {
  const { claimText, sourceText, anchorRect } = tooltip;
  const isFabrication = sourceText === null;
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Position below anchor; clamp to viewport right edge
  const top = anchorRect.bottom + window.scrollY + 6;
  const rawLeft = anchorRect.left + window.scrollX;
  const left = Math.min(rawLeft, window.innerWidth - 320);

  // Close on click-outside
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  return (
    <div
      ref={tooltipRef}
      role="tooltip"
      aria-live="polite"
      className="fixed z-50 w-72 rounded-lg shadow-lg border p-stack-sm text-body-md font-body-md"
      style={{
        top,
        left,
        fontFamily: "var(--font-ui)",
        backgroundColor: "var(--color-surface-container-lowest, #fff)",
        borderColor: isFabrication
          ? "var(--color-error, #ba1a1a)"
          : "var(--color-outline-variant, #c7c4d8)",
      }}
      onMouseLeave={onClose}
    >
      {/* Header badge */}
      <p
        className="text-label-md font-label-md uppercase tracking-wider mb-stack-xs"
        style={{
          color: isFabrication
            ? "var(--color-error, #ba1a1a)"
            : "var(--color-on-surface-variant, #464555)",
        }}
      >
        {isFabrication ? "Possible fabrication" : "Drift: sourced claim"}
      </p>

      {/* Claimed */}
      <p className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs">
        Claimed:
      </p>
      <p className="text-body-md font-body-md text-on-surface mb-stack-sm break-words">
        {claimText}
      </p>

      {/* Canonical */}
      <p className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs">
        Canonical said:
      </p>
      {sourceText ? (
        <p className="text-body-md font-body-md text-on-surface break-words">
          {sourceText}
        </p>
      ) : (
        <p className="text-body-md font-body-md italic text-on-surface-variant">
          no canonical source (possible fabrication)
        </p>
      )}

      {/* Dismiss */}
      <button
        type="button"
        className="mt-stack-sm text-label-md font-label-md uppercase tracking-wider text-primary hover:underline"
        onClick={onClose}
        aria-label="Close drift tooltip"
      >
        Dismiss
      </button>
    </div>
  );
}
