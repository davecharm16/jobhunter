type RedFlag = {
  text?: string;
  reason?: string;
};

type ParsedJD = {
  must_haves?: string[];
  nice_to_haves?: string[];
  /** JD tone — e.g. "professional", "enthusiastic". Always present on parsed JDs. */
  tone?: string;
  seniority?: string;
  /** Upwork budget band (e.g. "$25-50/hr") — present only on Upwork packages. */
  budget?: string;
  /** Red flags surfaced by the JD parser (may live here OR at top-level metadata.red_flags) */
  red_flags?: Array<RedFlag | string>;
  /** Job title extracted from the JD */
  job_title?: string | null;
  /** Company name extracted from the JD */
  company_name?: string | null;
};

type CallLog = {
  model: string;
  input_tokens: number;
  output_tokens: number;
  usd_cost: string;
  purpose: string;
};

type Cost = {
  total_usd: string;
  per_app_target_usd: string;
  exceeded_per_app_target: boolean;
  calls: CallLog[];
};

export type PackageMetadata = {
  slug: string;
  jd_source?: string;
  created_at?: string;
  source_board?: string;
  parsed_jd?: ParsedJD;
  red_flags?: Array<RedFlag | string>;
  prompt_templates?: Record<string, string>;
  drift_verdicts?: Record<string, string>;
  override?: { applied?: boolean; reason?: string | null };
  cost?: Cost;
  /** D1: human-readable role/company extracted from the JD parse (top-level fallback). */
  job_title?: string | null;
  company_name?: string | null;
  /** Original job posting URL, if captured at ingest time. */
  url?: string | null;
};

type Props = {
  metadata: PackageMetadata;
};

function isUpworkBoard(board: string | undefined): boolean {
  return (board ?? "").toLowerCase() === "upwork";
}

function hasAnyDriftFail(verdicts: Record<string, string> | undefined): boolean {
  if (!verdicts) return false;
  return Object.values(verdicts).some((v) => v === "fail");
}

function renderRedFlag(flag: RedFlag | string): string {
  if (typeof flag === "string") return flag;
  if (flag.text && flag.reason) return `${flag.text} - ${flag.reason}`;
  return flag.text ?? flag.reason ?? JSON.stringify(flag);
}

