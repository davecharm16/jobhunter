/**
 * ContentLossSection — Story 4.4
 *
 * Renders the populated content-loss block inside the drift diagnostics
 * surface. Replaces Story 3.5's "pending" placeholder. Pass / fail empty
 * states match the Stitch design language; dropped entries get a chip-style
 * JD-requirements list + a reason badge + a keyboard-accessible <details>
 * expansion for the full primary_text.
 *
 * Story 4.3's `config_snapshot` is rendered as a small "Run config" panel
 * when present; gracefully omitted when absent (e.g. older drift.json from
 * before Story 4.3 merged).
 */

import type { ReactNode } from "react";

export type ContentLossPreservedEntry = {
  entry_id: string;
  section: string;
  matched_in: string[];
  match_type: "substring" | "semantic";
};

export type ContentLossDroppedEntry = {
  entry_id: string;
  section: string;
  primary_text: string;
  jd_requirements_addressed: string[];
  reason: "irrelevant_to_jd" | "silently_lost";
};

export type ContentLossConfigSnapshot = {
  relevance_matcher?: string;
  presence_matcher?: string;
  tag_overlap_min?: number;
  keyword_overlap_pct?: number;
  embedding_distance_max?: number;
  presence_semantic_threshold?: number;
};

export type ContentLossBlock = {
  verdict: "pass" | "fail";
  check_version: string;
  ran_at: string;
  preserved_entries: ContentLossPreservedEntry[];
  dropped_entries: ContentLossDroppedEntry[];
  config_snapshot?: ContentLossConfigSnapshot;
  error?: string;
};

type Props = {
  block: ContentLossBlock;
};

export function ContentLossSection({ block }: Props) {
  const droppedSilently = block.dropped_entries.filter(
    (d) => d.reason === "silently_lost",
  );
  const droppedRationale = block.dropped_entries.filter(
    (d) => d.reason === "irrelevant_to_jd",
  );

  return (
    <div className="flex flex-col gap-stack-md">
      {block.error && (
        <div
          role="alert"
          className="border border-error rounded-lg p-stack-md text-error text-body-md font-body-md"
        >
          {block.error}
        </div>
      )}

      <ConfigSnapshotPanel snapshot={block.config_snapshot} />

      {block.verdict === "pass" && droppedSilently.length === 0 && (
        <PassState />
      )}

      {droppedSilently.length > 0 && (
        <DropList
          heading="High-impact entries silently lost"
          tone="error"
          entries={droppedSilently}
        />
      )}

      {droppedRationale.length > 0 && (
        <DropList
          heading="High-impact entries dropped with a rationale"
          tone="muted"
          entries={droppedRationale}
        />
      )}

      <PreservedSummary
        count={block.preserved_entries.length}
        silentDrops={droppedSilently.length}
      />
    </div>
  );
}

function PassState() {
  return (
    <div className="border border-outline-variant rounded-lg p-stack-md bg-surface-container-lowest text-body-md font-body-md text-on-surface">
      All high-impact canonical-CV entries relevant to this JD are present in
      the tailored output.
    </div>
  );
}

function PreservedSummary({
  count,
  silentDrops,
}: {
  count: number;
  silentDrops: number;
}) {
  return (
    <div className="text-label-md font-label-md uppercase text-on-surface-variant">
      {count} preserved · {silentDrops} silently lost
    </div>
  );
}

function DropList({
  heading,
  tone,
  entries,
}: {
  heading: string;
  tone: "error" | "muted";
  entries: ContentLossDroppedEntry[];
}) {
  const headingClass =
    tone === "error"
      ? "text-body-md font-body-md font-semibold text-error"
      : "text-body-md font-body-md font-semibold text-on-surface-variant";

  return (
    <section className="flex flex-col gap-stack-sm">
      <h4 className={headingClass}>{heading}</h4>
      <ul className="flex flex-col gap-stack-sm">
        {entries.map((entry) => (
          <DropCard key={entry.entry_id} entry={entry} tone={tone} />
        ))}
      </ul>
    </section>
  );
}

