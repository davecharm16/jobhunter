import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

// Downscale the screenshot and JPEG-encode it, stepping size/quality DOWN until
// the base64 is comfortably under Linux's 128KB single-arg limit (MAX_ARG_STRLEN)
// — the n8n vision command embeds this base64, so an over-limit payload causes
// `spawn E2BIG`. The loop guarantees any screenshot fits. Returns {b64, contentType}.
function fileToDownscaledBase64(
  file: File,
  maxEdge = 1400,
): Promise<{ b64: string; contentType: string }> {
  // keep well under 128KB so the whole shell command stays within the arg limit
  const LIMIT = 90_000;
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("could not load image"));
      img.onload = () => {
        const encode = (scale: number, quality: number): string | null => {
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext("2d");
          if (!ctx) return null;
          ctx.drawImage(img, 0, 0, w, h);
          return canvas.toDataURL("image/jpeg", quality).split(",", 2)[1];
        };
        let scale = Math.min(1, maxEdge / Math.max(img.width, img.height));
        let b64: string | null = null;
        for (let attempt = 0; attempt < 8; attempt++) {
          const quality = Math.max(0.35, 0.8 - attempt * 0.08);
          b64 = encode(scale, quality);
          if (b64 === null) {
            reject(new Error("canvas not supported"));
            return;
          }
          if (b64.length <= LIMIT) break;
          scale *= 0.8; // still too big → shrink further next pass
        }
        resolve({ b64: b64 as string, contentType: "image/jpeg" });
      };
      img.src = String(reader.result || "");
    };
    reader.readAsDataURL(file);
  });
}

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

function IconPostAdd() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 -960 960 960"
      aria-hidden="true"
      className="w-6 h-6 fill-current"
    >
      <path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h360v80H200v560h560v-360h80v360q0 33-23.5 56.5T760-120H200Zm480-480v-80h-80v-80h80v-80h80v80h80v80h-80v80h-80ZM240-360h360v-80H240v80Zm0-120h240v-80H240v80Zm0-120h240v-80H240v80Z" />
    </svg>
  );
}

function IconArrowForward() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 -960 960 960"
      aria-hidden="true"
      className="w-4 h-4 fill-current"
    >
      <path d="m600-240-56-58 142-142H160v-80h526L544-662l56-58 240 240-240 240Z" />
    </svg>
  );
}

export function PastePanel({ jdText, setJdText }: Props) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [extracting, setExtracting] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function onScreenshot(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (files.length === 0) return;
    setExtracting(true);
    setError(null);
    try {
      const images = await Promise.all(
        files.map(async (f) => {
          const { b64, contentType } = await fileToDownscaledBase64(f);
          return { image_b64: b64, content_type: contentType };
        }),
      );
      const resp = await fetch("/api/extract-jd", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ images }),
      });
      const body = await resp.json();
      if (!resp.ok) {
        setError(
          typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail),
        );
        return;
      }
      setJdText(body.jd_text); // fill the box so you can review/edit before generating
    } catch (exc) {
      setError(String(exc));
    } finally {
      setExtracting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/paste", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jd_text: jdText,
          source: "browser",
          ...(url.trim() ? { url: url.trim() } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail),
        );
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
    <section id="paste-panel" className="bg-surface-container-lowest border border-outline-variant rounded-xl p-gutter shadow-sm flex flex-col gap-stack-md">
      {/* Header row with icon + title */}
      <div className="flex items-center gap-stack-md">
        <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-on-primary shrink-0">
          <IconPostAdd />
        </div>
        <div>
          <h3 className="text-headline-md font-headline-md text-on-surface">
            Start New Application
          </h3>
          <p className="text-body-md font-body-md text-on-surface-variant">
            Paste a job description to generate a tailored CV and cover letter.
          </p>
        </div>
      </div>

      {/* Upload a screenshot instead of pasting — fills the box below for review */}
      <div className="flex items-center gap-stack-sm">
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          onChange={onScreenshot}
          className="hidden"
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy || extracting}
          className="border border-outline-variant text-on-surface text-body-md font-body-md py-stack-sm px-stack-md rounded-lg hover:bg-surface-container-high disabled:opacity-50 transition-colors"
        >
          {extracting ? "Reading screenshot(s)…" : "📷 Upload screenshot(s)"}
        </button>
        <span className="text-body-sm text-on-surface-variant">
          one or more screenshots of a posting → extracted into the box below to review
        </span>
      </div>

      {/* Textarea */}
      <textarea
        className="w-full h-32 bg-surface-container-low border border-outline-variant rounded-lg p-stack-md text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none resize-none transition-colors"
        placeholder="Paste full job description here (responsibilities, requirements, etc.)..."
        value={jdText}
        onChange={(event) => setJdText(event.target.value)}
        disabled={busy}
      />

      {/* URL input */}
      <input
        type="url"
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        disabled={busy}
        placeholder="Job posting link (optional)"
        className="w-full bg-surface-container-low border border-outline-variant rounded-lg p-stack-md text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant focus:border-primary focus:outline-none transition-colors"
      />

      {/* CTA row */}
      <div className="flex justify-end">
        <button
          type="button"
          onClick={submit}
          disabled={busy || jdText.trim().length === 0}
          className="bg-primary text-on-primary text-body-md font-body-md font-medium py-stack-sm px-stack-lg rounded-lg hover:bg-primary-container disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-stack-xs transition-colors"
        >
          {busy ? "Tailoring..." : "Begin Tailoring"}
          {!busy && <IconArrowForward />}
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
