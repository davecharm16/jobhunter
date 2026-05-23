/**
 * KeywordStuffingSection — Story 5.4
 *
 * Renders the populated keyword-stuffing block inside the drift diagnostics
 * surface. Replaces Story 3.5's "pending" placeholder; sibling to Story 4.4's
 * `ContentLossSection`. Two failure sub-blocks (Stories 5.1 density +
 * Story 5.2 placement) plus a pass empty-state matching the design language.
 *
 * Story 5.3's per-channel override resolution lands as `thresholds_applied`.
 * When the resolved set differs from the global defaults below, the affected
 * threshold value gets a small "(override applied for channel: <board>)"
 * label so the author can spot threshold drift without grepping config.
 * The global defaults are hard-coded here (they match config.yaml's shipped
 * values); future config edits without a new story are unlikely.
 */

import type { ReactNode } from "react";

/** Story 5.3 dump-paragraph location entry shape (matcher output). */
export type KeywordStuffingDumpLocation = {
  artifact: string;
  paragraph_index: number;
  kind: "keyword_dump_paragraph" | "comma_run_violation";
  matched_keywords: string[];
  excerpt: string;
  keyword_ratio?: number;
};

/** Story 5.1 density violation entry shape (matcher output). */
export type KeywordStuffingDensityViolation = {
  keyword: string;
  artifact: string;
  occurrences: number;
  total_tokens: number;
  density_pct: number;
  threshold_breached: "max_density_pct" | "max_repetitions_per_artifact";
};

/** Story 5.3 effective threshold set (after per-channel shallow-merge). */
export type KeywordStuffingThresholds = {
  max_density_pct: number;
  max_repetitions_per_artifact: number;
  dump_paragraph_min_tokens: number;
  dump_paragraph_max_keyword_ratio: number;
  comma_run_min_tokens: number;
};

/** Top-level keyword_stuffing block from package.drift.json. */
export type KeywordStuffingBlock = {
  verdict: "pass" | "fail";
  channel: "upwork" | "linkedin" | "onlinejobs_ph" | "other";
  ran_at?: string;
  density_violations: KeywordStuffingDensityViolation[];
  dump_paragraph_locations: KeywordStuffingDumpLocation[];
  thresholds_applied: KeywordStuffingThresholds;
};

/**
 * Global default thresholds — mirrors config.yaml's shipped values
 * (Story 5.3). Used to detect per-channel overrides on the wire so the
 * UI can call them out without re-reading config from the backend.
 */
export const KEYWORD_STUFFING_GLOBAL_DEFAULTS: KeywordStuffingThresholds = {
  max_density_pct: 1.5,
  max_repetitions_per_artifact: 3,
  dump_paragraph_min_tokens: 15,
  dump_paragraph_max_keyword_ratio: 0.3,
  comma_run_min_tokens: 4,
};

type ThresholdKey = keyof KeywordStuffingThresholds;

type Props = {
  block: KeywordStuffingBlock;
};

export function KeywordStuffingSection({ block }: Props) {
  const overrides = computeOverrides(block.thresholds_applied);

  return (
    <div className="flex flex-col gap-stack-md">
      <ChannelHeader channel={block.channel} />

      <ThresholdsPanel
        thresholds={block.thresholds_applied}
        overrides={overrides}
        channel={block.channel}
      />

      {block.verdict === "pass" ? (
        <PassState />
      ) : (
        <FailContent block={block} />
      )}
    </div>
  );
}

function ChannelHeader({ channel }: { channel: KeywordStuffingBlock["channel"] }) {
  return (
    <div className="flex flex-wrap items-baseline gap-stack-xs text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
      <span>Channel:</span>
      <code className="font-mono text-on-surface normal-case tracking-normal">
        {channel}
      </code>
    </div>
  );
}

