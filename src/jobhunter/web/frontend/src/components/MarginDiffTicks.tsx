import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shape of a single unsourced claim from the drift endpoint.
 * Mirrors the `UnsourcedClaim` type in DriftPage.tsx.
 */
export type UnsourcedClaim = {
  claim_id: string;
  claim_text: string;
  source_artifact: string;
  line_number: number;
  reason: string;
};

type Props = {
  /**
   * Fabrication-flagged claims to highlight.  When empty or undefined the
   * component renders nothing (graceful degradation).
   */
  claims: UnsourcedClaim[] | undefined;
  /**
   * Ref to the container element wrapping the MarkdownRenderer output.
   * The ticks are positioned absolutely relative to this container.
   */
  containerRef: React.RefObject<HTMLDivElement | null>;
};

type TickPosition = {
  claim: UnsourcedClaim;
  top: number;
  height: number;
};

/**
 * Renders thin blue vertical tick indicators in the left margin of the
 * markdown preview for every paragraph / list-item that contains a
 * fabrication-flagged claim (substring match).
 *
 * Clicking a tick shows a popover with the claim text, reason, and a
 * dismiss button that hides the tick for the current session.
 */
export function MarginDiffTicks({ claims, containerRef }: Props) {
  const [ticks, setTicks] = useState<TickPosition[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [activeClaim, setActiveClaim] = useState<string | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Scan rendered HTML for matching text nodes
  const scanForMatches = useCallback(() => {
    if (!claims || claims.length === 0 || !containerRef.current) {
      setTicks([]);
      return;
    }

    const container = containerRef.current;
    // Collect all <p> and <li> elements inside the rendered markdown
    const elements = container.querySelectorAll("p, li");
    const results: TickPosition[] = [];
    const containerRect = container.getBoundingClientRect();

    for (const claim of claims) {
      if (dismissed.has(claim.claim_id)) continue;

      const needle = claim.claim_text.toLowerCase();
      for (const el of elements) {
        const text = (el.textContent ?? "").toLowerCase();
        if (text.includes(needle)) {
          const elRect = el.getBoundingClientRect();
          results.push({
            claim,
            top: elRect.top - containerRect.top,
            height: elRect.height,
          });
          break; // one tick per claim
        }
      }
    }

    setTicks(results);
  }, [claims, containerRef, dismissed]);

  // Re-scan on mount, claim changes, or dismissals
  useEffect(() => {
    // Small delay so the markdown has rendered
    const timer = setTimeout(scanForMatches, 100);
    return () => clearTimeout(timer);
  }, [scanForMatches]);

  // Close popover when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node)
      ) {
        setActiveClaim(null);
      }
    }
    if (activeClaim) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [activeClaim]);

  if (!claims || claims.length === 0 || ticks.length === 0) {
    return null;
  }

  return (
    <>
      {ticks.map((tick) => (
        <div
          key={tick.claim.claim_id}
          className="absolute left-0 w-[3px] rounded-full cursor-pointer transition-opacity hover:opacity-80"
          style={{
            top: tick.top,
            height: tick.height,
            backgroundColor: "var(--color-accent)",
          }}
          onClick={() =>
            setActiveClaim(
              activeClaim === tick.claim.claim_id
                ? null
                : tick.claim.claim_id,
            )
          }
          title="Fabrication flag — click for details"
          role="button"
          aria-label={`Fabrication flag: ${tick.claim.claim_text.slice(0, 60)}`}
        >
          {activeClaim === tick.claim.claim_id && (
            <div
              ref={popoverRef}
              className="absolute left-3 top-0 z-50 w-72 rounded-lg border border-outline-variant bg-surface-container-lowest shadow-lg p-stack-sm"
              style={{ fontFamily: "var(--font-ui)" }}
            >
              <p className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs">
                Fabrication flag
              </p>
              <p className="text-body-md font-body-md text-on-surface mb-stack-xs break-words">
                {tick.claim.claim_text}
              </p>
              <p className="text-label-md text-on-surface-variant mb-stack-sm break-words">
                <code
                  className="bg-surface-container-low border border-outline-variant rounded px-1"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {tick.claim.reason}
                </code>
              </p>
              <button
                type="button"
                className="text-label-md font-label-md uppercase tracking-wider text-primary hover:text-primary-container transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  setDismissed((prev) => {
                    const next = new Set(prev);
                    next.add(tick.claim.claim_id);
                    return next;
                  });
                  setActiveClaim(null);
                }}
              >
                Dismiss
              </button>
            </div>
          )}
        </div>
      ))}
    </>
  );
}