function DropCard({
  entry,
  tone,
}: {
  entry: ContentLossDroppedEntry;
  tone: "error" | "muted";
}) {
  const cardClass =
    tone === "error"
      ? "border border-error rounded-lg p-stack-md bg-error-container text-on-error-container"
      : "border border-outline-variant rounded-lg p-stack-md bg-surface-container-low text-on-surface-variant";

  const badgeClass =
    tone === "error"
      ? "inline-flex items-center px-stack-xs py-stack-xs rounded text-label-md font-label-md uppercase bg-error text-on-error"
      : "inline-flex items-center px-stack-xs py-stack-xs rounded text-label-md font-label-md uppercase bg-surface-container-high text-on-surface-variant";

  return (
    <li className={cardClass}>
      <div className="flex items-start justify-between gap-stack-sm">
        <div className="flex flex-col gap-stack-xs min-w-0">
          <code className="text-label-md font-label-md text-on-surface-variant truncate">
            {entry.entry_id}
          </code>
          <p className="text-body-md font-body-md break-words">
            {entry.primary_text}
          </p>
        </div>
        <span className={badgeClass}>
          {entry.reason.replace("_", " ")}
        </span>
      </div>
      <ChipRow
        label="JD requirements"
        items={entry.jd_requirements_addressed}
      />
      <details className="mt-stack-sm focus-visible:ring-2 focus-visible:ring-primary">
        <summary className="cursor-pointer text-label-md font-label-md uppercase text-on-surface-variant">
          Detail
        </summary>
        <div className="mt-stack-xs text-body-md font-body-md">
          <p className="text-on-surface-variant">
            Section: <span className="font-medium">{entry.section}</span>
          </p>
          <p className="text-on-surface-variant">
            Reason code: <code>{entry.reason}</code>
          </p>
        </div>
      </details>
    </li>
  );
}

function ChipRow({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="mt-stack-sm flex flex-wrap items-center gap-stack-xs">
      <span className="text-label-md font-label-md uppercase text-on-surface-variant">
        {label}:
      </span>
      {items.map((item) => (
        <span
          key={item}
          className="inline-flex items-center px-stack-xs py-stack-xs rounded bg-surface-container-low text-on-surface text-label-md font-label-md"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function ConfigSnapshotPanel({
  snapshot,
}: {
  snapshot?: ContentLossConfigSnapshot;
}) {
  if (!snapshot) {
    return null;
  }
  const rows: ReactNode[] = [];
  if (snapshot.relevance_matcher) {
    rows.push(
      <SnapshotRow
        key="relevance"
        label="Relevance"
        value={describeRelevanceMatcher(snapshot)}
      />,
    );
  }
  if (snapshot.presence_matcher) {
    rows.push(
      <SnapshotRow
        key="presence"
        label="Presence"
        value={describePresenceMatcher(snapshot)}
      />,
    );
  }
  if (rows.length === 0) {
    return null;
  }
  return (
    <aside className="border border-outline-variant rounded-lg p-stack-md bg-surface-container-low">
      <div className="text-label-md font-label-md uppercase text-on-surface-variant mb-stack-xs">
        Run config
      </div>
      <div className="flex flex-col gap-stack-xs">{rows}</div>
    </aside>
  );
}

function SnapshotRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-stack-xs text-body-md font-body-md text-on-surface">
      <span className="text-on-surface-variant min-w-[5rem]">{label}:</span>
      <span>{value}</span>
    </div>
  );
}

function describeRelevanceMatcher(snapshot: ContentLossConfigSnapshot): string {
  switch (snapshot.relevance_matcher) {
    case "tag_overlap":
      return `tag-overlap, threshold=${snapshot.tag_overlap_min ?? 1}`;
    case "keyword_overlap":
      return `keyword-overlap, threshold=${formatPct(snapshot.keyword_overlap_pct)}`;
    case "embedding_distance":
      return `embedding-distance, threshold=${snapshot.embedding_distance_max ?? "-"}`;
    default:
      return snapshot.relevance_matcher ?? "unknown";
  }
}

function describePresenceMatcher(snapshot: ContentLossConfigSnapshot): string {
  switch (snapshot.presence_matcher) {
    case "substring":
      return "substring (exact textual match)";
    case "semantic":
      return `semantic, threshold=${snapshot.presence_semantic_threshold ?? "-"}`;
    default:
      return snapshot.presence_matcher ?? "unknown";
  }
}

function formatPct(value?: number): string {
  if (typeof value !== "number") return "-";
  return `${Math.round(value * 100)}%`;
}
