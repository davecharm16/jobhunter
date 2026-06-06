/**
 * PipelineCard — rich application pipeline card for the Dashboard.
 *
 * Implements dashboard gaps 01-1, 01-2, 01-3, 01-4, 01-15, 01-16, 01-17,
 * 01-18. Matches the design reference in:
 *   design_guidelines/stitch-export/html/01-dashboard.html (lines ~256-320)
 *
 * Layout per card:
 *   ┌─────────────────────────────────────────────┐
 *   │ Job Title (headline-md)    [Status Badge]   │
 *   │ work icon + Company / Source (body-md muted) │
 *   ├─────────────────────────────────────────────┤
 *   │ ○ Drift Health: Pass          [View Docs]   │
 *   └─────────────────────────────────────────────┘
 *
 * Verdict → UI mapping:
 *   pass         → green check   "Drift Health: Pass"  → "View Docs" → /packages/:slug
 *   overridden   → green check   "Drift Health: Pass"  → "View Docs" → /packages/:slug
 *   held:*       → red warning   "Fabrication Detected" etc. → "Fix Issues" → /packages/:slug/drift
 *                  + red ring on card border
 */

import type React from "react";
import { Link } from "react-router-dom";
import type { QueueEntry, QueueVerdict } from "./RecentPackagesTable";

// ─── SVG icons (inline, no external font dependency) ─────────────────────────

type IconProps = { className?: string; style?: React.CSSProperties };

function CheckCircleIcon({ className, style }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className ?? "w-5 h-5"}
      style={style}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 1 0-1.06-1.06l-4.5 4.5-2-2a.75.75 0 0 0-1.06 1.06l2.5 2.5a.75.75 0 0 0 1.06 0l5.06-5z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function WarningIcon({ className, style }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className ?? "w-5 h-5"}
      style={style}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M9.401 3.003c1.155-2 4.043-2 5.197 0l7.355 12.748c1.154 2-.29 4.5-2.599 4.5H4.645c-2.309 0-3.752-2.5-2.598-4.5L9.4 3.003zM12 8.25a.75.75 0 0 1 .75.75v3.75a.75.75 0 0 1-1.5 0V9a.75.75 0 0 1 .75-.75zm0 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function PendingIcon({ className }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className ?? "w-5 h-5"}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zM8.25 12a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5zM12 12.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5zM15.75 12a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function WorkIcon({ className }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className ?? "w-4 h-4"}
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M7.5 5.25a3 3 0 0 1 3-3h3a3 3 0 0 1 3 3v.205c.933.085 1.857.197 2.774.334 1.454.218 2.476 1.483 2.476 2.917v3.033c0 1.211-.734 2.352-1.936 2.752A24.726 24.726 0 0 1 12 15.75c-2.73 0-5.357-.442-7.814-1.259-1.202-.4-1.936-1.541-1.936-2.752V8.706c0-1.434 1.022-2.7 2.476-2.917A48.814 48.814 0 0 1 7.5 5.455V5.25zm7.5 0v.09a49.488 49.488 0 0 0-6 0v-.09a1.5 1.5 0 0 1 1.5-1.5h3a1.5 1.5 0 0 1 1.5 1.5zm-3 8.25a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z"
        clipRule="evenodd"
      />
      <path d="M3 18.4v-2.796a4.3 4.3 0 0 0 .713.31A26.226 26.226 0 0 0 12 17.25c2.892 0 5.68-.468 8.287-1.335.252-.084.49-.189.713-.311V18.4c0 1.452-1.047 2.728-2.523 2.923-2.12.282-4.282.427-6.477.427a49.19 49.19 0 0 1-6.477-.427C4.047 21.128 3 19.852 3 18.4z" />
    </svg>
  );
}

// ─── Verdict derivations ──────────────────────────────────────────────────────

type DriftState = "pass" | "fail" | "inprogress";

/** Map a queue verdict to the card's drift-health state. */
function driftState(verdict: QueueVerdict): DriftState {
  if (verdict === "pass" || verdict === "overridden") return "pass";
  if (verdict.startsWith("held:")) return "fail";
  return "inprogress";
}

const DRIFT_HEALTH_LABEL: Record<QueueVerdict, string> = {
  pass: "Drift Health: Pass",
  overridden: "Drift Health: Pass",
  "held:fabrication": "Fabrication Detected",
  "held:content-loss": "Content Loss Detected",
  "held:keyword-stuffing": "Keyword Stuffing Detected",
  "held:multiple": "Multiple Issues Detected",
};

