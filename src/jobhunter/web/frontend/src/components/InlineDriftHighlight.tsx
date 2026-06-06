import { useLayoutEffect, useRef, useState } from "react";
import { MarkdownRenderer } from "./MarkdownRenderer";

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
 * Highlight severity:
 * - No source_text  → fabrication/unsourced → error (red)
 * - Has source_text → sourced-but-tailored  → accent (primary-fixed / soft indigo)
 */
function highlightStyle(sourceText: string | null): {
  background: string;
  borderColor: string;
  borderStyle: string;
} {
  if (sourceText === null) {
    // Fabrication: error-container bg + dashed error underline
    return {
      background: "var(--tw-highlight-fabrication-bg, rgba(186,26,26,0.12))",
      borderColor: "var(--color-error, #ba1a1a)",
      borderStyle: "dashed",
    };
  }
  // Sourced-but-tailored: soft primary-fixed bg + solid primary underline
  return {
    background: "var(--tw-highlight-sourced-bg, rgba(226,223,255,0.55))",
    borderColor: "var(--color-primary, #3525cd)",
    borderStyle: "solid",
  };
}

/**
 * Walk all text nodes under `root` and wrap occurrences of `needle`
 * (case-insensitive) with a styled `<mark>` element, calling `onMark` for
 * each injected mark so we can attach event listeners.
 *
 * Returns an array of cleanup functions that restore the original DOM when
 * called (so we can reset before the next highlight pass).
 */
function injectHighlights(
  root: Element,
  needle: string,
  markAttrs: { dataset: Record<string, string>; style: Record<string, string> },
  onMark: (el: HTMLElement) => void,
): (() => void)[] {
  const cleanups: (() => void)[] = [];
  if (!needle.trim()) return cleanups;

  const lower = needle.toLowerCase();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);

  const nodesToProcess: Text[] = [];
  let node: Text | null;
  while ((node = walker.nextNode() as Text | null)) {
    if ((node.textContent ?? "").toLowerCase().includes(lower)) {
      nodesToProcess.push(node);
    }
  }

  for (const textNode of nodesToProcess) {
    const text = textNode.textContent ?? "";
    const lowerText = text.toLowerCase();
    let idx = lowerText.indexOf(lower);
    if (idx === -1) continue;

    const parent = textNode.parentNode;
    if (!parent) continue;

    // Split into before / match / after fragments and replace inline
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    while (idx !== -1) {
      if (idx > cursor) {
        fragment.appendChild(document.createTextNode(text.slice(cursor, idx)));
      }
      const mark = document.createElement("mark");
      mark.textContent = text.slice(idx, idx + needle.length);
      // Apply style
      Object.assign(mark.style, markAttrs.style);
      mark.style.display = "inline";
      mark.style.borderRadius = "2px";
      mark.style.paddingLeft = "2px";
      mark.style.paddingRight = "2px";
      mark.style.borderBottomWidth = "2px";
      mark.style.cursor = "help";
      // Dataset for claim lookup
      for (const [k, v] of Object.entries(markAttrs.dataset)) {
        mark.dataset[k] = v;
      }
      // Tabindex so keyboard users can focus
      mark.setAttribute("tabindex", "0");
      mark.setAttribute("role", "mark");
      onMark(mark);
      fragment.appendChild(mark);
      cursor = idx + needle.length;
      idx = lowerText.indexOf(lower, cursor);
    }
    if (cursor < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(cursor)));
    }

    parent.replaceChild(fragment, textNode);

    // Cleanup: restore original text node
    cleanups.push(() => {
      const current = parent.childNodes;
      // Find the first mark/text node we inserted by dataset
      // Strategy: gather siblings until we reconstruct the original span
      // Simpler: replace the whole parent's inner markup with original text
      // (only safe if parent is a leaf-ish element — for p/li/span this holds)
      // We save the original text and will use it.
      const originalText = text;
      // Walk siblings to find the injected marks and text nodes we added
      const toRemove: ChildNode[] = [];
      let restored = false;
      for (const child of Array.from(current)) {
        if (
          (child instanceof HTMLElement &&
            child.tagName === "MARK" &&
            child.dataset["claimId"] === markAttrs.dataset["claimId"]) ||
          (child instanceof Text &&
            !restored &&
            toRemove.length > 0)
        ) {
          toRemove.push(child);
        }
      }
      if (toRemove.length > 0) {
        const firstNode = toRemove[0];
        parent.insertBefore(document.createTextNode(originalText), firstNode);
        for (const n of toRemove) parent.removeChild(n);
      }
      restored = true;
    });
  }

  return cleanups;
}

/**
 * Renders a markdown artifact with inline drift highlights. Each matched
 * claim_text gets a coloured `<mark>` span; hovering/focusing it shows a
 * tooltip with "Canonical said / Claimed" content.
 *
 * Design reference: 04-jd-pipeline-tailoring.html — error-container+dashed
 * underline for fabrications; primary-fixed+solid underline for sourced claims.
 */
export function InlineDriftHighlight({ source, traces }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState>(null);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || !traces || traces.length === 0) return;

    // Give ReactMarkdown a tick to finish rendering
    const timer = setTimeout(() => {
      const allCleanups: (() => void)[] = [];

      for (const trace of traces) {
        if (!trace.claim_text.trim()) continue;

        const sev = highlightStyle(trace.source_text);

        const markAttrs = {
          dataset: { claimId: trace.claim_id },
          style: {
            backgroundColor: sev.background,
            borderBottomColor: sev.borderColor,
            borderBottomStyle: sev.borderStyle,
          },
        };

        const cleanups = injectHighlights(
          container,
          trace.claim_text,
          markAttrs,
          (mark) => {
            const showTip = () => {
              const rect = mark.getBoundingClientRect();
              setTooltip({
                claimText: trace.claim_text,
                sourceText: trace.source_text,
                anchorRect: rect,
              });
            };
            mark.addEventListener("mouseenter", showTip);
            mark.addEventListener("focus", showTip);
            mark.setAttribute(
              "aria-label",
              trace.source_text
                ? `Drift: claimed "${trace.claim_text}" — canonical said "${trace.source_text}"`
                : `Possible fabrication: "${trace.claim_text}" — no canonical source found`,
            );
            allCleanups.push(() => {
              mark.removeEventListener("mouseenter", showTip);
              mark.removeEventListener("focus", showTip);
            });
          },
        );

        allCleanups.push(...cleanups);
      }

      return () => {
        for (const fn of allCleanups) fn();
      };
    }, 120);

    return () => clearTimeout(timer);
  }, [source, traces]);

  // Close tooltip when mouse leaves the container or Escape pressed
  useLayoutEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setTooltip(null);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="relative" ref={containerRef}>
      <MarkdownRenderer source={source} />

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
  useLayoutEffect(() => {
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
