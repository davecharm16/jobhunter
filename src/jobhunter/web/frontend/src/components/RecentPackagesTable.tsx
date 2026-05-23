import { Link } from "react-router-dom";
import { QueueEmptyState } from "./QueueEmptyState";

export type QueueVerdict =
  | "pass"
  | "overridden"
  | "held:fabrication"
  | "held:content-loss"
  | "held:keyword-stuffing"
  | "held:multiple";

export type QueueEntry = {
  slug: string;
  source_board: string;
  verdict: QueueVerdict;
  timestamp: string;
};

type Props = {
  entries: QueueEntry[];
};

const VERDICT_BADGE: Record<QueueVerdict, string> = {
  pass: "bg-secondary-container text-primary border-primary/20",
  overridden:
    "bg-surface-container text-on-surface-variant border-outline-variant",
  "held:fabrication": "bg-error-container text-on-error-container border-error/40",
  "held:content-loss": "bg-error-container text-on-error-container border-error/40",
  "held:keyword-stuffing":
    "bg-error-container text-on-error-container border-error/40",
  "held:multiple": "bg-error-container text-on-error-container border-error/40",
};

const VERDICT_LABEL: Record<QueueVerdict, string> = {
  pass: "Pass",
  overridden: "Overridden",
  "held:fabrication": "Held - Fabrication",
  "held:content-loss": "Held - Content loss",
  "held:keyword-stuffing": "Held - Keyword stuffing",
  "held:multiple": "Held - Multiple",
};

function relativeTimestamp(iso: string): string {
  if (!iso) return "unknown";
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return iso;
  const deltaMs = Date.now() - then;
  if (deltaMs < 0) return iso;
  const minutes = Math.floor(deltaMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return iso.slice(0, 10);
}

function VerdictBadge({ verdict }: { verdict: QueueVerdict }) {
  return (
    <span
      className={`inline-flex items-center shrink-0 px-stack-sm py-stack-xs rounded-full border text-label-md font-label-md uppercase tracking-wider ${VERDICT_BADGE[verdict]}`}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

function SourceBoardChip({ board }: { board: string }) {
  return (
    <span className="inline-flex items-center px-stack-sm py-stack-xs rounded-full border border-outline-variant bg-surface-container-low text-label-md font-label-md text-on-surface-variant">
      {board || "unknown"}
    </span>
  );
}

export function RecentPackagesTable({ entries }: Props) {
  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded-xl shadow-sm overflow-hidden">
      <header className="flex items-center justify-between px-gutter py-stack-md border-b border-outline-variant bg-surface-container-low">
        <h3 className="text-headline-md font-headline-md text-on-surface">
          Recent packages
        </h3>
        <span className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider">
          {entries.length} shown
        </span>
      </header>
      {entries.length === 0 ? (
        <QueueEmptyState />
      ) : (
        <div className="flex flex-col">
          <div className="hidden md:grid grid-cols-[1fr_140px_200px_120px] gap-stack-md px-gutter py-stack-sm border-b border-outline-variant bg-surface-container-low">
            <span className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
              Slug
            </span>
            <span className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
              Source
            </span>
            <span className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
              Verdict
            </span>
            <span className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant text-right">
              When
            </span>
          </div>
          <ul className="flex flex-col">
            {entries.map((entry) => (
              <li
                key={entry.slug}
                className="border-b border-outline-variant last:border-b-0"
              >
                <Link
                  to={`/packages/${encodeURIComponent(entry.slug)}`}
                  className="grid grid-cols-1 md:grid-cols-[1fr_140px_200px_120px] gap-stack-sm md:gap-stack-md items-center px-gutter py-stack-md hover:bg-surface-container-low transition-colors"
                >
                  <span className="text-body-md font-body-md text-on-surface font-medium break-words">
                    {entry.slug}
                  </span>
                  <SourceBoardChip board={entry.source_board} />
                  <VerdictBadge verdict={entry.verdict} />
                  <span className="text-body-md font-body-md text-on-surface-variant md:text-right">
                    {relativeTimestamp(entry.timestamp)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