const STATUS_BADGE_CLASSES: Record<QueueVerdict, string> = {
  pass: "bg-secondary-container text-on-secondary-fixed",
  overridden: "bg-surface-container-highest text-on-surface",
  "held:fabrication": "bg-surface-container-highest text-on-surface",
  "held:content-loss": "bg-surface-container-highest text-on-surface",
  "held:keyword-stuffing": "bg-surface-container-highest text-on-surface",
  "held:multiple": "bg-surface-container-highest text-on-surface",
};

const STATUS_BADGE_LABEL: Record<QueueVerdict, string> = {
  pass: "Review",
  overridden: "Overridden",
  "held:fabrication": "Drift Check",
  "held:content-loss": "Drift Check",
  "held:keyword-stuffing": "Drift Check",
  "held:multiple": "Drift Check",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ verdict }: { verdict: QueueVerdict }) {
  return (
    <span
      className={`shrink-0 px-3 py-1 rounded-full text-label-md font-label-md font-medium ${STATUS_BADGE_CLASSES[verdict]}`}
    >
      {STATUS_BADGE_LABEL[verdict]}
    </span>
  );
}

function DriftHealthRow({ verdict }: { verdict: QueueVerdict }) {
  const state = driftState(verdict);
  const label = DRIFT_HEALTH_LABEL[verdict] ?? "Unknown";

  if (state === "pass") {
    return (
      <div className="flex items-center gap-2">
        {/* pass-green: #10B981 — matches design token used in the HTML reference */}
        <CheckCircleIcon className="w-5 h-5 shrink-0" style={{ color: "#10B981" }} />
        <span className="text-body-md font-body-md text-on-surface font-medium">
          {label}
        </span>
      </div>
    );
  }

  if (state === "fail") {
    return (
      <div className="flex items-center gap-2">
        {/* fail-red: #EF4444 — matches design token used in the HTML reference */}
        <WarningIcon className="w-5 h-5 shrink-0" style={{ color: "#EF4444" }} />
        <span className="text-body-md font-body-md font-medium" style={{ color: "#EF4444" }}>
          {label}
        </span>
      </div>
    );
  }

  // inprogress
  return (
    <div className="flex items-center gap-2">
      <PendingIcon className="w-5 h-5 shrink-0 text-on-surface-variant" />
      <span className="text-body-md font-body-md text-on-surface-variant font-medium">
        Tailoring in progress...
      </span>
    </div>
  );
}

function ActionButton({
  verdict,
  slug,
}: {
  verdict: QueueVerdict;
  slug: string;
}) {
  const state = driftState(verdict);
  const encodedSlug = encodeURIComponent(slug);

  if (state === "pass") {
    return (
      <Link
        to={`/packages/${encodedSlug}`}
        className="text-primary font-medium text-body-md font-body-md hover:underline shrink-0"
      >
        View Docs
      </Link>
    );
  }

  if (state === "fail") {
    return (
      <Link
        to={`/packages/${encodedSlug}/drift`}
        className="text-primary font-medium text-body-md font-body-md hover:underline shrink-0"
      >
        Fix Issues
      </Link>
    );
  }

  // inprogress
  return (
    <Link
      to={`/packages/${encodedSlug}`}
      className="text-primary font-medium text-body-md font-body-md hover:underline shrink-0"
    >
      Continue
    </Link>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

type PipelineCardProps = {
  entry: QueueEntry;
};

/**
 * One rich pipeline card. Failed/fabricated cards get a red ring.
 * Hover: shadow-md transition.
 */
export function PipelineCard({ entry }: PipelineCardProps) {
  const { slug, verdict, source_board, job_title, company_name } = entry;
  const state = driftState(verdict);
  const isFailed = state === "fail";

  // Display label for company/source line
  const sourceLabel = company_name
    ? `${company_name} (${source_board})`
    : source_board || "unknown";

  const cardBase =
    "bg-surface-container-lowest border border-outline-variant rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col gap-4";
  const redRing = isFailed ? " ring-1 ring-error/20" : "";

  return (
    <article className={`${cardBase}${redRing}`}>
      {/* Header row: title + status badge */}
      <div className="flex justify-between items-start gap-stack-sm">
        <div className="min-w-0">
          <h4 className="text-headline-md font-headline-md text-on-surface font-semibold truncate">
            {job_title ?? slug}
          </h4>
          <p className="text-body-md font-body-md text-on-surface-variant flex items-center gap-1 mt-1">
            <WorkIcon className="w-4 h-4 shrink-0" />
            <span className="truncate">{sourceLabel}</span>
          </p>
        </div>
        <StatusBadge verdict={verdict} />
      </div>

      {/* Divider + drift-health row + action button */}
      <div className="border-t border-outline-variant pt-4 flex justify-between items-center gap-stack-sm">
        <DriftHealthRow verdict={verdict} />
        <ActionButton verdict={verdict} slug={slug} />
      </div>
    </article>
  );
}
