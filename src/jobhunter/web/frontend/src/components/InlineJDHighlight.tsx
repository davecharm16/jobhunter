import { useEffect, useRef, useState } from "react";
import { MarkdownRenderer, type HighlightSpan, type OnMarkClick } from "./MarkdownRenderer";

/**
 * A JD must-have requirement used to highlight matching phrases in the CV.
 */
export type JDMustHave = string;

type TooltipState = {
  requirement: string;
  anchorRect: DOMRect;
} | null;

type StandaloneProps = {
  /** Raw markdown source to render */
  source: string;
  /**
   * JD must-have requirements. Phrases from this list that appear verbatim
   * (case-insensitive) in the CV text get a soft secondary-container highlight
   * with a tooltip naming the matched JD requirement.
   *
   * Best-effort keyword match: uses full-phrase substring search (case-insensitive).
   * Phrases paraphrased by the LLM will not be highlighted.
   */
  mustHaves: JDMustHave[] | undefined;
};

/**
 * Convert JD must-haves to HighlightSpan[] for MarkdownRenderer.
 */
function mustHavesToSpans(mustHaves: JDMustHave[]): HighlightSpan[] {
  const seen = new Set<string>();
  const spans: HighlightSpan[] = [];
  for (const requirement of mustHaves) {
    const phrase = requirement.trim().replace(/[.,;:!?]+$/, "").trim();
    if (!phrase || seen.has(phrase.toLowerCase())) continue;
    seen.add(phrase.toLowerCase());
    spans.push({
      kind: "jd-tailored",
      matchText: phrase,
      requirement,
    });
  }
  return spans;
}

/**
 * Standalone component: renders markdown + JD-tailoring highlights.
 *
 * All highlights are rendered as React elements via MarkdownRenderer —
 * no DOM mutation, no TreeWalker, no useLayoutEffect injection. This prevents
 * the NotFoundError crash that occurred when React tried to reconcile text
 * nodes that had been mutated by the previous DOM-injection approach.
 *
 * When drift highlights are also needed, use DriftAndJDHighlight which
 * composes both highlight kinds through the same React-rendered path.
 */
export function InlineJDHighlight({ source, mustHaves }: StandaloneProps) {
  const [tooltip, setTooltip] = useState<TooltipState>(null);
  const spans: HighlightSpan[] = mustHaves && mustHaves.length > 0
    ? mustHavesToSpans(mustHaves)
    : [];

  // Close tooltip on Escape
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setTooltip(null);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleMarkActivate: OnMarkClick = (span, anchorRect) => {
    if (span.kind === "jd-tailored") {
      setTooltip({ requirement: span.requirement, anchorRect });
    }
  };

  return (
    <div className="relative">
      <MarkdownRenderer
        source={source}
        highlightSpans={spans}
        onMarkActivate={handleMarkActivate}
      />
      {tooltip && (
        <JDTooltip tooltip={tooltip} onClose={() => setTooltip(null)} />
      )}
    </div>
  );
}

/* ── Tooltip ─────────────────────────────────────────────────────────────── */

type JDTooltipProps = {
  tooltip: NonNullable<TooltipState>;
  onClose: () => void;
};

export function JDTooltip({ tooltip, onClose }: JDTooltipProps) {
  const { requirement, anchorRect } = tooltip;
  const tooltipRef = useRef<HTMLDivElement>(null);

  const top = anchorRect.bottom + window.scrollY + 6;
  const rawLeft = anchorRect.left + window.scrollX;
  const left = Math.min(rawLeft, window.innerWidth - 320);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        tooltipRef.current &&
        !tooltipRef.current.contains(e.target as Node)
      ) {
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
        borderColor: "var(--color-primary, #3525cd)",
      }}
      onMouseLeave={onClose}
    >
      <p
        className="text-label-md font-label-md uppercase tracking-wider mb-stack-xs"
        style={{ color: "var(--color-primary, #3525cd)" }}
      >
        Tailored to JD
      </p>
      <p className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs">
        JD requirement:
      </p>
      <p className="text-body-md font-body-md text-on-surface break-words">
        {requirement}
      </p>
      <button
        type="button"
        className="mt-stack-sm text-label-md font-label-md uppercase tracking-wider text-primary hover:underline"
        onClick={onClose}
        aria-label="Close JD highlight tooltip"
      >
        Dismiss
      </button>
    </div>
  );
}

/**
 * Exported for DriftAndJDHighlight to build JD spans without rendering.
 */
export { mustHavesToSpans };
