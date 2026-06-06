/**
 * FlowCard — Story 7.5 (updated: 03-10 status indicator, 03-18 provider icon)
 *
 * One card per n8n ingest flow (Upwork, OnlineJobs.ph, LinkedIn email).
 * Shows last-run timestamp + status badge + JD count + (when status is
 * never_run) the contract reminder copy explaining how to wire the n8n
 * INGEST_BASE_URL.
 *
 * 03-10: Operational status dot+label derived from last_run_status.
 *   The API returns the outcome of the most-recent completed ingest run
 *   (pass | fail | never_run). There is no real-time n8n running/stopped
 *   signal — the dot reflects the last-known run result honestly:
 *     pass       → green  "Active"
 *     fail       → red    "Error"
 *     never_run  → grey   "Not configured"
 *
 * 03-18: Provider branded avatar tile (inline SVG monogram — no new deps).
 *
 * Sibling to Story 6.3's HeldCountCard / RecentPackagesTable in component
 * style — design-token Tailwind classes only, no ad-hoc hex/pixel values.
 */

export type FlowStatus = "pass" | "fail" | "never_run";

export type FlowTelemetry = {
  flow_name: "upwork" | "onlinejobs_ph" | "linkedin_email";
  last_run_timestamp: string | null;
  last_run_status: FlowStatus;
  jds_ingested_count: number;
  last_error: string | null;
};

const FLOW_LABELS: Record<FlowTelemetry["flow_name"], string> = {
  upwork: "Upwork search",
  onlinejobs_ph: "OnlineJobs.ph listings",
  linkedin_email: "LinkedIn email alerts",
};

type Props = {
  flow: FlowTelemetry;
};

export function FlowCard({ flow }: Props) {
  return (
    <article className="border border-outline-variant rounded-xl bg-surface-container-lowest p-gutter flex flex-col gap-stack-md shadow-sm relative overflow-hidden">
      {/* 03-10: left accent stripe — green=active, red=error, grey=not configured */}
      <AccentStripe status={flow.last_run_status} />

      <header className="flex items-start justify-between gap-stack-sm">
        {/* 03-18: provider avatar + title/code block */}
        <div className="flex items-start gap-stack-sm min-w-0">
          <ProviderIcon provider={flow.flow_name} />
          <div className="flex flex-col gap-stack-xs min-w-0">
            <h4 className="text-headline-md font-headline-md text-on-surface">
              {FLOW_LABELS[flow.flow_name]}
            </h4>
            <code className="text-label-md font-label-md text-on-surface-variant">
              {flow.flow_name}
            </code>
          </div>
        </div>
        <StatusBadge status={flow.last_run_status} />
      </header>

      {/* 03-10: operational status dot + label */}
      <OperationalStatus status={flow.last_run_status} />

      <div className="grid grid-cols-2 gap-stack-md">
        <Metric
          label="Last run"
          value={
            flow.last_run_timestamp
              ? formatRelative(flow.last_run_timestamp)
              : "—"
          }
          title={flow.last_run_timestamp ?? undefined}
        />
        <Metric
          label="JDs ingested"
          value={String(flow.jds_ingested_count)}
        />
      </div>

      {flow.last_error && (
        <p className="text-body-md font-body-md text-error">
          Last error: {flow.last_error}
        </p>
      )}

      {flow.last_run_status === "never_run" && <NeverRunHint />}
    </article>
  );
}

// ─── 03-10: Accent stripe (left edge colour cue) ────────────────────────────

function AccentStripe({ status }: { status: FlowStatus }) {
  const color =
    status === "pass"
      ? "bg-[#14b86a]"   /* emerald-500 equivalent */
      : status === "fail"
        ? "bg-error"
        : "bg-outline-variant";
  return (
    <div
      className={`absolute top-0 left-0 w-1 h-full ${color}`}
      aria-hidden="true"
    />
  );
}

// ─── 03-10: Operational status dot + label ──────────────────────────────────

/**
 * Maps last_run_status to a human-readable operational signal.
 * NOTE: this reflects the LAST RUN OUTCOME from disk sidecars, not a live
 * n8n running/stopped state (the API has no such signal).
 */
