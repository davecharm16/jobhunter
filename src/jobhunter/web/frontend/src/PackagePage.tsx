import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import {
  MetadataSidebar,
  type PackageMetadata,
} from "./components/MetadataSidebar";

type PackagePayload = {
  slug: string;
  jd_text: string | null;
  cv_markdown: string | null;
  cover_letter_markdown: string | null;
  upwork_proposal_markdown: string | null;
  metadata: PackageMetadata;
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; payload: PackagePayload }
  | { kind: "error"; status: number | null; message: string };

type ArtifactTab = "cv" | "letter" | "proposal";

function isUpwork(payload: PackagePayload): boolean {
  return (payload.metadata.source_board ?? "").toLowerCase() === "upwork";
}

function pickDefaultTab(payload: PackagePayload): ArtifactTab {
  if (isUpwork(payload) && payload.upwork_proposal_markdown) return "proposal";
  if (payload.cv_markdown) return "cv";
  if (payload.cover_letter_markdown) return "letter";
  if (payload.upwork_proposal_markdown) return "proposal";
  return "cv";
}

export function PackagePage() {
  const { slug } = useParams<{ slug: string }>();
  const [fetchState, setFetchState] = useState<FetchState>({ kind: "loading" });
  const [activeTab, setActiveTab] = useState<ArtifactTab>("cv");

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
          `/api/package/${encodeURIComponent(slug!)}`,
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
        const payload = body as PackagePayload;
        setFetchState({ kind: "ready", payload });
        setActiveTab(pickDefaultTab(payload));
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

  const tabs = useMemo(() => {
    if (fetchState.kind !== "ready") return [];
    const out: Array<{ key: ArtifactTab; label: string; available: boolean }> = [
      {
        key: "cv",
        label: "Tailored CV",
        available: Boolean(fetchState.payload.cv_markdown),
      },
      {
        key: "letter",
        label: "Cover Letter",
        available: Boolean(fetchState.payload.cover_letter_markdown),
      },
    ];
    if (isUpwork(fetchState.payload) || fetchState.payload.upwork_proposal_markdown) {
      out.push({
        key: "proposal",
        label: "Upwork Proposal",
        available: Boolean(fetchState.payload.upwork_proposal_markdown),
      });
    }
    return out;
  }, [fetchState]);

  if (fetchState.kind === "loading") {
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
        <p className="text-body-md font-body-md text-on-surface-variant">
          Loading package...
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
              Package <code className="font-mono">{slug}</code> was not found.
            </>
          ) : (
            <>Failed to load package: {fetchState.message}</>
          )}
        </div>
        <Link
          to="/"
          className="text-primary underline text-body-md font-body-md"
        >
          Back to dashboard
        </Link>
      </div>
    );
  }

  const { payload } = fetchState;
  const board = payload.metadata.source_board ?? "unknown";
  const parsed = payload.metadata.parsed_jd ?? {};
  const driftVerdicts = payload.metadata.drift_verdicts ?? {};
  const fabricationFailed = driftVerdicts.fabrication === "fail";
  const driftLinkClass = fabricationFailed
    ? "inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg bg-primary text-on-primary text-body-md font-body-md font-medium hover:bg-primary/90 transition-colors"
    : "inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg border border-outline-variant text-body-md font-body-md text-on-surface-variant hover:text-primary hover:border-primary transition-colors";

  const activeArtifact =
    activeTab === "cv"
      ? payload.cv_markdown
      : activeTab === "letter"
        ? payload.cover_letter_markdown
        : payload.upwork_proposal_markdown;

  return (
    <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
      <header className="flex flex-col gap-stack-xs">
        <div className="flex items-center gap-stack-sm text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
          <Link to="/" className="hover:text-primary">
            Dashboard
          </Link>
          <span>/</span>
          <span>Packages</span>
        </div>
        <h1 className="text-display font-display text-on-surface break-words">
          {payload.slug}
        </h1>
        <p className="text-body-md font-body-md text-on-surface-variant">
          Source board: <span className="font-medium">{board}</span>
        </p>
        <div className="mt-stack-sm">
          <Link
            to={`/packages/${encodeURIComponent(payload.slug)}/drift`}
            className={driftLinkClass}
            aria-label={
              fabricationFailed
                ? "View drift diagnostics (fabrication failed)"
                : "View drift diagnostics"
            }
          >
            View drift diagnostics
            {fabricationFailed && (
              <span className="text-label-md font-label-md uppercase tracking-wider">
                fabrication fail
              </span>
            )}
          </Link>
        </div>
      </header>

      <div className="flex flex-col lg:flex-row gap-gutter">
        <section className="lg:w-1/3 flex flex-col gap-stack-md">
          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-md shadow-sm flex flex-col gap-stack-sm">
            <h2 className="text-headline-md font-headline-md text-on-surface">
              Job Description
            </h2>
            {payload.jd_text ? (
              <pre className="whitespace-pre-wrap break-words text-body-md font-body-md text-on-surface bg-surface rounded-lg p-stack-sm border border-outline-variant max-h-[480px] overflow-y-auto">
                {payload.jd_text}
              </pre>
            ) : (
              <p className="text-body-md font-body-md text-on-surface-variant italic">
                JD text was not persisted for this package. (Story 1.5 did not
                capture raw JD text; future stories will backfill.)
              </p>
            )}
          </div>

          {parsed.must_haves && parsed.must_haves.length > 0 && (
            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-md shadow-sm flex flex-col gap-stack-sm">
              <h3 className="text-body-lg font-body-lg font-semibold text-on-surface">
                Must-haves
              </h3>
              <ul className="flex flex-col gap-stack-xs">
                {parsed.must_haves.map((item, idx) => (
                  <li
                    key={idx}
                    className="text-body-md font-body-md text-on-surface"
                  >
                    - {item}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="flex-1 flex flex-col bg-surface-container-lowest border border-outline-variant rounded-xl shadow-sm overflow-hidden min-h-[320px]">
          <div className="flex border-b border-outline-variant bg-surface-container-low">
            {tabs.map((tab) => {
              const active = tab.key === activeTab;
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  disabled={!tab.available}
                  className={
                    active
                      ? "px-stack-lg py-stack-sm text-body-md font-body-md font-semibold text-primary border-b-2 border-primary bg-surface-container-lowest disabled:opacity-50"
                      : "px-stack-lg py-stack-sm text-body-md font-body-md text-on-surface-variant hover:bg-surface-container-high border-b-2 border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                  }
                >
                  {tab.label}
                </button>
              );
            })}
            <div className="ml-auto flex items-center px-stack-md">
              <span className="text-label-md font-label-md text-on-surface-variant border border-outline-variant rounded-lg px-stack-sm py-stack-xs">
                Drift Check Active
              </span>
            </div>
          </div>

          <div className="flex-1 p-stack-lg overflow-y-auto bg-surface-container-lowest">
            {activeArtifact ? (
              <MarkdownRenderer source={activeArtifact} />
            ) : (
              <p className="text-body-md font-body-md text-on-surface-variant italic">
                This artifact is not present in the staged package.
              </p>
            )}
          </div>
        </section>

        <MetadataSidebar metadata={payload.metadata} />
      </div>
    </div>
  );
}