function PassState() {
  return (
    <div className="border border-outline-variant rounded-lg p-stack-md bg-surface-container-lowest text-body-md font-body-md text-on-surface">
      No keyword stuffing detected. Every measured JD must-have stayed under
      the configured density ceiling, and no dump-paragraphs or comma-runs
      were found in the tailored output.
    </div>
  );
}

function FailContent({ block }: { block: KeywordStuffingBlock }) {
  const hasDensity = block.density_violations.length > 0;
  const hasDump = block.dump_paragraph_locations.length > 0;

  return (
    <div className="flex flex-col gap-stack-lg">
      {hasDensity && (
        <DensityViolations
          violations={block.density_violations}
          thresholds={block.thresholds_applied}
        />
      )}
      {hasDump && (
        <DumpParagraphLocations
          locations={block.dump_paragraph_locations}
        />
      )}
      {!hasDensity && !hasDump && (
        <p className="text-body-md font-body-md text-on-surface-variant italic">
          Verdict failed but no per-keyword violations or dump-paragraphs were
          surfaced. This is unexpected — inspect package.drift.json directly.
        </p>
      )}
    </div>
  );
}

// ---- Density violations ----------------------------------------------------

function DensityViolations({
  violations,
  thresholds,
}: {
  violations: KeywordStuffingDensityViolation[];
  thresholds: KeywordStuffingThresholds;
}) {
  return (
    <section className="flex flex-col gap-stack-sm">
      <h4 className="text-body-md font-body-md font-semibold text-error">
        Density violations
      </h4>
      <ul className="flex flex-col gap-stack-sm">
        {violations.map((violation, idx) => (
          <DensityViolationRow
            key={`${violation.artifact}:${violation.keyword}:${idx}`}
            violation={violation}
            thresholds={thresholds}
          />
        ))}
      </ul>
    </section>
  );
}

function DensityViolationRow({
  violation,
  thresholds,
}: {
  violation: KeywordStuffingDensityViolation;
  thresholds: KeywordStuffingThresholds;
}) {
  const isDensity = violation.threshold_breached === "max_density_pct";
  const measured = isDensity ? violation.density_pct : violation.occurrences;
  const ceiling = isDensity
    ? thresholds.max_density_pct
    : thresholds.max_repetitions_per_artifact;
  const measuredLabel = isDensity
    ? `${violation.density_pct.toFixed(2)}%`
    : `${violation.occurrences}`;
  const ceilingLabel = isDensity
    ? `${thresholds.max_density_pct.toFixed(2)}%`
    : `${thresholds.max_repetitions_per_artifact}`;
  const ruleLabel = isDensity
    ? "density"
    : "repetitions";

  return (
    <li className="border border-error rounded-lg p-stack-md bg-error-container text-on-error-container flex flex-col gap-stack-xs">
      <div className="flex items-start justify-between gap-stack-sm flex-wrap">
        <div className="flex flex-col gap-stack-xs min-w-0">
          <span className="text-body-md font-body-md font-semibold break-words">
            {violation.keyword}
          </span>
          <code className="font-mono text-label-md font-label-md text-on-surface-variant truncate">
            {violation.artifact}
          </code>
        </div>
        <span className="inline-flex items-center px-stack-xs py-stack-xs rounded text-label-md font-label-md uppercase bg-error text-on-error">
          {ruleLabel}
        </span>
      </div>
      <DensityBar measured={measured} ceiling={ceiling} />
      <div className="flex flex-wrap gap-stack-md text-label-md font-label-md">
        <span>
          <span className="uppercase tracking-wider">Measured:</span>{" "}
          <code className="font-mono">{measuredLabel}</code>
        </span>
        <span>
          <span className="uppercase tracking-wider">Ceiling:</span>{" "}
          <code className="font-mono">{ceilingLabel}</code>
        </span>
        <span>
          <span className="uppercase tracking-wider">Occurrences:</span>{" "}
          <code className="font-mono">{violation.occurrences}</code>
        </span>
        <span>
          <span className="uppercase tracking-wider">Tokens:</span>{" "}
          <code className="font-mono">{violation.total_tokens}</code>
        </span>
      </div>
    </li>
  );
}

