import { useState } from "react";
import { Sidebar } from "./Sidebar";
import { PastePanel } from "./PastePanel";

export function App() {
  const [jdText, setJdText] = useState("");

  return (
    <div className="min-h-full flex bg-surface text-on-surface">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-16 px-gutter flex items-center border-b border-outline-variant bg-surface">
          <h2 className="text-headline-lg font-headline-lg text-on-surface">
            Dashboard
          </h2>
        </header>
        <div className="p-gutter max-w-container-max mx-auto w-full flex flex-col gap-stack-lg">
          <div>
            <h3 className="text-display font-display text-on-surface mb-stack-sm">
              Start a new application
            </h3>
            <p className="text-body-lg font-body-lg text-on-surface-variant">
              Paste a job description and tailor a CV + cover letter against
              your canonical CV.
            </p>
          </div>
          <PastePanel jdText={jdText} setJdText={setJdText} />
        </div>
      </main>
    </div>
  );
}
