import { useEffect, useRef, useState } from "react";

/**
 * Confirmation modal for the Story 6.4 Approve action.
 *
 * Surfaced from `PackagePage.tsx` when `metadata.held === true`. Asks the
 * operator for two structured fields before POSTing to
 * `/api/override/<slug>`:
 *
 *   - `reason` — non-empty text. The textarea trims its value before
 *     submission and disables Submit when the trimmed value is empty.
 *   - `ack_drift` — checkbox the operator must tick. Submit stays
 *     disabled until both fields are valid, matching the route's
 *     server-side `StrictBool` + `min_length=1` contract so the UI and
 *     the API agree on what "valid" means.
 *
 * Accessibility:
 *   - `role="dialog"` + `aria-modal="true"` + `aria-labelledby` so
 *     screen readers announce the dialog by its title.
 *   - Escape closes the modal (cancel) without firing the request.
 *   - The reason textarea autofocuses on mount.
 */

type Props = {
  slug: string;
  onClose: () => void;
  onSuccess: (note: string) => void;
};

type SubmitState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; status: number | null; message: string };

type OverrideErrorEntry = {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
};

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts: string[] = [];
    for (const item of detail as OverrideErrorEntry[]) {
      const field =
        Array.isArray(item.loc) && item.loc.length > 0
          ? String(item.loc[item.loc.length - 1])
          : "field";
      const msg = item.msg ?? item.type ?? "invalid";
      parts.push(`${field}: ${msg}`);
    }
    return parts.join("; ");
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return "unknown error";
  }
}

export function ApproveOverrideModal({ slug, onClose, onSuccess }: Props) {
  const [reason, setReason] = useState("");
  const [ackDrift, setAckDrift] = useState(false);
  const [submitState, setSubmitState] = useState<SubmitState>({ kind: "idle" });
  const reasonRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    reasonRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const trimmedReason = reason.trim();
  const canSubmit =
    trimmedReason.length > 0 &&
    ackDrift &&
    submitState.kind !== "submitting";

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitState({ kind: "submitting" });
    try {
      const response = await fetch(
        `/api/override/${encodeURIComponent(slug)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reason: trimmedReason,
            ack_drift: ackDrift,
          }),
        },
      );
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setSubmitState({
          kind: "error",
          status: response.status,
          message: formatErrorDetail(body.detail),
        });
        return;
      }
      const note =
        typeof body.note === "string"
          ? body.note
          : `Overridden. Open ./out/_overridden/${slug}/ and submit when ready.`;
      onSuccess(note);
    } catch (exc) {
      setSubmitState({
        kind: "error",
        status: null,
        message: String(exc),
      });
    }
  }

  const titleId = `approve-override-title-${slug}`;
  const reasonId = `approve-override-reason-${slug}`;
  const ackId = `approve-override-ack-${slug}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/60 px-stack-md"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="bg-surface-container-lowest border border-outline-variant rounded-xl shadow-lg max-w-lg w-full p-stack-lg flex flex-col gap-stack-md"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex flex-col gap-stack-xs">
          <h2
            id={titleId}
            className="text-headline-md font-headline-md text-on-surface"
          >
            Approve override
          </h2>
          <p className="text-body-md font-body-md text-on-surface-variant">
            Releasing <code className="font-mono">{slug}</code> moves it to
            <code className="font-mono"> ./out/_overridden/{slug}/</code>. No
            submission happens — you still hand it in yourself.
          </p>
        </header>

        <form className="flex flex-col gap-stack-md" onSubmit={onSubmit}>
          <div className="flex flex-col gap-stack-xs">
            <label
              htmlFor={reasonId}
              className="text-label-md font-label-md uppercase tracking-wider text-on-surface-variant"
            >
              Reason (required)
            </label>
            <textarea
              ref={reasonRef}
              id={reasonId}
              required
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              placeholder="Why is releasing this package OK?"
              className="bg-surface border border-outline-variant rounded-lg p-stack-sm text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant/60 focus:outline-none focus:border-primary"
            />
          </div>

          <label
            htmlFor={ackId}
            className="flex items-start gap-stack-sm cursor-pointer select-none"
          >
            <input
              id={ackId}
              type="checkbox"
              checked={ackDrift}
              onChange={(event) => setAckDrift(event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary"
            />
            <span className="text-body-md font-body-md text-on-surface">
              I have reviewed the drift report and accept the risk.
            </span>
          </label>

          {submitState.kind === "error" && (
            <div
              role="alert"
              className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-sm text-body-md font-body-md"
            >
              {submitState.status === 404
                ? `Package not found (404): ${submitState.message}`
                : submitState.status === 409
                  ? `Conflict (409): ${submitState.message}`
                  : submitState.status === 422
                    ? `Validation failed (422): ${submitState.message}`
                    : `Override failed${
                        submitState.status ? ` (${submitState.status})` : ""
                      }: ${submitState.message}`}
            </div>
          )}

          <div className="flex justify-end gap-stack-sm">
            <button
              type="button"
              onClick={onClose}
              className="px-stack-md py-stack-sm rounded-lg border border-outline-variant text-body-md font-body-md text-on-surface hover:bg-surface-container-high transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="px-stack-md py-stack-sm rounded-lg bg-primary text-on-primary text-body-md font-body-md font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitState.kind === "submitting" ? "Submitting..." : "Submit"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
