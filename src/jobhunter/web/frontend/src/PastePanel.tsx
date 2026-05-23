import { useState } from "react";
import { useNavigate } from "react-router-dom";

type PasteResponse = {
  slug: string;
  cv_path: string;
  cover_letter_path: string;
  cost_usd: string;
};

type Props = {
  jdText: string;
  setJdText: (value: string) => void;
};

export function PastePanel({ jdText, setJdText }: Props) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/paste", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: jdText, source: "browser" }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
        return;
      }
      const { slug } = body as PasteResponse;
      navigate(`/packages/${encodeURIComponent(slug)}`);
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter flex flex-col gap-stack-md">
      <h4 className="text-headline-md font-headline-md text-on-surface">
        Paste a job description
      </h4>
      <textarea
        className="w-full h-48 bg-surface-container-low border border-outline-variant rounded-lg p-stack-md text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none resize-none"
        placeholder="Paste the full job description here..."
        value={jdText}
        onChange={(event) => setJdText(event.target.value)}
        disabled={busy}
      />
      <div className="flex justify-end">
        <button
          type="button"
          onClick={submit}
          disabled={busy || jdText.trim().length === 0}
          className="bg-primary text-on-primary text-body-md font-body-md font-medium py-stack-sm px-stack-lg rounded-lg hover:bg-primary-container disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? "Tailoring..." : "Tailor this JD"}
        </button>
      </div>

      {error && (
        <div className="border border-error rounded-lg p-stack-md text-error text-body-md font-body-md">
          {error}
        </div>
      )}
    </section>
  );
}
