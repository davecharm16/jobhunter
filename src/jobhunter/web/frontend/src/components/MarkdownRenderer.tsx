import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";

// ---------------------------------------------------------------------------
// Highlight span types (shared with InlineDriftHighlight / InlineJDHighlight)
// ---------------------------------------------------------------------------

/**
 * A single highlight span to be rendered inside markdown text.
 * - kind "drift-sourced"  → indigo bg, solid underline (claim traced to CV)
 * - kind "drift-fabrication" → red bg, dashed underline (no canonical source)
 * - kind "jd-tailored"   → sky-blue bg, dashed primary underline (JD match)
 */
export type HighlightSpan =
  | {
      kind: "drift-sourced" | "drift-fabrication";
      matchText: string;
      claim_text: string;
      source_text: string | null;
    }
  | {
      kind: "jd-tailored";
      matchText: string;
      requirement: string;
    };

export type OnMarkClick =
  | ((span: HighlightSpan, anchorRect: DOMRect) => void)
  | null;

// ---------------------------------------------------------------------------
// Text-splitting utility
// ---------------------------------------------------------------------------

/**
 * Split `text` into an array of React nodes, wrapping every occurrence of
 * any span's `matchText` (case-insensitive) with a <mark> element styled
 * according to the span's `kind`. Overlapping spans are not supported (first
 * match wins). Plain-string segments are left as bare strings so React owns
 * every node and the DOM is never mutated externally.
 */
export function applyHighlightSpans(
  text: string,
  spans: HighlightSpan[],
  onMark: OnMarkClick,
): ReactNode[] {
  if (!spans.length || !text) return [text];

  // Build a list of { start, end, span } from all matches across all spans.
  type Match = { start: number; end: number; span: HighlightSpan };
  const matches: Match[] = [];

  const lowerText = text.toLowerCase();
  for (const span of spans) {
    const needle = span.matchText.toLowerCase();
    if (!needle.trim()) continue;
    let idx = lowerText.indexOf(needle);
    while (idx !== -1) {
      matches.push({ start: idx, end: idx + span.matchText.length, span });
      idx = lowerText.indexOf(needle, idx + needle.length);
    }
  }

  if (!matches.length) return [text];

  // Sort by start position; drop overlapping (earlier match wins).
  matches.sort((a, b) => a.start - b.start || b.end - a.end);
  const resolved: Match[] = [];
  let cursor = 0;
  for (const m of matches) {
    if (m.start < cursor) continue; // overlaps previous match
    resolved.push(m);
    cursor = m.end;
  }

  // Build React node array.
  const nodes: ReactNode[] = [];
  let pos = 0;
  for (let i = 0; i < resolved.length; i++) {
    const m = resolved[i];
    if (m.start > pos) nodes.push(text.slice(pos, m.start));

    const style = spanStyle(m.span);
    const ariaLabel = spanAriaLabel(m.span);
    const matchedText = text.slice(m.start, m.end);

    nodes.push(
      <mark
        key={`hl-${i}`}
        tabIndex={0}
        role="mark"
        aria-label={ariaLabel}
        style={style}
        onMouseEnter={
          onMark
            ? (e) => {
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                onMark(m.span, rect);
              }
            : undefined
        }
        onFocus={
          onMark
            ? (e) => {
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                onMark(m.span, rect);
              }
            : undefined
        }
      >
        {matchedText}
      </mark>,
    );
    pos = m.end;
  }
  if (pos < text.length) nodes.push(text.slice(pos));

  return nodes;
}

function spanStyle(span: HighlightSpan): React.CSSProperties {
  const base: React.CSSProperties = {
    display: "inline",
    borderRadius: "2px",
    paddingLeft: "2px",
    paddingRight: "2px",
    borderBottomWidth: "2px",
    cursor: "help",
  };
  if (span.kind === "drift-fabrication") {
    return {
      ...base,
      backgroundColor: "var(--tw-highlight-fabrication-bg, rgba(186,26,26,0.12))",
      borderBottomColor: "var(--color-error, #ba1a1a)",
      borderBottomStyle: "dashed",
    };
  }
  if (span.kind === "drift-sourced") {
    return {
      ...base,
      backgroundColor: "var(--tw-highlight-sourced-bg, rgba(226,223,255,0.55))",
      borderBottomColor: "var(--color-primary, #3525cd)",
      borderBottomStyle: "solid",
    };
  }
  // jd-tailored
  return {
    ...base,
    backgroundColor: "rgba(218,226,253,0.55)",
    borderBottomColor: "var(--color-primary, #3525cd)",
    borderBottomStyle: "dashed",
  };
}

function spanAriaLabel(span: HighlightSpan): string {
  if (span.kind === "drift-sourced") {
    return `Drift: claimed "${span.claim_text}" — canonical said "${span.source_text}"`;
  }
  if (span.kind === "drift-fabrication") {
    return `Possible fabrication: "${span.claim_text}" — no canonical source found`;
  }
  // kind === "jd-tailored"
  if (span.kind === "jd-tailored") {
    return `Tailored to JD requirement: "${span.requirement}"`;
  }
  return "";
}

