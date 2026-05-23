import { useEffect, useMemo, useState } from "react";
import { EntryCard } from "./components/EntryCard";

type CanonicalCV = Record<string, any>;

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; doc: CanonicalCV }
  | { kind: "error"; message: string };

type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; path: string }
  | { kind: "error"; message: string };

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function SettingsPage() {
  const [fetchState, setFetchState] = useState<FetchState>({ kind: "loading" });
  const [original, setOriginal] = useState<CanonicalCV | null>(null);
  const [working, setWorking] = useState<CanonicalCV | null>(null);
  const [saveState, setSaveState] = useState<SaveState>({ kind: "idle" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/canonical-cv");
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          setFetchState({
            kind: "error",
            message:
              typeof body.detail === "string"
                ? body.detail
                : JSON.stringify(body.detail),
          });
          return;
        }
        setOriginal(body);
        setWorking(deepClone(body));
        setFetchState({ kind: "ready", doc: body });
      } catch (exc) {
        if (cancelled) return;
        setFetchState({ kind: "error", message: String(exc) });
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const isDirty = useMemo(() => {
    if (!original || !working) return false;
    return !deepEqual(original, working);
  }, [original, working]);

  function updateBasics(field: string, value: string) {
    setWorking((prev) => {
      if (!prev) return prev;
      const next = deepClone(prev);
      next.basics = next.basics ?? {};
      next.basics[field] = value;
      return next;
    });
  }

  function updateEntry(
    section: string,
    index: number,
    mutator: (entry: Record<string, any>) => void,
  ) {
    setWorking((prev) => {
      if (!prev) return prev;
      const next = deepClone(prev);
      const arr = next[section] as Array<Record<string, any>> | undefined;
      if (!arr || !arr[index]) return prev;
      mutator(arr[index]);
      return next;
    });
  }

  function setEntryTags(
    section: string,
    index: number,
    tags: string[] | undefined,
  ) {
    updateEntry(section, index, (entry) => {
      if (tags === undefined || tags.length === 0) {
        delete entry.tags;
      } else {
        entry.tags = tags;
      }
    });
  }

  function setEntryHighImpact(section: string, index: number, value: boolean) {
    updateEntry(section, index, (entry) => {
      if (value) {
        entry.highImpact = true;
      } else {
        delete entry.highImpact;
      }
    });
  }

  async function save() {
    if (!working) return;
    setSaveState({ kind: "saving" });
    try {
      const response = await fetch("/api/canonical-cv", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(working),
      });
      const body = await response.json();
      if (!response.ok) {
        const message =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body);
        setSaveState({ kind: "error", message });
        return;
      }
      setOriginal(deepClone(working));
      setSaveState({ kind: "saved", path: body.path });
    } catch (exc) {
      setSaveState({ kind: "error", message: String(exc) });
    }
  }

  if (fetchState.kind === "loading") {
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
        <p className="text-body-md font-body-md text-on-surface-variant">
          Loading canonical CV...
        </p>
      </div>
    );
  }

  if (fetchState.kind === "error" || !working) {
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
        <div className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
          Failed to load canonical CV:{" "}
          {fetchState.kind === "error" ? fetchState.message : "unknown error"}
        </div>
      </div>
    );
  }

  const basics = working.basics ?? {};
  const work = (working.work ?? []) as Array<Record<string, any>>;
  const education = (working.education ?? []) as Array<Record<string, any>>;
  const skills = (working.skills ?? []) as Array<Record<string, any>>;
  const projects = (working.projects ?? []) as Array<Record<string, any>>;

  return (
    <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
      <div className="mb-stack-lg flex items-start justify-between gap-stack-md flex-wrap">
        <div>
          <h1 className="text-display font-display text-on-surface mb-stack-xs">
            Settings &amp; Configuration
          </h1>
          <p className="text-body-lg font-body-lg text-on-surface-variant">
            Manage your canonical CV source, tags, and high-impact flags.
          </p>
        </div>
        <div className="flex items-center gap-stack-sm">
          {saveState.kind === "saved" && (
            <span className="text-label-md font-label-md text-on-surface-variant">
              Saved to {saveState.path}
            </span>
          )}
          <button
            type="button"
            onClick={save}
            disabled={!isDirty || saveState.kind === "saving"}
            className="bg-primary text-on-primary text-body-md font-body-md font-medium py-stack-sm px-stack-lg rounded-lg hover:bg-primary-container disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saveState.kind === "saving" ? "Saving..." : "Save"}
          </button>
        </div>
      </div>

      {saveState.kind === "error" && (
        <div className="mb-stack-md border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
          {saveState.message}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-gutter">
        <div className="lg:col-span-8 flex flex-col gap-gutter">
          <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-lg flex flex-col gap-stack-md shadow-sm">
            <header className="border-b border-outline-variant pb-stack-md">
              <h2 className="text-headline-md font-headline-md text-on-surface">
                Basics
              </h2>
              <p className="text-label-md font-label-md text-on-surface-variant mt-stack-xs">
                Identity and contact details (JSON Resume `basics`).
              </p>
            </header>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-stack-md">
              <BasicsField
                label="Name"
                value={basics.name ?? ""}
                onChange={(v) => updateBasics("name", v)}
              />
              <BasicsField
                label="Label"
                value={basics.label ?? ""}
                onChange={(v) => updateBasics("label", v)}
              />
              <BasicsField
                label="Email"
                value={basics.email ?? ""}
                onChange={(v) => updateBasics("email", v)}
              />
              <BasicsField
                label="Phone"
                value={basics.phone ?? ""}
                onChange={(v) => updateBasics("phone", v)}
              />
              <BasicsField
                label="URL"
                value={basics.url ?? ""}
                onChange={(v) => updateBasics("url", v)}
              />
            </div>

            <div>
              <label className="block text-label-md font-label-md text-on-surface-variant mb-stack-xs">
                Summary
              </label>
              <textarea
                value={basics.summary ?? ""}
                onChange={(event) =>
                  updateBasics("summary", event.target.value)
                }
                className="w-full h-32 bg-surface border border-outline-variant rounded-lg p-stack-sm text-body-md font-body-md text-on-surface focus:border-primary focus:outline-none resize-none"
              />
            </div>
          </section>

          <Section
            title="Work"
            description="Per-entry tags and the high-impact flag (FR2, FR3) gate downstream tailoring + content-loss checks."
            empty={work.length === 0 ? "No work entries yet." : undefined}
          >
            {work.map((entry, idx) => (
              <EntryCard
                key={`work-${idx}`}
                title={entry.position ?? entry.name ?? `Work entry ${idx + 1}`}
                subtitle={[entry.name, entry.startDate, entry.endDate]
                  .filter(Boolean)
                  .join(" - ")}
                tags={entry.tags}
                highImpact={entry.highImpact}
                onTagsChange={(next) => setEntryTags("work", idx, next)}
                onHighImpactChange={(next) =>
                  setEntryHighImpact("work", idx, next)
                }
              >
                {entry.summary && (
                  <p className="text-body-md font-body-md text-on-surface-variant">
                    {entry.summary}
                  </p>
                )}
                {Array.isArray(entry.highlights) &&
                  entry.highlights.length > 0 && (
                    <ul className="list-disc pl-stack-md flex flex-col gap-stack-xs">
                      {(entry.highlights as string[]).map((h, hi) => (
                        <li
                          key={hi}
                          className="text-body-md font-body-md text-on-surface"
                        >
                          {h}
                        </li>
                      ))}
                    </ul>
                  )}
              </EntryCard>
            ))}
          </Section>

          <Section
            title="Education"
            empty={education.length === 0 ? "No education entries yet." : undefined}
          >
            {education.map((entry, idx) => (
              <EntryCard
                key={`education-${idx}`}
                title={entry.institution ?? `Education entry ${idx + 1}`}
                subtitle={[entry.studyType, entry.area, entry.startDate, entry.endDate]
                  .filter(Boolean)
                  .join(" - ")}
                tags={entry.tags}
                highImpact={entry.highImpact}
                onTagsChange={(next) => setEntryTags("education", idx, next)}
                onHighImpactChange={(next) =>
                  setEntryHighImpact("education", idx, next)
                }
              />
            ))}
          </Section>
        </div>

        <div className="lg:col-span-4 flex flex-col gap-gutter">
          <Section
            title="Skills"
            empty={skills.length === 0 ? "No skills entries yet." : undefined}
          >
            {skills.map((entry, idx) => (
              <EntryCard
                key={`skill-${idx}`}
                title={entry.name ?? `Skill ${idx + 1}`}
                subtitle={entry.level}
                tags={entry.tags}
                highImpact={entry.highImpact}
                onTagsChange={(next) => setEntryTags("skills", idx, next)}
                onHighImpactChange={(next) =>
                  setEntryHighImpact("skills", idx, next)
                }
              >
                {Array.isArray(entry.keywords) && entry.keywords.length > 0 && (
                  <p className="text-body-md font-body-md text-on-surface-variant">
                    {(entry.keywords as string[]).join(", ")}
                  </p>
                )}
              </EntryCard>
            ))}
          </Section>

          <Section
            title="Projects"
            empty={projects.length === 0 ? "No project entries yet." : undefined}
          >
            {projects.map((entry, idx) => (
              <EntryCard
                key={`project-${idx}`}
                title={entry.name ?? `Project ${idx + 1}`}
                subtitle={[entry.startDate, entry.endDate]
                  .filter(Boolean)
                  .join(" - ")}
                tags={entry.tags}
                highImpact={entry.highImpact}
                onTagsChange={(next) => setEntryTags("projects", idx, next)}
                onHighImpactChange={(next) =>
                  setEntryHighImpact("projects", idx, next)
                }
              >
                {entry.description && (
                  <p className="text-body-md font-body-md text-on-surface-variant">
                    {entry.description}
                  </p>
                )}
              </EntryCard>
            ))}
          </Section>
        </div>
      </div>
    </div>
  );
}

type BasicsFieldProps = {
  label: string;
  value: string;
  onChange: (next: string) => void;
};

function BasicsField({ label, value, onChange }: BasicsFieldProps) {
  return (
    <div>
      <label className="block text-label-md font-label-md text-on-surface-variant mb-stack-xs">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full h-10 px-stack-sm bg-surface border border-outline-variant rounded-lg text-body-md font-body-md text-on-surface focus:border-primary focus:outline-none"
      />
    </div>
  );
}

type SectionProps = {
  title: string;
  description?: string;
  empty?: string;
  children?: React.ReactNode;
};

function Section({ title, description, empty, children }: SectionProps) {
  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-stack-lg flex flex-col gap-stack-md shadow-sm">
      <header className="border-b border-outline-variant pb-stack-md">
        <h2 className="text-headline-md font-headline-md text-on-surface">
          {title}
        </h2>
        {description && (
          <p className="text-label-md font-label-md text-on-surface-variant mt-stack-xs">
            {description}
          </p>
        )}
      </header>
      {empty ? (
        <p className="text-body-md font-body-md text-on-surface-variant">
          {empty}
        </p>
      ) : (
        <div className="flex flex-col gap-stack-md">{children}</div>
      )}
    </section>
  );
}
