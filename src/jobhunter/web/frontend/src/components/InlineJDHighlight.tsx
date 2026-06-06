import { RefObject, useLayoutEffect, useRef, useState } from "react";
import { MarkdownRenderer } from "./MarkdownRenderer";

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
 * JD-tailoring highlight style — secondary-container (sky blue) bg with a
 * dashed primary underline. Visually distinct from drift highlights:
 * - Drift sourced: primary-fixed (soft indigo), solid underline
 * - Drift fabrication: error-container (red), dashed underline
 * - JD tailored (this): secondary-container (blue), dashed primary underline
 */
const TAILORING_STYLE = {
  backgroundColor: "rgba(218,226,253,0.55)", // secondary-container @ 55%
  borderBottomColor: "var(--color-primary, #3525cd)",
  borderBottomStyle: "dashed" as const,
  borderBottomWidth: "2px",
  display: "inline",
  borderRadius: "2px",
  paddingLeft: "2px",
  paddingRight: "2px",
  cursor: "help",
};

function injectKeywordHighlights(
  root: Element,
  needle: string,
  requirement: string,
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

    const fragment = document.createDocumentFragment();
    let cursor = 0;
    while (idx !== -1) {
      if (idx > cursor) {
        fragment.appendChild(document.createTextNode(text.slice(cursor, idx)));
      }
      const mark = document.createElement("mark");
      mark.textContent = text.slice(idx, idx + needle.length);
      Object.assign(mark.style, TAILORING_STYLE);
      mark.dataset["jdRequirement"] = requirement;
      mark.dataset["jdNeedle"] = needle;
      mark.setAttribute("tabindex", "0");
      mark.setAttribute("role", "mark");
      mark.setAttribute(
        "aria-label",
        `Tailored to JD requirement: "${requirement}"`,
      );
      onMark(mark);
      fragment.appendChild(mark);
      cursor = idx + needle.length;
      idx = lowerText.indexOf(lower, cursor);
    }
    if (cursor < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(cursor)));
    }

    parent.replaceChild(fragment, textNode);

    cleanups.push(() => {
      const current = Array.from(parent.childNodes);
      const toRemove: ChildNode[] = [];
      for (const child of current) {
        if (
          child instanceof HTMLElement &&
          child.tagName === "MARK" &&
          child.dataset["jdNeedle"] === needle
        ) {
          toRemove.push(child);
        }
      }
      if (toRemove.length > 0) {
        const firstNode = toRemove[0];
        parent.insertBefore(document.createTextNode(text), firstNode);
        for (const n of toRemove) parent.removeChild(n);
      }
    });
  }

  return cleanups;
}

function buildNeedles(requirement: string): string[] {
  const phrase = requirement.trim().replace(/[.,;:!?]+$/, "").trim();
  if (phrase.length === 0) return [];
  return [phrase];
}

/**
 * Hook: run JD must-have highlights on an externally-managed container.
 * Use this when the container is already rendered by another component
 * (e.g. InlineDriftHighlight). `setTooltip` is a setter for the caller's
 * tooltip state; pass null to disable tooltips from this hook.
 */
export function useJDHighlights(
  containerRef: RefObject<Element | null>,
  mustHaves: JDMustHave[] | undefined,
  source: string,
  setTooltip: (t: TooltipState) => void,
): void {
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container || !mustHaves || mustHaves.length === 0) return;

    // Run at 160ms — after InlineDriftHighlight (120ms) so JD marks render on
    // top of drift marks without interfering with drift's cleanup.
    const timer = setTimeout(() => {
      const allCleanups: (() => void)[] = [];

      for (const requirement of mustHaves) {
        const needles = buildNeedles(requirement);
        for (const needle of needles) {
          const cleanups = injectKeywordHighlights(
            container,
            needle,
            requirement,
            (mark) => {
              const showTip = () => {
                const rect = mark.getBoundingClientRect();
                setTooltip({ requirement, anchorRect: rect });
              };
              mark.addEventListener("mouseenter", showTip);
              mark.addEventListener("focus", showTip);
              allCleanups.push(() => {
                mark.removeEventListener("mouseenter", showTip);
                mark.removeEventListener("focus", showTip);
              });
            },
          );
          allCleanups.push(...cleanups);
        }
      }

      return () => {
        for (const fn of allCleanups) fn();
      };
    }, 160);

    return () => clearTimeout(timer);
  }, [source, mustHaves, containerRef, setTooltip]);
}

/**
 * Standalone component: renders markdown + JD-tailoring highlights.
 *
 * When drift highlights are also needed, use InlineDriftHighlight as the base
 * and add the `useJDHighlights` hook on its container ref instead — see
 * the DriftAndJDHighlight wrapper below.
 */
export function InlineJDHighlight({ source, mustHaves }: StandaloneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState>(null);

  useJDHighlights(containerRef, mustHaves, source, setTooltip);

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

  useLayoutEffect(() => {
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