// ---------------------------------------------------------------------------
// Recursive children walker
// ---------------------------------------------------------------------------

/**
 * Walk React children recursively and apply highlight spans to any string
 * leaf nodes. Returns a new ReactNode[] with highlights injected — React
 * owns everything, no DOM mutation.
 */
function highlightChildren(
  children: ReactNode,
  spans: HighlightSpan[],
  onMark: OnMarkClick,
): ReactNode {
  if (typeof children === "string") {
    const nodes = applyHighlightSpans(children, spans, onMark);
    return nodes.length === 1 && typeof nodes[0] === "string"
      ? nodes[0]
      : <>{nodes}</>;
  }
  if (Array.isArray(children)) {
    return <>{children.map((child, i) => <span key={i}>{highlightChildren(child, spans, onMark)}</span>)}</>;
  }
  return children;
}

// ---------------------------------------------------------------------------
// Component types
// ---------------------------------------------------------------------------

type MdNode = { children?: ReactNode };
type MdAnchor = MdNode & { href?: string };

type Props = {
  /** Raw markdown — rendered with the library's default safe pipeline. */
  source: string;
  /**
   * Optional highlight spans applied via a custom `react-markdown` text
   * renderer. When omitted the component renders plain markdown with no
   * highlights (identical to the previous behaviour).
   */
  highlightSpans?: HighlightSpan[];
  /**
   * Callback invoked when a highlight mark is hovered or focused.
   * Receives the span descriptor and the mark's bounding rect.
   */
  onMarkActivate?: OnMarkClick;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/** Renders markdown safely (no raw HTML, no scripts) — FR44 trust boundary. */
export function MarkdownRenderer({ source, highlightSpans, onMarkActivate }: Props) {
  const spans = highlightSpans ?? [];
  const onMark = onMarkActivate ?? null;

  // Build a wrapper that applies highlights to an element's text children.
  function hlWrap(children: ReactNode): ReactNode {
    if (!spans.length) return children;
    return highlightChildren(children, spans, onMark);
  }

  return (
    <div className="prose-jh flex flex-col gap-stack-sm text-body-md font-body-md text-on-surface">
      <ReactMarkdown
        // react-markdown 9 disables raw HTML by default — no additional
        // rehype-raw plugin is passed, so model output cannot inject scripts
        // or arbitrary HTML even if it includes `<...>` tags.
        skipHtml
        components={{
          h1: ({ children }: MdNode) => (
            <h1 className="text-headline-lg font-headline-lg text-on-surface mt-stack-md">
              {hlWrap(children)}
            </h1>
          ),
          h2: ({ children }: MdNode) => (
            <h2 className="text-headline-md font-headline-md text-on-surface mt-stack-md">
              {hlWrap(children)}
            </h2>
          ),
          h3: ({ children }: MdNode) => (
            <h3 className="text-body-lg font-body-lg font-semibold text-on-surface mt-stack-sm">
              {hlWrap(children)}
            </h3>
          ),
          p: ({ children }: MdNode) => (
            <p className="text-body-md font-body-md text-on-surface">
              {hlWrap(children)}
            </p>
          ),
          ul: ({ children }: MdNode) => (
            <ul className="list-disc pl-stack-md flex flex-col gap-stack-xs">
              {children}
            </ul>
          ),
          ol: ({ children }: MdNode) => (
            <ol className="list-decimal pl-stack-md flex flex-col gap-stack-xs">
              {children}
            </ol>
          ),
          li: ({ children }: MdNode) => (
            <li className="text-body-md font-body-md text-on-surface">
              {hlWrap(children)}
            </li>
          ),
          strong: ({ children }: MdNode) => (
            <strong className="font-semibold text-on-surface">{hlWrap(children)}</strong>
          ),
          em: ({ children }: MdNode) => (
            <em className="italic text-on-surface">{hlWrap(children)}</em>
          ),
          a: ({ href, children }: MdAnchor) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline hover:text-primary-container"
            >
              {children}
            </a>
          ),
          code: ({ children }: MdNode) => (
            <code className="bg-surface-container-low border border-outline-variant rounded px-1 text-body-md font-body-md">
              {children}
            </code>
          ),
          pre: ({ children }: MdNode) => (
            <pre className="bg-surface-container-low border border-outline-variant rounded-lg p-stack-sm overflow-x-auto text-body-md font-body-md">
              {children}
            </pre>
          ),
          blockquote: ({ children }: MdNode) => (
            <blockquote className="border-l-4 border-outline-variant pl-stack-sm text-body-md font-body-md text-on-surface-variant italic">
              {hlWrap(children)}
            </blockquote>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
