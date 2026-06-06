import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApproveOverrideModal } from "./components/ApproveOverrideModal";
import {
  InlineDriftHighlight,
  type DriftTrace,
} from "./components/InlineDriftHighlight";
import { DriftAndJDHighlight } from "./components/DriftAndJDHighlight";
import { InlineJDHighlight } from "./components/InlineJDHighlight";
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

/* ── Drift data (for fabrication margin ticks + inline highlights) ── */
type DriftApiTrace = {
  claim_id: string;
  claim_text: string;
  source_text: string | null;
};

type DriftFabricationCheck = {
  verdict: "pass" | "fail";
  traces: DriftApiTrace[];
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
  const [regenOpen, setRegenOpen] = useState(false);
  const [regenNotes, setRegenNotes] = useState("");
  const [regenJdText, setRegenJdText] = useState("");
  const [regenNeedsJd, setRegenNeedsJd] = useState(false);
  const [regenLoading, setRegenLoading] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  // Story 8.3: drift data for fabrication margin ticks
  const [driftClaims, setDriftClaims] = useState<UnsourcedClaim[]>([]);
  // Story 04-2: inline highlight traces (sourced + unsourced combined)
  const [driftTraces, setDriftTraces] = useState<DriftTrace[]>([]);
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
        // 04-2: combine sourced traces + unsourced claims into a single
        // DriftTrace[] for inline highlights. Unsourced claims get
        // source_text: null (fabrication / no canonical source).
        const sourced: DriftTrace[] = (
          body.fabrication_check?.traces ?? []
        ).map((t) => ({
          claim_id: t.claim_id,
          claim_text: t.claim_text,
          source_text: t.source_text,
        }));
        const unsourced: DriftTrace[] = claims.map((c) => ({
          claim_id: c.claim_id,
          claim_text: c.claim_text,
          source_text: null,
        }));
        setDriftTraces([...sourced, ...unsourced]);
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
  // 04-5: job title + company for the page header.
  // Fallback chain: parsed_jd.job_title → metadata.job_title → null.
  // (metadata.job_title is the D1 top-level field; parsed_jd.job_title is the
  // same value mirrored into the parsed dict — prefer parsed_jd first so
  // old packages without the top-level field still resolve.)
  const jobTitle =
    parsed.job_title ?? payload.metadata.job_title ?? null;
  const companyName =
    parsed.company_name ?? payload.metadata.company_name ?? null;
  // location: no such field exists in ParsedJD — removed.
  const headerTitle =
    jobTitle && companyName
      ? `${jobTitle} at ${companyName}`
      : jobTitle
        ? jobTitle
        : companyName
          ? `Role at ${companyName}`
          : null;
  // 04-6: red flags — prefer parsed_jd.red_flags over top-level metadata.red_flags
  const redFlags: Array<string | { text?: string; reason?: string }> =
    (parsed.red_flags && parsed.red_flags.length > 0
      ? parsed.red_flags
      : payload.metadata.red_flags ?? []) as Array<
      string | { text?: string; reason?: string }
    >;
  // 04-1: must-haves for JD keyword highlights in the CV
  const mustHaves: string[] = parsed.must_haves ?? [];
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
  // Story 04-2: inline highlights also shown only on CV tab
  const activeTraces = activeTab === "cv" ? driftTraces : [];

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
          style={{ fontFamily: headerTitle ? "var(--font-ui)" : "var(--font-mono)" }}
        >
          {headerTitle ?? payload.slug}
        </h1>
        {/* 04-5: sub-headline with slug when we have a resolved title */}
        {headerTitle && (
          <p className="text-body-md font-body-md text-on-surface-variant" style={{ fontFamily: "var(--font-mono)" }}>
            {payload.slug}
          </p>
        )}
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
              <button
                type="button"
                onClick={() => setRegenOpen(!regenOpen)}
                aria-label="Regenerate with correction notes"
                className="inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg border border-outline-variant text-body-md font-body-md text-on-surface-variant hover:text-primary hover:border-primary transition-colors"
              >
                {regenOpen ? "Cancel regenerate" : "Regenerate with notes"}
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
        {regenOpen && (
          <div className="mt-stack-md border border-outline-variant rounded-xl p-stack-md bg-surface-container-lowest flex flex-col gap-stack-sm">
            <label
              htmlFor="regen-notes"
              className="text-body-md font-body-md font-semibold text-on-surface"
              style={{ fontFamily: "var(--font-ui)" }}
            >
              Correction notes for the AI
            </label>
            {regenNeedsJd && (
              <>
                <label
                  htmlFor="regen-jd"
                  className="text-body-md font-body-md font-semibold text-on-surface"
                  style={{ fontFamily: "var(--font-ui)" }}
                >
                  Original JD text <span className="text-error">(required — not saved in this package)</span>
                </label>
                <textarea
                  id="regen-jd"
                  value={regenJdText}
                  onChange={(e) => setRegenJdText(e.target.value)}
                  placeholder="Paste the original job description here..."
                  rows={6}
                  className="w-full rounded-lg border border-outline-variant bg-surface p-stack-sm text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary resize-y"
                />
              </>
            )}
            <textarea
              id="regen-notes"
              value={regenNotes}
              onChange={(e) => setRegenNotes(e.target.value)}
              placeholder="e.g. 'Remove the claim about coaching habits', 'Add more detail about Shopify work', 'Keep it to 1 page'"
              rows={4}
              className="w-full rounded-lg border border-outline-variant bg-surface p-stack-sm text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary resize-y"
              style={{ fontFamily: "var(--font-mono)" }}
            />
            {regenError && (
              <p className="text-body-md font-body-md text-error">{regenError}</p>
            )}
            <div className="flex gap-stack-sm">
              <button
                type="button"
                disabled={regenLoading || !regenNotes.trim() || (regenNeedsJd && !regenJdText.trim())}
                onClick={async () => {
                  setRegenLoading(true);
                  setRegenError(null);
                  try {
                    const reqBody: Record<string, string> = { notes: regenNotes.trim() };
                    if (regenJdText.trim()) {
                      reqBody.jd_text = regenJdText.trim();
                    }
                    const resp = await fetch(
                      `/api/package/${encodeURIComponent(slug!)}/regenerate`,
                      {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(reqBody),
                      },
                    );
                    const body = await resp.json();
                    if (!resp.ok) {
                      const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
                      if (detail.includes("no_jd_text_found")) {
                        setRegenNeedsJd(true);
                        setRegenError("This package doesn't have the JD saved. Paste the original JD text above, then try again.");
                      } else {
                        setRegenError(detail);
                      }
                      return;
                    }
                    window.location.href = `/packages/${encodeURIComponent(body.slug)}`;
                  } catch (err) {
                    setRegenError(`Network error: ${err}`);
                  } finally {
                    setRegenLoading(false);
                  }
                }}
                className="inline-flex items-center gap-stack-sm px-stack-md py-stack-sm rounded-lg bg-primary text-on-primary text-body-md font-body-md font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {regenLoading ? (
                  <>
                    <span className="inline-block w-4 h-4 border-2 border-on-primary/30 border-t-on-primary rounded-full animate-spin" />
                    Regenerating...
                  </>
                ) : (
                  "Regenerate"
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setRegenOpen(false);
                  setRegenNotes("");
                  setRegenError(null);
                }}
                className="px-stack-md py-stack-sm rounded-lg border border-outline-variant text-body-md font-body-md text-on-surface-variant hover:text-on-surface transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </header>

      {/* 04-6: Red Flags — prominent card shown near the top when non-empty */}
      {redFlags.length > 0 && (
        <div
          className="rounded-xl border border-error/40 bg-error-container/20 p-stack-md flex flex-col gap-stack-sm shadow-sm"
          role="alert"
          aria-label="Red flags detected in this job description"
        >
          <div className="flex items-center gap-stack-sm">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="shrink-0"
              style={{ color: "var(--color-error, #ba1a1a)" }}
              aria-hidden="true"
            >
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            <h2
              className="text-body-lg font-body-lg font-semibold"
              style={{
                color: "var(--color-error, #ba1a1a)",
                fontFamily: "var(--font-ui)",
              }}
            >
              Red Flags
            </h2>
          </div>
          <ul className="flex flex-col gap-stack-xs">
            {redFlags.map((flag, idx) => {
              const text =
                typeof flag === "string"
                  ? flag
                  : flag.text && flag.reason
                    ? `${flag.text} — ${flag.reason}`
                    : flag.text ?? flag.reason ?? JSON.stringify(flag);
              return (
                <li
                  key={idx}
                  className="flex items-start gap-stack-sm text-body-md font-body-md text-on-surface-variant"
                  style={{ fontFamily: "var(--font-ui)" }}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="mt-0.5 shrink-0"
                    style={{ color: "var(--color-error, #ba1a1a)" }}
                    aria-hidden="true"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                  {text}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* 04-7: Budget Range (Upwork only, from signals) + Tone stat cards */}
      {(parsed.budget || parsed.tone) && (
        <div className="flex flex-wrap gap-stack-md">
          {parsed.budget && (
            <div className="flex-1 min-w-[140px] bg-surface-container rounded-xl border border-outline-variant p-stack-md">
              <p
                className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs"
                style={{ fontFamily: "var(--font-ui)" }}
              >
                Budget Range
              </p>
              <p
                className="text-body-lg font-body-lg font-semibold text-on-surface"
                style={{ fontFamily: "var(--font-ui)" }}
              >
                {parsed.budget}
              </p>
            </div>
          )}
          {parsed.tone && (
            <div className="flex-1 min-w-[140px] bg-surface-container rounded-xl border border-outline-variant p-stack-md">
              <p
                className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs"
                style={{ fontFamily: "var(--font-ui)" }}
              >
                Tone
              </p>
              <p
                className="text-body-lg font-body-lg font-semibold text-on-surface"
                style={{ fontFamily: "var(--font-ui)" }}
              >
                {parsed.tone}
              </p>
            </div>
          )}
        </div>
      )}

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
              <Link
                to={`/packages/${encodeURIComponent(payload.slug)}/drift`}
                className="inline-flex items-center gap-1 text-label-md font-label-md text-on-surface-variant border border-outline-variant rounded-lg px-stack-sm py-stack-xs hover:text-primary hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary/50 transition-colors cursor-pointer"
                style={{ fontFamily: "var(--font-mono)" }}
                aria-label="Drift Check Active — view drift diagnostics for this package"
              >
                Drift Check Active
              </Link>
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
                  activeTraces.length > 0 && mustHaves.length > 0 ? (
                    /* 04-1 + 04-2: both drift highlights and JD tailoring highlights */
                    <DriftAndJDHighlight
                      source={activeArtifact}
                      traces={activeTraces}
                      mustHaves={mustHaves}
                    />
                  ) : activeTraces.length > 0 ? (
                    /* 04-2: drift highlights only */
                    <InlineDriftHighlight
                      source={activeArtifact}
                      traces={activeTraces}
                    />
                  ) : mustHaves.length > 0 ? (
                    /* 04-1: JD tailoring highlights only */
                    <InlineJDHighlight
                      source={activeArtifact}
                      mustHaves={mustHaves}
                    />
                  ) : (
                    <MarkdownRenderer source={activeArtifact} />
                  )
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
