import { useRef, useState } from "react";
import { InlineDriftHighlight, type DriftTrace } from "./InlineDriftHighlight";
import { JDTooltip, useJDHighlights, type JDMustHave } from "./InlineJDHighlight";

type Props = {
  /** Raw markdown source */
  source: string;
  /** Drift traces from the fabrication-check endpoint */
  traces: DriftTrace[];
  /** JD must-have requirements for positive tailoring highlights */
  mustHaves: JDMustHave[];
};

/**
 * Combines drift highlights (InlineDriftHighlight) and JD-tailoring highlights
 * (useJDHighlights) on the same rendered markdown.
 *
 * InlineDriftHighlight manages its own inner div and ref. We wrap it in an
 * outer div and run JD highlights on the outer div, which covers the inner
 * content via the DOM walker — the TreeWalker recurses into all descendants.
 *
 * Timing: drift runs at 120ms, JD runs at 160ms, so drift marks are in the
 * DOM before JD walks it. JD highlights will highlight text inside drift
 * <mark> elements if a must-have phrase overlaps a drift claim — this is
 * acceptable (two layers of highlight). Each cleanup is independent.
 */
export function DriftAndJDHighlight({ source, traces, mustHaves }: Props) {
  const outerRef = useRef<HTMLDivElement>(null);
  const [jdTooltip, setJdTooltip] = useState<{
    requirement: string;
    anchorRect: DOMRect;
  } | null>(null);

  useJDHighlights(outerRef, mustHaves, source, setJdTooltip);

  return (
    <div ref={outerRef} className="relative">
      <InlineDriftHighlight source={source} traces={traces} />
      {jdTooltip && (
        <JDTooltip tooltip={jdTooltip} onClose={() => setJdTooltip(null)} />
      )}
    </div>
  );
}
