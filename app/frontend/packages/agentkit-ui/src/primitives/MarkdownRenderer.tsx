/**
 * @module MarkdownRenderer
 *
 * Markdown renderer — converts raw markdown strings into styled React
 * elements using `react-markdown` with `react-syntax-highlighter`.
 *
 * Rendering features:
 *   - Syntax-highlighted fenced code blocks with a language label and
 *     copy-to-clipboard button (theme: One Dark)
 *   - Inline `code` spans with muted background styling
 *   - External links open in a new tab (`target="_blank"`)
 *   - Standard markdown elements: tables, lists, blockquotes, headings
 *
 * The `CodeBlock` sub-component detects fenced blocks via the
 * `language-<lang>` className injected by react-markdown and delegates
 * to Prism’s `SyntaxHighlighter`; inline code falls through to a
 * styled `<code>` span.
 *
 * @props
 *   - `content` — raw markdown string to render
 *
 * @collaborators
 *   - `react-markdown`             — markdown-to-React transform
 *   - `react-syntax-highlighter`   — Prism-based code block highlighting
 *   - `lucide-react` (Copy, Check) — copy button icons
 *
 * @dependents
 *   Used by {@link TextBlock} and any other
 *   component that needs rich markdown output.
 */

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check } from "lucide-react";

interface MarkdownRendererProps {
  content: string;
  /** Extra classes merged onto the prose wrapper (e.g. forced text colour). */
  className?: string;
}

export function MarkdownRenderer({ content, className: extraClass }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      className={`prose max-w-none break-words [font-size:inherit]
        prose-headings:text-[inherit] prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
        prose-p:text-[inherit] prose-p:leading-relaxed
        prose-strong:text-[inherit]
        prose-li:text-[inherit]
        prose-blockquote:border-brand/30 prose-blockquote:text-[inherit]
        ${extraClass ?? ""}`}
      components={{
        code: CodeBlock,
        /* Custom table rendering — scrollable container with rounded borders,
           zebra-striped rows, and a styled header. Overrides default prose
           table styles for a cleaner, more polished look. */
        table: ({ children }) => (
          <div className="my-3 overflow-x-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-[0.85em]">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-neutral-bg3 text-text-muted text-[0.7em] uppercase tracking-wider">
            {children}
          </thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-2 text-left font-semibold border-b border-border whitespace-nowrap">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1.5 text-text-secondary border-b border-border/50 whitespace-nowrap">
            {children}
          </td>
        ),
        tr: ({ children, ...props }) => {
          /* Zebra striping — even rows get a subtle background tint */
          const isInBody = !(props as { node?: { position?: { start?: { line?: number } } } }).node?.position;
          return (
            <tr className={`transition-colors hover:bg-neutral-bg3/50 ${isInBody ? "even:bg-neutral-bg2/50" : ""}`}>
              {children}
            </tr>
          );
        },
        a: ({ children, href, ...props }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand hover:underline"
            {...props}
          >
            {children}
          </a>
        ),
        pre: ({ children }) => <>{children}</>,
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

// ── Code Block with Copy Button ─────────────────────────────────────────────

function CodeBlock({
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  const [copied, setCopied] = useState(false);

  const match = /language-(\w+)/.exec(className ?? "");
  const language = match?.[1] ?? "";
  const code = String(children).replace(/\n$/, "");

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  // Inline code (no language class)
  if (!match) {
    return (
      <code
        className="rounded bg-neutral-bg3 px-1.5 py-0.5 text-xs font-mono text-brand"
        {...props}
      >
        {children}
      </code>
    );
  }

  // Fenced code block
  return (
    <div className="group relative my-3 rounded-lg overflow-hidden border border-border">
      {/* Language label + copy button */}
      <div className="flex items-center justify-between bg-neutral-bg3 px-3 py-1.5 text-xs text-text-muted">
        <span className="font-mono uppercase">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity hover:text-text-primary"
          aria-label="Copy code"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      <SyntaxHighlighter
        style={oneDark}
        language={language}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: "0.8rem",
          background: "var(--color-bg-2)",
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
