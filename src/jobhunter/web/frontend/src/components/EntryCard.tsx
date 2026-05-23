import { ReactNode } from "react";
import { TagInput } from "./TagInput";
import { HighImpactToggle } from "./HighImpactToggle";

type Props = {
  title: string;
  subtitle?: string;
  tags: string[] | undefined;
  highImpact: boolean | undefined;
  onTagsChange: (next: string[] | undefined) => void;
  onHighImpactChange: (next: boolean) => void;
  children?: ReactNode;
};

export function EntryCard({
  title,
  subtitle,
  tags,
  highImpact,
  onTagsChange,
  onHighImpactChange,
  children,
}: Props) {
  return (
    <article className="bg-surface border border-outline-variant rounded-lg p-stack-md flex flex-col gap-stack-sm">
      <header className="flex items-start justify-between gap-stack-md">
        <div className="min-w-0">
          <h4 className="text-body-md font-body-md font-semibold text-on-surface truncate">
            {title}
          </h4>
          {subtitle && (
            <p className="text-label-md font-label-md text-on-surface-variant mt-stack-xs">
              {subtitle}
            </p>
          )}
        </div>
        <HighImpactToggle value={highImpact} onChange={onHighImpactChange} />
      </header>

      {children && <div className="flex flex-col gap-stack-xs">{children}</div>}

      <div>
        <div className="text-label-md font-label-md text-on-surface-variant uppercase tracking-wider mb-stack-xs">
          Tags
        </div>
        <TagInput tags={tags} onChange={onTagsChange} />
      </div>
    </article>
  );
}
