import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DriftDetailPane, type DriftDocument } from "./components/DriftDetailPane";

type FetchState =
  | { kind: "loading" }
  | { kind: "ready"; payload: DriftDocument }
  | { kind: "error"; status: number | null; message: string };

export function DriftPage() {
  const { slug } = useParams<{ slug: string }>();
  const [fetchState, setFetchState] = useState<FetchState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    if (!slug) {
      setFetchState({ kind: "error", status: null, message: "missing_slug_in_route" });
      return;
    }
    setFetchState({ kind: "loading" });
    async function load() {
      try {
        const response = await fetch(`/api/package/${encodeURIComponent(slug!)}/drift`);
        const body = await response.json();
        if (cancelled) return;
        if (!response.ok) {
          const message =
            typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          setFetchState({ kind: "error", status: response.status, message });
          return;
        }
        setFetchState({ kind: "ready", payload: body as DriftDocument });
      } catch (exc) {
        if (cancelled) return;
        setFetchState({ kind: "error", status: null, message: String(exc) });
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (fetchState.kind === "loading") {
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
        <p className="text-body-md font-body-md text-on-surface-variant">
          Loading drift report...
        </p>
      </div>
    );
  }

  if (fetchState.kind === "error") {
    const is404 = fetchState.status === 404;
    return (
      <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full flex flex-col gap-stack-md">
        <div className="border border-error bg-error-container text-on-error-container rounded-lg p-stack-md text-body-md font-body-md">
          {is404 ? (
            <>
              No drift report exists for package{" "}
              <code className="font-mono">{slug}</code>. This is normal for
              packages staged before the fabrication matcher landed (Epic 1
              walking-skeleton runs).
            </>
          ) : (
            <>Failed to load drift report: {fetchState.message}</>
          )}
        </div>
        <div className="flex gap-stack-md">
          <Link
            to={`/packages/${slug ?? ""}`}
            className="text-primary underline text-body-md font-body-md"
          >
            Back to package
          </Link>
          <Link to="/" className="text-primary underline text-body-md font-body-md">
            Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-margin-mobile md:p-margin-desktop max-w-container-max mx-auto w-full">
      <DriftDetailPane slug={slug!} doc={fetchState.payload} showPageHeader />
    </div>
  );
}
