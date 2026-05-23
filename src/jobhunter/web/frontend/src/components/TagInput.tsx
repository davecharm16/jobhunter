import { useState, KeyboardEvent } from "react";

type Props = {
  tags: string[] | undefined;
  onChange: (next: string[] | undefined) => void;
};

export function TagInput({ tags, onChange }: Props) {
  const [draft, setDraft] = useState("");
  const items = tags ?? [];

  function commit() {
    const value = draft.trim();
    if (!value) return;
    if (items.includes(value)) {
      setDraft("");
      return;
    }
    onChange([...items, value]);
    setDraft("");
  }

  function remove(idx: number) {
    const next = items.filter((_, i) => i !== idx);
    onChange(next.length === 0 && tags === undefined ? undefined : next);
  }

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && draft === "" && items.length > 0) {
      remove(items.length - 1);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-stack-xs">
      {items.map((tag, idx) => (
        <span
          key={`${tag}-${idx}`}
          className="inline-flex items-center gap-stack-xs px-stack-sm py-stack-xs rounded-full bg-secondary-container text-on-primary-fixed-variant text-label-md font-label-md"
        >
          {tag}
          <button
            type="button"
            onClick={() => remove(idx)}
            className="text-on-primary-fixed-variant hover:text-primary"
            aria-label={`Remove tag ${tag}`}
          >
            x
          </button>
        </span>
      ))}
      <input
        type="text"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKey}
        onBlur={commit}
        placeholder={items.length === 0 ? "Add tag and press Enter" : "Add tag"}
        className="flex-1 min-w-[8rem] bg-transparent text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant focus:outline-none"
      />
    </div>
  );
}
