import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  DriftSection,
  type DriftVerdict,
} from "./components/DriftSection";

// The drift.json shape mirrors `jobhunter.fabrication_matcher.FabricationCheck`
// at the wire. Stories 4.4 + 5.4 will add sibling keys (`content_loss`,
// `keyword_stuffing`); the type permits but does not require them today.
type Trace = {
  claim_id: string;
  claim_text: string;
  matched_canonical_entry_id: string;
  match_method: "exact_string" | "substring" | "semantic";
  match_score: number;
};

type UnsourcedClaim = {
  claim_id: string;
  claim_text: string;
  source_artifact: string;
  line_number: number;
  reason: string;
};

type FabricationCheck = {
  verdict: "pass" | "fail";
  claims_total: number;
  claims_sourced: number;
  claims_unsourced: number;
  traces: Trace[];
  unsourced_claims: UnsourcedClaim[];
};

type DriftDocument = {
  fabrication_check?: FabricationCheck;
  content_loss?: unknown;
  keyword_stuffing?: unknown;
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; payload: DriftDocument }
  | { kind: "error"; status: number | null; message: string };

function fabricationVerdict(doc: DriftDocument): DriftVerdict {
  const fab = doc.fabrication_check;
  if (!fab) return "unknown";
  return fab.verdict;
}

function FabricationContent({ check }: { check: FabricationCheck }) {
  if (check.verdict === "pass") {
    return (
      <div className="rounded-lg border border-outline-variant bg-surface p-stack-md flex flex-col gap-stack-xs">
        <p className="text-body-md font-body-md text-on-surface">
          No fabricated claims detected.
        </p>
        <p className="text-label-md font-label-md text-on-surface-variant">
          Every one of the {check.claims_total} extracted claim
          {check.claims_total === 1 ? "" : "s"} traces back to a canonical-CV
          entry.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-stack-md">
      <p className="text-body-md font-body-md text-on-surface-variant">
        {check.claims_unsourced} of {check.claims_total} claim
        {check.claims_total === 1 ? "" : "s"} could not be traced back to the
        canonical CV.
      </p>
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
                <code className="font-mono text-on-surface">
                  {claim.source_artifact}
                </code>
              </span>
              <span>
                <span className="uppercase tracking-wider">Line:</span>{" "}
                <code className="font-mono text-on-surface">
                  {claim.line_number}
                </code>
              </span>
              <span>
                <span className="uppercase tracking-wider">Claim ID:</span>{" "}
                <code className="font-mono text-on-surface">
                  {claim.claim_id}
                </code>
              </span>
            </div>
            <details className="group rounded-lg border border-outline-variant bg-surface-container-lowest mt-stack-xs">
              <summary className="cursor-pointer list-none px-stack-md py-stack-sm text-label-md font-label-md uppercase tracking-wider text-on-surface-variant focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg hover:text-primary group-open:text-primary flex items-center justify-between">
                <span>Near-miss detail</span>
                <span className="text-label-md font-label-md group-open:hidden">
                  expand
                </span>
                <span className="text-label-md font-label-md hidden group-open:inline">
                  collapse
                </span>
              </summary>
              <div className="px-stack-md pb-stack-md text-body-md font-body-md text-on-surface-variant">
                <p>
                  <span className="uppercase tracking-wider text-label-md">
                    Reason:
                  </span>{" "}
                  <code className="font-mono text-on-surface">
                    {claim.reason}
                  </code>
                </p>
                <p className="mt-stack-xs italic">
                  Candidate canonical-CV near-misses will be surfaced here once
                  the matcher emits them (future enhancement to
                  package.drift.json).
                </p>
              </div>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PlaceholderContent({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-outline-variant bg-surface p-stack-md">
      <p className="text-body-md font-body-md text-on-surface-variant italic">
        {label} pending — not yet implemented.
      </p>
    </div>
  );
}

export function DriftPage() {
  const { slug } = useParams<{ slug: string }>();
  const [fetchState, setFetchState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    if (!slug) {
      setFetchState({
        kind: "error",
        status: null,
        message: "missing_slug_in_route",
      });
      return;
    }
    setFetchState({ kind: "loading" });
    async function load() {
      try {
        const response = await fetch(
          `/api/package/${encodeURIComponent(slug!)}/drift`,
        );
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          const message =
            typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
          setFetchState({
            kind: "error",
            status: response.status,
            message,
          });
          return;
        }
        setFetchState({ kind: "ready", payload: body as DriftDocument });
      } catch (exc) {
        if (cancelled) return;
        setFetchState({
          kind: "error",
          status: null,
          message: String(exc),
        });
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (fetchState.kind === "loading") {
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
        <p className="text-body-md font-body-md text-on-surface-variant">
          Loading drift report...
        </p>
      </div>
    );
  }

  if (fetchState.kind === "error") {
    const is404 = fetchState.status === 404;
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full flex flex-col gap-stack-md">
        <div className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
          {is404 ? (
            <>
              No drift report exists for package{" "}
              <code className="font-mono">{slug}</code>. This is normal for
              packages staged before the fabrication matcher landed (Epic 1
              walking-skeleton runs).
            </>
          ) : (
            <>Failed to load drift report: {fetchState.message}</>
          )}
        </div>
        <div className="flex gap-stack-md">
          <Link
            to={`/packages/${slug ?? ""}`}
            className="text-primary underline text-body-md font-body-md"
          >
            Back to package
          </Link>
          <Link
            to="/"
            className="text-primary underline text-body-md font-body-md"
          >
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  const { payload } = fetchState;
  const fabrication = payload.fabrication_check;
  const fabVerdict = fabricationVerdict(payload);

  return (
    <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      <header className="flex flex-col gap-stack-xs">
        <div className="flex items-center gap-stack-sm text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
          <Link to="/" className="hover:text-primary">
            Dashboard
          </Link>
          <span>/</span>
          <Link
            to={`/packages/${slug ?? ""}`}
            className="hover:text-primary"
          >
            {slug}
          </Link>
          <span>/</span>
          <span>Drift</span>
        </div>
        <h1 className="text-display font-display text-on-surface break-words">
          Drift Check Diagnostics
        </h1>
        <p className="text-body-lg font-body-lg text-on-surface-variant max-w-2xl">
          Per-claim traceability between the tailored output and your canonical
          CV. Fabrication detection is live; content-loss and keyword-stuffing
          land in Epics 4 and 5.
        </p>
      </header>

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

        <DriftSection title="Content Loss" verdict="pending">
          <PlaceholderContent label="Content-loss diagnostics (Story 4.4)" />
        </DriftSection>

        <DriftSection title="Keyword Stuffing" verdict="pending">
          <PlaceholderContent label="Keyword-stuffing diagnostics (Story 5.4)" />
        </DriftSection>
      </div>
    </div>
  );
}
