/**
 * ScenarioOverlay — full-viewport modal showing scenario details + graph ontology.
 *
 * Purpose:
 *   Renders a centered modal overlay with all scenario metadata:
 *   display name, description, domain/version, use cases, example
 *   questions (with copy-to-clipboard buttons), and the graph ontology
 *   tables (vertices + edges) parsed from graph_schema.yaml.
 *
 * Isolation:
 *   Pure rendering component. Reads from ``ScenarioInfo`` prop only.
 *   No store imports, no network requests, no side effects.
 *   Cannot affect chat, sessions, observability, or any other feature.
 *
 * Key collaborators:
 *   - components/layout/Header.tsx — opens/closes this overlay via local useState
 *   - hooks/useScenario.ts — provides the ScenarioInfo data
 *
 * Dependents:
 *   Called by: Header.tsx only
 */

import { useState, useCallback, useEffect } from "react";
import type { ScenarioInfo } from "@/hooks/useScenario";

interface ScenarioOverlayProps {
  /** Scenario metadata to display. */
  scenario: ScenarioInfo;
  /** Callback to close the overlay. */
  onClose: () => void;
}

/**
 * Full-viewport modal overlay showing scenario info + graph ontology.
 * Closes on backdrop click, Escape key, or the close button.
 */
export function ScenarioOverlay({ scenario, onClose }: ScenarioOverlayProps) {
  /* Per-section text scale (percentage) */
  const [infoScale, setInfoScale] = useState(100);
  const [vertexScale, setVertexScale] = useState(100);
  const [edgeScale, setEdgeScale] = useState(100);
  /* Graph ontology tables default to collapsed */
  const [showVertices, setShowVertices] = useState(false);
  const [showEdges, setShowEdges] = useState(false);

  /* Close on Escape key */
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  /* Deduplicate edges for display (same label+source+target may appear
     multiple times for bidirectional links like connects_to source/target) */
  const uniqueEdges = scenario.graph_schema?.edges
    ? deduplicateEdges(scenario.graph_schema.edges)
    : [];

  return (
    /* Backdrop — click to close */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      {/* Modal container — stop click propagation so clicks inside don't close */}
      <div
        className="relative w-full max-w-5xl max-h-[92vh] mx-4 rounded-xl bg-neutral-bg1 border border-border shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button — top right */}
        <button
          onClick={onClose}
          className="absolute top-3 right-4 text-text-muted hover:text-text-primary text-lg leading-none transition-colors z-10"
          title="Close"
        >
          ✕
        </button>

        {/* Scrollable content */}
        <div className="overflow-y-auto p-6 space-y-6">
          {/* Header: title + domain/version badges */}
          <div>
            <h2 className="text-lg font-bold text-text-primary leading-tight pr-8">
              <span className="text-brand mr-2">◆</span>
              {scenario.display_name}
            </h2>
            <div className="flex items-center gap-2 mt-2">
              {scenario.domain && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand/10 text-brand border border-brand/20 font-medium">
                  {scenario.domain}
                </span>
              )}
              {scenario.version && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-neutral-bg3 text-text-muted border border-border font-medium">
                  v{scenario.version}
                </span>
              )}
            </div>
          </div>

          {/* Description */}
          {scenario.description && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <SectionHeading>Description</SectionHeading>
                <ScaleSlider value={infoScale} onChange={setInfoScale} />
              </div>
              <p className="text-text-secondary leading-relaxed" style={{ fontSize: `${Math.round(14 * infoScale / 100)}px` }}>
                {scenario.description}
              </p>
            </div>
          )}

          {/* Use cases */}
          {scenario.use_cases.length > 0 && (
            <section>
              <SectionHeading>Use Cases</SectionHeading>
              <ul className="space-y-1.5">
                {scenario.use_cases.map((uc, i) => (
                  <li
                    key={i}
                    className="text-text-secondary flex gap-2"
                    style={{ fontSize: `${Math.round(14 * infoScale / 100)}px` }}
                  >
                    <span className="text-brand shrink-0">•</span>
                    <span>{uc}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Example questions — each in a card with copy button */}
          {scenario.example_questions.length > 0 && (
            <section>
              <SectionHeading>Example Questions</SectionHeading>
              <div className="space-y-2" style={{ fontSize: `${Math.round(14 * infoScale / 100)}px` }}>
                {scenario.example_questions.map((q, i) => (
                  <QuestionCard key={i} question={q} />
                ))}
              </div>
            </section>
          )}

          {/* Graph ontology — vertices table (collapsed by default) */}
          {scenario.graph_schema &&
            scenario.graph_schema.vertices.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-2">
                  <button
                    onClick={() => setShowVertices((v) => !v)}
                    className="flex items-center gap-1 text-text-primary hover:text-brand transition-colors"
                  >
                    <span className="text-xs">{showVertices ? "▼" : "▶"}</span>
                    <SectionHeading>
                      Graph Ontology — Vertices ({scenario.graph_schema.vertices.length})
                    </SectionHeading>
                  </button>
                  {showVertices && <ScaleSlider value={vertexScale} onChange={setVertexScale} />}
                </div>
                {showVertices && (
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full" style={{ fontSize: `${Math.round(13 * vertexScale / 100)}px` }}>
                    <thead>
                      <tr className="bg-neutral-bg2 text-text-muted">
                        <th className="text-left px-3 py-2 font-semibold w-40">
                          Label
                        </th>
                        <th className="text-left px-3 py-2 font-semibold">
                          Properties
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {scenario.graph_schema.vertices.map((v, i) => (
                        <tr
                          key={i}
                          className="border-t border-border hover:bg-neutral-bg2/50"
                        >
                          <td className="px-3 py-1.5 font-medium text-brand">
                            {v.label}
                          </td>
                          <td className="px-3 py-1.5 text-text-secondary font-mono">
                            {v.properties.join(", ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                )}
              </section>
            )}          {/* Graph ontology — edges table (collapsed by default) */}
          {uniqueEdges.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-2">
                <button
                  onClick={() => setShowEdges((v) => !v)}
                  className="flex items-center gap-1 text-text-primary hover:text-brand transition-colors"
                >
                  <span className="text-xs">{showEdges ? "▼" : "▶"}</span>
                  <SectionHeading>
                    Graph Ontology — Edges ({uniqueEdges.length})
                  </SectionHeading>
                </button>
                {showEdges && <ScaleSlider value={edgeScale} onChange={setEdgeScale} />}
              </div>
              {showEdges && (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full" style={{ fontSize: `${Math.round(13 * edgeScale / 100)}px` }}>
                  <thead>
                    <tr className="bg-neutral-bg2 text-text-muted">
                      <th className="text-left px-3 py-2 font-semibold">
                        Relationship
                      </th>
                      <th className="text-left px-3 py-2 font-semibold">
                        Source
                      </th>
                      <th className="text-left px-3 py-2 font-semibold">
                        Target
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {uniqueEdges.map((e, i) => (
                      <tr
                        key={i}
                        className="border-t border-border hover:bg-neutral-bg2/50"
                      >
                        <td className="px-3 py-1.5 font-medium text-text-primary">
                          {e.label}
                        </td>
                        <td className="px-3 py-1.5 text-brand font-mono">
                          {e.source}
                        </td>
                        <td className="px-3 py-1.5 text-brand font-mono">
                          {e.target}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/** Section heading with a subtle line below. */
function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-2 pb-1 border-b border-border">
      {children}
    </h3>
  );
}

/** Individual question card with a copy-to-clipboard button. */
function QuestionCard({ question }: { question: string }) {
  /* "idle" | "copied" — controls the copy button label */
  const [copied, setCopied] = useState(false);

  /** Copy question text to clipboard and show "Copied!" for 1.5s. */
  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(question);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* Clipboard API may fail in non-HTTPS contexts — fail silently */
    }
  }, [question]);

  return (
    <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg border border-border bg-neutral-bg2/50 hover:bg-neutral-bg2 transition-colors group">
      {/* Question text */}
      <span className="text-sm text-text-primary flex-1 leading-snug">
        {question}
      </span>
      {/* Copy button */}
      <button
        onClick={handleCopy}
        className="shrink-0 text-[10px] px-2 py-0.5 rounded border border-border text-text-muted hover:text-brand hover:border-brand/30 transition-colors opacity-0 group-hover:opacity-100"
        title="Copy to clipboard"
      >
        {copied ? "✓ Copied" : "📋 Copy"}
      </button>
    </div>
  );
}

/**
 * Deduplicate edges that share the same label + source + target.
 * (e.g. connects_to appears twice for source/target sides of a link)
 */
function deduplicateEdges(
  edges: { label: string; source: string; target: string }[]
): { label: string; source: string; target: string }[] {
  const seen = new Set<string>();
  return edges.filter((e) => {
    const key = `${e.label}|${e.source}|${e.target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Per-table text scale slider — compact inline range input. */
function ScaleSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 shrink-0">
      <input
        type="range"
        min={70}
        max={180}
        step={5}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="accent-brand cursor-pointer"
        style={{ width: "80px", height: "4px" }}
        title={`Text scale: ${value}%`}
      />
      <span className="text-[10px] font-mono text-text-muted w-8 text-right">
        {value}%
      </span>
    </div>
  );
}