/**
 * Visual: a horizontal bar where the filled portion represents the measured
 * value clamped at 100% of the ceiling, plus an "overflow" overhang in a
 * stronger tone when the measured exceeds the ceiling. The under-ceiling
 * region uses surface-container-low; the breached portion uses error.
 */
function DensityBar({
  measured,
  ceiling,
}: {
  measured: number;
  ceiling: number;
}) {
  // Bar visualises [0, max(measured, ceiling)] so both are visible together.
  const upperBound = Math.max(measured, ceiling) || 1;
  const ceilingPct = (ceiling / upperBound) * 100;
  const measuredPct = (measured / upperBound) * 100;
  // Filled = whole measured portion in error tone. The ceiling marker is a
  // dashed vertical line overlaid on top to communicate the threshold.
  return (
    <div className="relative h-2 rounded-full bg-surface-container-low overflow-hidden">
      <div
        className="absolute inset-y-0 left-0 bg-error"
        style={{ width: `${Math.min(measuredPct, 100)}%` }}
        aria-hidden="true"
      />
      <div
        className="absolute inset-y-0 border-r-2 border-on-surface-variant border-dashed"
        style={{ left: `${Math.min(ceilingPct, 100)}%` }}
        aria-hidden="true"
      />
      <span className="sr-only">
        Measured {measured} against ceiling {ceiling}.
      </span>
    </div>
  );
}

// ---- Dump-paragraph locations ---------------------------------------------

function DumpParagraphLocations({
  locations,
}: {
  locations: KeywordStuffingDumpLocation[];
}) {
  return (
    <section className="flex flex-col gap-stack-sm">
      <h4 className="text-body-md font-body-md font-semibold text-error">
        Dump-paragraph locations
      </h4>
      <ul className="flex flex-col gap-stack-sm">
        {locations.map((location, idx) => (
          <DumpLocationCard
            key={`${location.artifact}:${location.paragraph_index}:${idx}`}
            location={location}
          />
        ))}
      </ul>
    </section>
  );
}

function DumpLocationCard({
  location,
}: {
  location: KeywordStuffingDumpLocation;
}) {
  const kindLabel =
    location.kind === "keyword_dump_paragraph"
      ? "keyword dump"
      : "comma run";
  return (
    <li className="border border-outline-variant rounded-lg p-stack-md bg-surface-container-low text-on-surface-variant flex flex-col gap-stack-xs">
      <div className="flex items-start justify-between gap-stack-sm flex-wrap">
        <div className="flex flex-col gap-stack-xs min-w-0">
          <code className="font-mono text-label-md font-label-md text-on-surface truncate">
            {location.artifact}
          </code>
          <span className="text-label-md font-label-md uppercase tracking-wider">
            Paragraph #{location.paragraph_index}
            {typeof location.keyword_ratio === "number" && (
              <>
                {" · "}
                <span className="normal-case tracking-normal">
                  keyword ratio{" "}
                  <code className="font-mono">
                    {formatRatioPct(location.keyword_ratio)}
                  </code>
                </span>
              </>
            )}
          </span>
        </div>
        <span className="inline-flex items-center px-stack-xs py-stack-xs rounded text-label-md font-label-md uppercase bg-surface-container-high text-on-surface-variant">
          {kindLabel}
        </span>
      </div>
      <ChipRow label="Matched keywords" items={location.matched_keywords} />
      <pre className="mt-stack-xs font-mono text-label-md font-label-md text-on-surface bg-surface-container-lowest border border-outline-variant rounded p-stack-sm whitespace-pre-wrap break-words">
        {location.excerpt}
      </pre>
    </li>
  );
}