export function MetadataSidebar({ metadata }: Props) {
  const parsed = metadata.parsed_jd ?? {};
  const board = metadata.source_board ?? "unknown";
  const upwork = isUpworkBoard(board);
  const drift = metadata.drift_verdicts ?? {};
  const cost = metadata.cost;
  const promptTemplates = metadata.prompt_templates ?? {};
  const overrideAvailable = hasAnyDriftFail(drift);
  // 04-7: budget (Upwork only) — tone is already shown in the Parsed JD card
  const hasBudgetOrTone = !!parsed.budget;
  // 04-6: red_flags may live in parsed_jd.red_flags (primary) or top-level metadata.red_flags
  const redFlags: Array<RedFlag | string> = (
    parsed.red_flags && parsed.red_flags.length > 0
      ? parsed.red_flags
      : metadata.red_flags ?? []
  );

  return (
    <aside className="w-full lg:w-80 shrink-0 flex flex-col gap-stack-md">
      <Card title="Package">
        <Row label="Slug" value={metadata.slug} />
        {metadata.created_at && (
          <Row label="Created" value={metadata.created_at} />
        )}
        <Row label="JD source" value={metadata.jd_source ?? "unknown"} />
        <Row
          label="Source board"
          value={board}
          highlight={upwork ? "tertiary" : undefined}
        />
      </Card>

      <Card title="Parsed JD">
        {parsed.must_haves && parsed.must_haves.length > 0 && (
          <ListBlock label="Must-haves" items={parsed.must_haves} />
        )}
        {parsed.nice_to_haves && parsed.nice_to_haves.length > 0 && (
          <ListBlock label="Nice-to-haves" items={parsed.nice_to_haves} />
        )}
        {parsed.tone && <Row label="Tone" value={parsed.tone} />}
        {parsed.seniority && (
          <Row label="Seniority" value={parsed.seniority} />
        )}
      </Card>

      {/* 04-7: Budget shown for Upwork packages in a dedicated signals card */}
      {hasBudgetOrTone && (
        <Card title="Upwork signals">
          {parsed.budget && <Row label="Budget" value={parsed.budget} />}
        </Card>
      )}

      {redFlags.length > 0 && (
        <Card title="Red flags" tone="error">
          <ul className="flex flex-col gap-stack-xs">
            {redFlags.map((flag, idx) => (
              <li
                key={idx}
                className="text-body-md font-body-md text-on-surface-variant"
              >
                {renderRedFlag(flag)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="Prompt templates">
        {Object.keys(promptTemplates).length === 0 ? (
          <p className="text-label-md font-label-md text-on-surface-variant">
            No prompt versions recorded.
          </p>
        ) : (
          Object.entries(promptTemplates).map(([name, version]) => (
            <Row key={name} label={name} value={version} />
          ))
        )}
      </Card>

      <Card title="Drift verdicts">
        {Object.entries(drift).map(([name, verdict]) => (
          <Row
            key={name}
            label={name.replace(/_/g, " ")}
            value={verdict}
            highlight={
              verdict === "fail"
                ? "error"
                : verdict === "pass"
                  ? "primary"
                  : undefined
            }
          />
        ))}
      </Card>

      <Card title="Cost per request">
        {cost ? (
          <>
            <Row label="Total" value={`$${cost.total_usd}`} />
            <Row
              label="Per-app target"
              value={`$${cost.per_app_target_usd}`}
            />
            <Row
              label="Over target?"
              value={cost.exceeded_per_app_target ? "yes" : "no"}
              highlight={cost.exceeded_per_app_target ? "error" : undefined}
            />
            {cost.calls && cost.calls.length > 0 && (
              <div className="mt-stack-sm flex flex-col gap-stack-xs">
                <div className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
                  Per-call breakdown
                </div>
                {cost.calls.map((call, idx) => (
                  <div
                    key={idx}
                    className="border border-outline-variant rounded-lg p-stack-sm bg-surface"
                  >
                    <div className="text-label-md font-label-md text-on-surface-variant">
                      {call.purpose} - {call.model}
                    </div>
                    <div className="text-body-md font-body-md text-on-surface">
                      ${call.usd_cost}{" "}
                      <span className="text-label-md font-label-md text-on-surface-variant">
                        ({call.input_tokens} in / {call.output_tokens} out)
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-label-md font-label-md text-on-surface-variant">
            No cost data recorded.
          </p>
        )}
      </Card>

      <Card title="Override">
        <p className="text-body-md font-body-md text-on-surface-variant">
          {overrideAvailable
            ? "Drift fail detected. Override gates approval."
            : "All drift checks pending. No override needed."}
        </p>
      </Card>
    </aside>
  );
}

type CardProps = {
  title: string;
  tone?: "default" | "error";
  children: React.ReactNode;
};

function Card({ title, tone = "default", children }: CardProps) {
  const borderClass =
    tone === "error" ? "border-error" : "border-outline-variant";
  return (
    <section
      className={`bg-surface-container-lowest border ${borderClass} rounded-xl p-stack-md flex flex-col gap-stack-sm shadow-sm`}
    >
      <h3 className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant">
        {title}
      </h3>
      <div className="flex flex-col gap-stack-xs">{children}</div>
    </section>
  );
}

type RowProps = {
  label: string;
  value: string;
  highlight?: "primary" | "error" | "tertiary";
};

function Row({ label, value, highlight }: RowProps) {
  const valueColor =
    highlight === "primary"
      ? "text-primary"
      : highlight === "error"
        ? "text-error"
        : highlight === "tertiary"
          ? "text-tertiary"
          : "text-on-surface";
  return (
    <div className="flex items-baseline justify-between gap-stack-sm">
      <span className="text-label-md font-label-md text-on-surface-variant">
        {label}
      </span>
      <span
        className={`text-body-md font-body-md font-medium ${valueColor} text-right break-words`}
      >
        {value}
      </span>
    </div>
  );
}

type ListBlockProps = {
  label: string;
  items: string[];
};

function ListBlock({ label, items }: ListBlockProps) {
  return (
    <div>
      <div className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant mb-stack-xs">
        {label}
      </div>
      <ul className="flex flex-col gap-stack-xs">
        {items.map((item, idx) => (
          <li
            key={idx}
            className="text-body-md font-body-md text-on-surface"
          >
            - {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