function OperationalStatus({ status }: { status: FlowStatus }) {
  const { dot, label, labelClass } =
    status === "pass"
      ? {
          dot: "bg-[#14b86a]",
          label: "Active",
          labelClass: "text-[#0d7f4a]",
        }
      : status === "fail"
        ? {
            dot: "bg-error",
            label: "Error",
            labelClass: "text-error",
          }
        : {
            dot: "bg-outline",
            label: "Not configured",
            labelClass: "text-on-surface-variant",
          };

  return (
    <div className="flex items-center gap-stack-xs">
      <span
        className={`w-2 h-2 rounded-full shrink-0 ${dot}`}
        aria-hidden="true"
      />
      <span className={`text-label-md font-label-md uppercase ${labelClass}`}>
        {label}
      </span>
    </div>
  );
}

// ─── 03-18: Provider branded avatar tile ────────────────────────────────────

function ProviderIcon({ provider }: { provider: FlowTelemetry["flow_name"] }) {
  if (provider === "upwork") return <UpworkIcon />;
  if (provider === "linkedin_email") return <LinkedInIcon />;
  return <OnlineJobsIcon />;
}

/** Upwork — green rounded square with white "U" */
function UpworkIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="Upwork"
      role="img"
      className="shrink-0"
    >
      <rect width="40" height="40" rx="8" fill="#14a800" />
      <text
        x="20"
        y="27"
        textAnchor="middle"
        fontSize="20"
        fontWeight="700"
        fontFamily="Inter, sans-serif"
        fill="#ffffff"
      >
        U
      </text>
    </svg>
  );
}

/** LinkedIn — blue rounded square with white "in" */
function LinkedInIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="LinkedIn"
      role="img"
      className="shrink-0"
    >
      <rect width="40" height="40" rx="8" fill="#0a66c2" />
      <text
        x="20"
        y="27"
        textAnchor="middle"
        fontSize="16"
        fontWeight="700"
        fontFamily="Inter, sans-serif"
        fill="#ffffff"
      >
        in
      </text>
    </svg>
  );
}

/** OnlineJobs.ph — orange/amber rounded square with white "OJ" */
function OnlineJobsIcon() {
  return (
    <svg
      width="40"
      height="40"
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="OnlineJobs.ph"
      role="img"
      className="shrink-0"
    >
      <rect width="40" height="40" rx="8" fill="#d97706" />
      <text
        x="20"
        y="27"
        textAnchor="middle"
        fontSize="13"
        fontWeight="700"
        fontFamily="Inter, sans-serif"
        fill="#ffffff"
      >
        OJ
      </text>
    </svg>
  );
}

// ─── StatusBadge (existing, unchanged) ──────────────────────────────────────

function StatusBadge({ status }: { status: FlowStatus }) {
  const label =
    status === "pass" ? "Pass" : status === "fail" ? "Fail" : "Never run";
  const tone =
    status === "pass"
      ? "bg-tertiary-container text-on-tertiary-container"
      : status === "fail"
        ? "bg-error-container text-on-error-container"
        : "bg-surface-container-high text-on-surface-variant";
  return (
    <span
      className={`inline-flex items-center px-stack-sm py-stack-xs rounded text-label-md font-label-md uppercase ${tone}`}
    >
      {label}
    </span>
  );
}

function Metric({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div className="flex flex-col gap-stack-xs">
      <span className="text-label-md font-label-md uppercase text-on-surface-variant">
        {label}
      </span>
      <span
        className="text-body-md font-body-md text-on-surface"
        title={title}
      >
        {value}
      </span>
    </div>
  );
}

function NeverRunHint() {
  return (
    <div className="border border-outline-variant rounded-lg bg-surface-container-low p-stack-md">
      <p className="text-body-md font-body-md text-on-surface-variant">
        No JDs ingested via this flow yet. Point the n8n flow's{" "}
        <code className="text-label-md font-label-md">INGEST_BASE_URL</code> at{" "}
        <code className="text-label-md font-label-md">
          http://127.0.0.1:8765
        </code>{" "}
        and the next successful POST will land here.
      </p>
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const seconds = (Date.now() - then) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  return `${Math.floor(seconds / 86400)} day ago`;
}