function ChipRow({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-stack-xs">
      <span className="text-label-md font-label-md uppercase text-on-surface-variant">
        {label}:
      </span>
      {items.map((item) => (
        <span
          key={item}
          className="inline-flex items-center px-stack-xs py-stack-xs rounded bg-surface-container-lowest text-on-surface text-label-md font-label-md"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

// ---- Thresholds panel + override detection --------------------------------

function ThresholdsPanel({
  thresholds,
  overrides,
  channel,
}: {
  thresholds: KeywordStuffingThresholds;
  overrides: Set<ThresholdKey>;
  channel: KeywordStuffingBlock["channel"];
}) {
  const rows: ReactNode[] = [];
  rows.push(
    <ThresholdRow
      key="max_density_pct"
      label="Max density"
      value={`${thresholds.max_density_pct.toFixed(2)}%`}
      overridden={overrides.has("max_density_pct")}
      channel={channel}
    />,
  );
  rows.push(
    <ThresholdRow
      key="max_repetitions_per_artifact"
      label="Max repetitions"
      value={`${thresholds.max_repetitions_per_artifact}`}
      overridden={overrides.has("max_repetitions_per_artifact")}
      channel={channel}
    />,
  );
  rows.push(
    <ThresholdRow
      key="dump_paragraph_min_tokens"
      label="Dump-paragraph min tokens"
      value={`${thresholds.dump_paragraph_min_tokens}`}
      overridden={overrides.has("dump_paragraph_min_tokens")}
      channel={channel}
    />,
  );
  rows.push(
    <ThresholdRow
      key="dump_paragraph_max_keyword_ratio"
      label="Dump-paragraph max ratio"
      value={formatRatioPct(thresholds.dump_paragraph_max_keyword_ratio)}
      overridden={overrides.has("dump_paragraph_max_keyword_ratio")}
      channel={channel}
    />,
  );
  rows.push(
    <ThresholdRow
      key="comma_run_min_tokens"
      label="Comma-run min tokens"
      value={`${thresholds.comma_run_min_tokens}`}
      overridden={overrides.has("comma_run_min_tokens")}
      channel={channel}
    />,
  );

  return (
    <aside className="border border-outline-variant rounded-lg p-stack-md bg-surface-container-low">
      <div className="text-label-md font-label-md uppercase text-on-surface-variant mb-stack-xs">
        Thresholds applied
      </div>
      <div className="flex flex-col gap-stack-xs">{rows}</div>
    </aside>
  );
}

function ThresholdRow({
  label,
  value,
  overridden,
  channel,
}: {
  label: string;
  value: string;
  overridden: boolean;
  channel: KeywordStuffingBlock["channel"];
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-stack-xs text-body-md font-body-md text-on-surface">
      <span className="text-on-surface-variant min-w-[12rem]">{label}:</span>
      <code className="font-mono">{value}</code>
      {overridden && (
        <span className="text-label-md font-label-md text-primary italic">
          (override applied for channel: {channel})
        </span>
      )}
    </div>
  );
}

/**
 * Compares each effective threshold to the global defaults and returns the
 * set of keys that differ — drives the "(override applied …)" labels.
 * Tolerates small floating-point noise (e.g. 0.30000000000000004) so a YAML
 * value identical to the default does not light up as overridden.
 */
function computeOverrides(
  thresholds: KeywordStuffingThresholds,
): Set<ThresholdKey> {
  const overrides = new Set<ThresholdKey>();
  const keys: ThresholdKey[] = [
    "max_density_pct",
    "max_repetitions_per_artifact",
    "dump_paragraph_min_tokens",
    "dump_paragraph_max_keyword_ratio",
    "comma_run_min_tokens",
  ];
  for (const key of keys) {
    const effective = thresholds[key];
    const defaultValue = KEYWORD_STUFFING_GLOBAL_DEFAULTS[key];
    if (!nearlyEqual(effective, defaultValue)) {
      overrides.add(key);
    }
  }
  return overrides;
}

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) < 1e-9;
}

function formatRatioPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}
