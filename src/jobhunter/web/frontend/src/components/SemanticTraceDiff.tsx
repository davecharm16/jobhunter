/**
 * SemanticTraceDiff — Story gaps 05-4, 05-5, 05-11, 05-12
 *
 * Two-column split-pane viewer that renders the canonical CV source on the
 * left and the tailored claim on the right with a word-level color-coded diff.
 *
 * Red   = words present in canonical but absent from the tailored claim
 * Green = words present in tailored claim but absent from canonical
 *
 * Implementation: hand-rolled LCS-based word-level diff. No extra npm deps.
 * Character-level diffs within long prose aren't necessary here; word-level
 * highlight gives enough granularity to make fabrication alerts actionable.
 */

type DiffOp = "equal" | "remove" | "insert";

interface DiffToken {
  text: string;
  op: DiffOp;
}

/** Tokenise text into words + whitespace runs so spaces round-trip cleanly. */
function tokenise(text: string): string[] {
  // Split on whitespace boundaries while keeping the whitespace as its own
  // token — this lets us reconstruct the text faithfully.
  return text.split(/(\s+)/);
}

/**
 * Build a split-diff result: separate token lists for left pane and right pane.
 */
function splitDiff(
  sourceText: string,
  claimText: string,
): { leftTokens: DiffToken[]; rightTokens: DiffToken[] } {
  const L = tokenise(sourceText);
  const R = tokenise(claimText);

  const m = L.length;
  const n = R.length;

  if (m > 2000 || n > 2000) {
    // Fallback: no diffing
    return {
      leftTokens: [{ text: sourceText, op: "equal" }],
      rightTokens: [{ text: claimText, op: "equal" }],
    };
  }

  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0),
  );
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (L[i - 1] === R[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  const leftOps: DiffToken[] = [];
  const rightOps: DiffToken[] = [];
  let i = m;
  let j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && L[i - 1] === R[j - 1]) {
      leftOps.push({ text: L[i - 1], op: "equal" });
      rightOps.push({ text: R[j - 1], op: "equal" });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      rightOps.push({ text: R[j - 1], op: "insert" });
      j--;
    } else {
      leftOps.push({ text: L[i - 1], op: "remove" });
      i--;
    }
  }

  leftOps.reverse();
  rightOps.reverse();

  return { leftTokens: leftOps, rightTokens: rightOps };
}

/** Render a sequence of DiffTokens as inline spans with appropriate styling. */
function DiffSpans({ tokens }: { tokens: DiffToken[] }) {
  return (
    <>
      {tokens.map((tok, idx) => {
        if (tok.op === "remove") {
          return (
            <span
              key={idx}
              className="bg-error-container text-on-error-container line-through rounded-sm px-[1px]"
            >
              {tok.text}
            </span>
          );
        }
        if (tok.op === "insert") {
          return (
            <strong
              key={idx}
              className="bg-[#dcfce7] text-[#14532d] rounded-sm px-[1px] font-semibold underline decoration-[#14532d]/50"
            >
              {tok.text}
            </strong>
          );
        }
        // equal — plain text, preserve whitespace
        return <span key={idx}>{tok.text}</span>;
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

type Props = {
  /** The claim text from the tailored output (right pane). */
  claimText: string;
  /**
   * The original canonical-CV text that was matched (left pane).
   * When null this is an unsourced / potentially fabricated claim.
   */
  sourceText: string | null;
  /** Unique id used for accessible region labelling. */
  traceId: string;
  /**
   * When true, renders the colour-coding legend in the diff header.
   * Defaults to false so callers that render a viewer-level legend once
   * (e.g. TraceDiffList / DriftPage) avoid repeating it per instance.
   */
  showLegend?: boolean;
};

export function SemanticTraceDiff({
  claimText,
  sourceText,
  traceId,
  showLegend = false,
}: Props) {
  const hasSource = sourceText !== null && sourceText !== undefined;

  const { leftTokens, rightTokens } = hasSource
    ? splitDiff(sourceText!, claimText)
    : {
        leftTokens: [] as DiffToken[],
        rightTokens: [{ text: claimText, op: "equal" as DiffOp }],
      };

  return (
    <div
      className="rounded-lg border border-outline-variant overflow-hidden"
      role="region"
      aria-label={`Semantic trace diff ${traceId}`}
    >
      {/* Diff viewer header — label + optional legend */}
      <div className="flex items-center justify-between gap-stack-md px-stack-md py-stack-sm bg-surface-container-low border-b border-outline-variant flex-wrap gap-y-stack-xs">
        <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
          Semantic Trace Diff
        </span>
        {showLegend && (
          <div className="flex items-center gap-stack-md text-label-md font-label-md text-on-surface-variant">
            <span className="flex items-center gap-stack-xs">
              <span className="inline-block w-3 h-3 rounded-sm bg-error-container border border-error/30" />
              <span>− removed</span>
            </span>
            <span className="flex items-center gap-stack-xs">
              <strong className="inline-block w-3 h-3 rounded-sm bg-[#dcfce7] border border-[#86efac]" />
              <span>+ added</span>
            </span>
          </div>
        )}
      </div>

      {/* Split panes */}
      <div className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-outline-variant bg-surface-container-lowest min-h-[4rem]">
        {/* Left pane — Canonical source */}
        <div className="p-stack-md flex flex-col gap-stack-xs overflow-x-auto">
          <span className="inline-block text-label-md font-label-md uppercase tracking-wider text-on-surface-variant bg-surface-container-highest px-stack-xs py-[2px] rounded-sm self-start">
            canonical-cv
          </span>
          <div className="font-mono text-body-md font-body-md text-on-surface-variant leading-relaxed whitespace-pre-wrap break-words">
            {hasSource ? (
              <DiffSpans tokens={leftTokens} />
            ) : (
              <span className="inline-flex items-center gap-stack-xs text-error italic">
                <span
                  className="inline-block w-2 h-2 rounded-full bg-error shrink-0"
                  aria-hidden="true"
                />
                No canonical source — possible fabrication
              </span>
            )}
          </div>
        </div>

        {/* Right pane — Tailored claim */}
        <div className="p-stack-md flex flex-col gap-stack-xs overflow-x-auto">
          <span className="inline-block text-label-md font-label-md uppercase tracking-wider text-on-surface bg-secondary-container px-stack-xs py-[2px] rounded-sm self-start">
            cv.md
          </span>
          <div className="font-mono text-body-md font-body-md text-on-surface-variant leading-relaxed whitespace-pre-wrap break-words">
            <DiffSpans tokens={rightTokens} />
          </div>
        </div>
      </div>
    </div>
  );
}

