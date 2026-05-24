/**
 * FlowCard — Story 7.5
 *
 * One card per n8n ingest flow (Upwork, OnlineJobs.ph, LinkedIn email).
 * Shows last-run timestamp + status badge + JD count + (when status is
 * never_run) the contract reminder copy explaining how to wire the n8n
 * INGEST_BASE_URL.
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
    <article className="border border-outline-variant rounded-xl bg-surface-container-lowest p-gutter flex flex-col gap-stack-md shadow-sm">
      <header className="flex items-start justify-between gap-stack-sm">
        <div className="flex flex-col gap-stack-xs min-w-0">
          <h4 className="text-headline-md font-headline-md text-on-surface">
            {FLOW_LABELS[flow.flow_name]}
          </h4>
          <code className="text-label-md font-label-md text-on-surface-variant">
            {flow.flow_name}
          </code>
        </div>
        <StatusBadge status={flow.last_run_status} />
      </header>

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
