import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApproveOverrideModal } from "./components/ApproveOverrideModal";
import { MarkdownRenderer } from "./components/MarkdownRenderer";
import {
  MarginDiffTicks,
  type UnsourcedClaim,
} from "./components/MarginDiffTicks";
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
  metadata: PackageMetadata & { held?: boolean };
};

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; payload: PackagePayload }
  | { kind: "error"; status: number | null; message: string };

type ArtifactTab = "cv" | "letter" | "proposal";

/* ── Drift data (for fabrication margin ticks) ────────────────────── */
type DriftFabricationCheck = {
  verdict: "pass" | "fail";
  unsourced_claims: UnsourcedClaim[];
};

type DriftDocument = {
  fabrication_check?: DriftFabricationCheck;
};

/* ── Toast flash ──────────────────────────────────────────────────── */
type Toast = { id: number; message: string };

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
  // Story 6.4: local UI state for the Approve action. `overrideApplied`
  // is the optimistic flip after a 200 OK from `/api/override/<slug>` so
  // the badge + button disappear without a full page refetch. `note`
  // surfaces the server's "Open ./out/_overridden/..." reminder.
  const [modalOpen, setModalOpen] = useState(false);
  const [overrideApplied, setOverrideApplied] = useState(false);
  const [overrideNote, setOverrideNote] = useState<string | null>(null);
  // Story 8.3: drift data for fabrication margin ticks
  const [driftClaims, setDriftClaims] = useState<UnsourcedClaim[]>([]);
  // Story 8.3: toast flash for copy/download feedback
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastIdRef = useRef(0);
  // Story 8.3: ref for the markdown preview wrapper (MarginDiffTicks)
  const previewRef = useRef<HTMLDivElement>(null);

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

  // Story 8.3: fetch drift data for fabrication margin ticks
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    async function loadDrift() {
      try {
        const res = await fetch(
          `/api/package/${encodeURIComponent(slug!)}/drift`,
        );
        if (!res.ok || cancelled) return; // 404 / error: graceful degradation
        const body = (await res.json()) as DriftDocument;
        if (cancelled) return;
        const claims = body.fabrication_check?.unsourced_claims ?? [];
        setDriftClaims(claims);
      } catch {
        // Drift data unavailable — no ticks, no error
      }
    }
    loadDrift();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Story 8.3: toast flash helper
  const showToast = useCallback((message: string) => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 2000);
  }, []);

  // Story 8.3: copy markdown to clipboard
  const handleCopy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        showToast("Copied!");
      } catch {
        showToast("Copy failed — check browser permissions.");
      }
    },
    [showToast],
  );

  // Story 8.3: download markdown as .md file
  const handleDownloadMd = useCallback(
    (text: string, filename: string) => {
      const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast(`Downloaded ${filename}`);
    },
    [showToast],
  );

  // Story 8.3: download PDF from backend
  const handleDownloadPdf = useCallback(
    async (pdfName: string) => {
      if (!slug) return;
      try {
        const res = await fetch(
          `/api/package/${encodeURIComponent(slug)}/download/${pdfName}`,
        );
        if (res.status === 501 || res.status === 404) {
          showToast("PDF generation not available yet.");
          return;
        }
        if (!res.ok) {
          showToast(`PDF download failed (${res.status}).`);
          return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = pdfName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast(`Downloaded ${pdfName}`);
      } catch {
        showToast("PDF generation not available yet.");
      }
    },
    [slug, showToast],
  );

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
  // Story 6.4: a package is held until either the server-side `held` flag
  // says so OR the optimistic flag from a successful override flips it
  // off. Both conditions OR together so the Approve button hides as soon
  // as the modal reports success, even before the next route load.
  const isHeld = (payload.metadata.held ?? false) && !overrideApplied;
  const driftLinkClass = fabricationFailed
    ? "inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg bg-primary text-on-primary text-body-md font-body-md font-medium hover:bg-primary/90 transition-colors"
    : "inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg border border-outline-variant text-body-md font-body-md text-on-surface-variant hover:text-primary hover:border-primary transition-colors";

  const activeArtifact =
    activeTab === "cv"
      ? payload.cv_markdown
      : activeTab === "letter"
        ? payload.cover_letter_markdown
        : payload.upwork_proposal_markdown;

  // Story 8.3: filenames for download actions
  const mdFilename =
    activeTab === "cv"
      ? "cv.md"
      : activeTab === "letter"
        ? "cover-letter.md"
        : "upwork-proposal.md";
  const pdfFilename =
    activeTab === "cv"
      ? "cv.pdf"
      : activeTab === "letter"
        ? "cover-letter.pdf"
        : "upwork-proposal.pdf";

  // Story 8.3: only show fabrication ticks on the CV tab
  const activeClaims = activeTab === "cv" ? driftClaims : [];

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
        <h1
          className="text-display font-display text-on-surface break-words"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {payload.slug}
        </h1>
        <p className="text-body-md font-body-md text-on-surface-variant">
          Source board: <span className="font-medium">{board}</span>
        </p>
        <div className="mt-stack-sm flex flex-wrap items-center gap-stack-sm">
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
          {isHeld && (
            <>
              <span
                className="inline-flex items-center px-stack-sm py-stack-xs rounded-full border border-error bg-error-container text-on-error-container text-label-md font-label-md uppercase tracking-wider"
                aria-label="Package is held"
              >
                Held
              </span>
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                aria-label="Approve override for this package"
                className="inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg bg-primary text-on-primary text-body-md font-body-md font-medium hover:bg-primary/90 transition-colors"
              >
                Approve override
              </button>
            </>
          )}
        </div>
        {overrideApplied && overrideNote && (
          <div
            role="status"
            className="mt-stack-md border border-primary/40 bg-secondary-container text-on-surface rounded-lg p-stack-sm text-body-md font-body-md"
          >
            {overrideNote}
          </div>
        )}
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
          <div
            className="flex border-b border-outline-variant bg-surface-container-low"
            style={{ fontFamily: "var(--font-ui)" }}
          >
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
              <span
                className="text-label-md font-label-md text-on-surface-variant border border-outline-variant rounded-lg px-stack-sm py-stack-xs"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                Drift Check Active
              </span>
            </div>
          </div>

          <div className="flex-1 p-stack-lg overflow-y-auto bg-surface-container-lowest relative">
            <div ref={previewRef} className="relative">
              <MarginDiffTicks
                claims={activeClaims}
                containerRef={previewRef}
              />
              <div className="pl-stack-sm">
                {activeArtifact ? (
                  <MarkdownRenderer source={activeArtifact} />
                ) : (
                  <p className="text-body-md font-body-md text-on-surface-variant italic">
                    This artifact is not present in the staged package.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Story 8.3: Action toolbar */}
          {activeArtifact && (
            <div
              className="flex items-center gap-stack-sm px-stack-lg py-stack-sm border-t border-outline-variant bg-surface-container-low"
              style={{ fontFamily: "var(--font-ui)" }}
            >
              <button
                type="button"
                onClick={() => handleCopy(activeArtifact)}
                className="inline-flex items-center gap-1.5 px-stack-sm py-stack-xs rounded-lg border border-outline-variant text-label-md font-label-md text-on-surface-variant hover:text-primary hover:border-primary transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <span style={{ fontFamily: "var(--font-mono)" }}>Copy</span>
              </button>
              <button
                type="button"
                onClick={() => handleDownloadMd(activeArtifact, mdFilename)}
                className="inline-flex items-center gap-1.5 px-stack-sm py-stack-xs rounded-lg border border-outline-variant text-label-md font-label-md text-on-surface-variant hover:text-primary hover:border-primary transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  {mdFilename}
                </span>
              </button>
              <button
                type="button"
                onClick={() => handleDownloadPdf(pdfFilename)}
                className="inline-flex items-center gap-1.5 px-stack-sm py-stack-xs rounded-lg border border-outline-variant text-label-md font-label-md text-on-surface-variant hover:text-primary hover:border-primary transition-colors"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="12" y1="18" x2="12" y2="12" />
                  <polyline points="9 15 12 18 15 15" />
                </svg>
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  {pdfFilename}
                </span>
              </button>
            </div>
          )}
        </section>

        <MetadataSidebar metadata={payload.metadata} />
      </div>

      {modalOpen && (
        <ApproveOverrideModal
          slug={payload.slug}
          onClose={() => setModalOpen(false)}
          onSuccess={(note) => {
            setOverrideApplied(true);
            setOverrideNote(note);
            setModalOpen(false);
          }}
        />
      )}

      {/* Story 8.3: Toast flash overlay */}
      {toasts.length > 0 && (
        <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-stack-xs">
          {toasts.map((t) => (
            <div
              key={t.id}
              role="status"
              className="bg-inverse-surface text-inverse-on-surface text-body-md font-body-md px-stack-md py-stack-sm rounded-lg shadow-lg animate-fade-in"
              style={{ fontFamily: "var(--font-ui)" }}
            >
              {t.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
