import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";

type Props = {
  /** Raw markdown — rendered with the library's default safe pipeline. */
  source: string;
};

type MdNode = { children?: ReactNode };
type MdAnchor = MdNode & { href?: string };

/** Renders markdown safely (no raw HTML, no scripts) — FR44 trust boundary. */
export function MarkdownRenderer({ source }: Props) {
  return (
    <div className="prose-jh flex flex-col gap-stack-sm text-body-md font-body-md text-on-surface">
      <ReactMarkdown
        // react-markdown 9 disables raw HTML by default — no additional
        // rehype-raw plugin is passed, so model output cannot inject scripts
        // or arbitrary HTML even if it includes `<...>` tags.
        skipHtml
        components={{
          h1: ({ children }: MdNode) => (
            <h1 className="text-headline-lg font-headline-lg text-on-surface mt-stack-md">
              {children}
            </h1>
          ),
          h2: ({ children }: MdNode) => (
            <h2 className="text-headline-md font-headline-md text-on-surface mt-stack-md">
              {children}
            </h2>
          ),
          h3: ({ children }: MdNode) => (
            <h3 className="text-body-lg font-body-lg font-semibold text-on-surface mt-stack-sm">
              {children}
            </h3>
          ),
          p: ({ children }: MdNode) => (
            <p className="text-body-md font-body-md text-on-surface">
              {children}
            </p>
          ),
          ul: ({ children }: MdNode) => (
            <ul className="list-disc pl-stack-md flex flex-col gap-stack-xs">
              {children}
            </ul>
          ),
          ol: ({ children }: MdNode) => (
            <ol className="list-decimal pl-stack-md flex flex-col gap-stack-xs">
              {children}
            </ol>
          ),
          li: ({ children }: MdNode) => (
            <li className="text-body-md font-body-md text-on-surface">
              {children}
            </li>
          ),
          strong: ({ children }: MdNode) => (
            <strong className="font-semibold text-on-surface">{children}</strong>
          ),
          em: ({ children }: MdNode) => (
            <em className="italic text-on-surface">{children}</em>
          ),
          a: ({ href, children }: MdAnchor) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline hover:text-primary-container"
            >
              {children}
            </a>
          ),
          code: ({ children }: MdNode) => (
            <code className="bg-surface-container-low border border-outline-variant rounded px-1 text-body-md font-body-md">
              {children}
            </code>
          ),
          pre: ({ children }: MdNode) => (
            <pre className="bg-surface-container-low border border-outline-variant rounded-lg p-stack-sm overflow-x-auto text-body-md font-body-md">
              {children}
            </pre>
          ),
          blockquote: ({ children }: MdNode) => (
            <blockquote className="border-l-4 border-outline-variant pl-stack-sm text-body-md font-body-md text-on-surface-variant italic">
              {children}
            </blockquote>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
