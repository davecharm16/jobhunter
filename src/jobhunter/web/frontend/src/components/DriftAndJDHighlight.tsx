import { useEffect, useRef, useState } from "react";
import { type DriftTrace } from "./InlineDriftHighlight";
import { type JDMustHave, JDTooltip, mustHavesToSpans } from "./InlineJDHighlight";
import { MarkdownRenderer, type HighlightSpan, type OnMarkClick } from "./MarkdownRenderer";

type DriftTooltipState = {
  claimText: string;
  sourceText: string | null;
  anchorRect: DOMRect;
} | null;

type JDTooltipState = {
  requirement: string;
  anchorRect: DOMRect;
} | null;

type Props = {
  /** Raw markdown source */
  source: string;
  /** Drift traces from the fabrication-check endpoint */
  traces: DriftTrace[];
  /** JD must-have requirements for positive tailoring highlights */
  mustHaves: JDMustHave[];
};

/**
 * Convert drift traces to HighlightSpan[], deduplicating by claim_text.
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
 * Combines drift highlights and JD-tailoring highlights on the same rendered
 * markdown — all through React-owned elements, no DOM mutation.
 *
 * Both highlight kinds are merged into a single HighlightSpan[] and passed to
 * MarkdownRenderer's `highlightSpans` prop. The renderer does a single pass
 * over each text node, so there are no staggered timeouts, no TreeWalker, and
 * no risk of React reconciliation errors from externally-mutated text nodes.
 *
 * Tooltip display is split by kind: drift marks show a DriftTooltip; JD marks
 * show a JDTooltip. At most one tooltip is visible at a time.
 */
export function DriftAndJDHighlight({ source, traces, mustHaves }: Props) {
  const [driftTooltip, setDriftTooltip] = useState<DriftTooltipState>(null);
  const [jdTooltip, setJdTooltip] = useState<JDTooltipState>(null);

  // Merge both span sets; drift spans take priority on overlap (listed first).
  const spans: HighlightSpan[] = [
    ...tracesToSpans(traces),
    ...mustHavesToSpans(mustHaves),
  ];

  // Close tooltips on Escape
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setDriftTooltip(null);
        setJdTooltip(null);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleMarkActivate: OnMarkClick = (span, anchorRect) => {
    if (span.kind === "drift-sourced" || span.kind === "drift-fabrication") {
      setJdTooltip(null);
      setDriftTooltip({
        claimText: span.claim_text,
        sourceText: span.source_text,
        anchorRect,
      });
    } else if (span.kind === "jd-tailored") {
      setDriftTooltip(null);
      setJdTooltip({ requirement: span.requirement, anchorRect });
    }
  };

  return (
    <div className="relative">
      <MarkdownRenderer
        source={source}
        highlightSpans={spans}
        onMarkActivate={handleMarkActivate}
      />

      {driftTooltip && (
        <DriftTooltip
          tooltip={driftTooltip}
          onClose={() => setDriftTooltip(null)}
        />
      )}
      {jdTooltip && (
        <JDTooltip
          tooltip={jdTooltip}
          onClose={() => setJdTooltip(null)}
        />
      )}
    </div>
  );
}

/* ── Drift tooltip (inline to avoid cross-file circular) ─────────────────── */

type DriftTooltipProps = {
  tooltip: NonNullable<DriftTooltipState>;
  onClose: () => void;
};

function DriftTooltip({ tooltip, onClose }: DriftTooltipProps) {
  const { claimText, sourceText, anchorRect } = tooltip;
  const isFabrication = sourceText === null;
  const tooltipRef = useRef<HTMLDivElement>(null);

  const top = anchorRect.bottom + window.scrollY + 6;
  const rawLeft = anchorRect.left + window.scrollX;
  const left = Math.min(rawLeft, window.innerWidth - 320);

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

      <p className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs">
        Claimed:
      </p>
      <p className="text-body-md font-body-md text-on-surface mb-stack-sm break-words">
        {claimText}
      </p>

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
