/**
 * OntologyStudio — "From Documents to Knowledge Graph" showcase overlay.
 *
 * Three panels: a document shelf (left), a document viewer with an Extract
 * button (centre), and the growing ontology graph (right). Extraction is a
 * scripted, staged animation: entities highlight inline in the document, then
 * stream into the ontology canvas as nodes + edges with live counters + a log.
 *
 * Fully client-side + deterministic (data from studioData.ts). Opened from the
 * sidebar via workshopStore; rendered in App.tsx.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { X, Sparkles, Check, FileText } from "lucide-react";
import { useWorkshopStore } from "@/stores/workshopStore";
import {
  STUDIO_DOCS,
  ENTITY_TYPE_INFO,
  REL_TYPE_INFO,
  ENTITY_PROPS,
  type StudioDoc,
  type StudioEntity,
} from "./studioData";
import { OntologyCanvas, typeColor, type OntoNode, type OntoLink } from "./OntologyCanvas";

const STEP_MS = 420;

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function sleep(ms: number, signal: { cancelled: boolean }): Promise<void> {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms);
    const check = setInterval(() => {
      if (signal.cancelled) {
        clearTimeout(t);
        clearInterval(check);
        resolve();
      }
    }, 60);
  });
}

/** Render document text with revealed entity IDs wrapped in coloured pills. */
function Highlighted({
  text,
  entities,
  revealed,
}: {
  text: string;
  entities: StudioEntity[];
  revealed: Set<string>;
}) {
  const active = entities
    .filter((e) => revealed.has(e.id))
    .sort((a, b) => b.id.length - a.id.length);
  if (active.length === 0) return <>{text}</>;
  const pattern = new RegExp("(" + active.map((e) => escapeRegExp(e.id)).join("|") + ")", "g");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, i) => {
        const ent = active.find((e) => e.id === part);
        if (!ent) return <span key={i}>{part}</span>;
        const c = typeColor(ent.type);
        return (
          <span
            key={i}
            className="rounded px-1 font-medium transition-colors"
            style={{ backgroundColor: c + "26", color: c, boxShadow: `inset 0 0 0 1px ${c}66` }}
            title={ent.type}
          >
            {part}
          </span>
        );
      })}
    </>
  );
}

/** Floating detail card for a clicked entity: type, definition, properties,
 *  source documents, and its relationships. */
function EntityDetail({
  id,
  nodes,
  links,
  onClose,
}: {
  id: string;
  nodes: OntoNode[];
  links: OntoLink[];
  onClose: () => void;
}) {
  const type = nodes.find((n) => n.id === id)?.type;
  if (!type) return null;
  const c = typeColor(type);
  const props = ENTITY_PROPS[id];
  const sources = STUDIO_DOCS.filter((d) => d.entities.some((e) => e.id === id));
  const out = links.filter((l) => l.source === id);
  const inc = links.filter((l) => l.target === id);

  return (
    <div className="absolute top-3 right-3 z-20 w-[290px] max-h-[calc(100%-1.5rem)] overflow-y-auto rounded-xl border border-white/15 bg-[#0f1930] shadow-2xl">
      <div className="flex items-start justify-between gap-2 px-3 py-2.5 border-b border-white/10">
        <div className="min-w-0">
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{ backgroundColor: c + "26", color: c, boxShadow: `inset 0 0 0 1px ${c}66` }}
          >
            {type}
          </span>
          <div className="mt-1 font-mono text-[12px] font-semibold text-white break-all">{id}</div>
        </div>
        <button onClick={onClose} aria-label="Close" className="shrink-0 rounded p-1 text-slate-400 hover:text-white hover:bg-white/10">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="p-3 space-y-3 text-[11px]">
        {ENTITY_TYPE_INFO[type] && <p className="text-slate-400 leading-relaxed">{ENTITY_TYPE_INFO[type]}</p>}
        {props && (
          <div>
            <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1">Properties</div>
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
              {Object.entries(props).map(([k, v]) => (
                <div key={k} className="contents">
                  <span className="text-slate-500">{k}</span>
                  <span className="text-slate-200 font-mono break-words">{v}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div>
          <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1">Extracted from</div>
          <div className="flex flex-wrap gap-1">
            {sources.map((d) => (
              <span key={d.id} className="rounded bg-white/5 border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-300">
                {d.icon} {d.docType}
              </span>
            ))}
          </div>
        </div>
        {(out.length > 0 || inc.length > 0) && (
          <div>
            <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1">Relationships</div>
            <div className="space-y-1">
              {out.map((l, i) => (
                <div key={`o${i}`} className="text-slate-300" title={REL_TYPE_INFO[l.type]}>
                  <span className="text-sky-300">{l.type}</span> → <span className="font-mono">{l.target}</span>
                </div>
              ))}
              {inc.map((l, i) => (
                <div key={`i${i}`} className="text-slate-400" title={REL_TYPE_INFO[l.type]}>
                  <span className="font-mono">{l.source}</span> <span className="text-sky-300">{l.type}</span> → this
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Ontology schema summary: every entity + relationship type with a definition. */
function SchemaPanel({
  nodes,
  links,
  onClose,
}: {
  nodes: OntoNode[];
  links: OntoLink[];
  onClose: () => void;
}) {
  const entTypes = [...new Set(nodes.map((n) => n.type))].sort();
  const relTypes = [...new Set(links.map((l) => l.type))].sort();
  const countOf = (t: string) => nodes.filter((n) => n.type === t).length;

  return (
    <div className="absolute top-3 left-3 z-20 w-[300px] max-h-[calc(100%-1.5rem)] overflow-y-auto rounded-xl border border-white/15 bg-[#0f1930] shadow-2xl">
      <div className="flex items-center justify-between gap-2 px-3 py-2.5 border-b border-white/10">
        <span className="text-xs font-semibold text-white">Ontology schema</span>
        <button onClick={onClose} aria-label="Close schema" className="rounded p-1 text-slate-400 hover:text-white hover:bg-white/10">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="p-3 space-y-3 text-[11px]">
        <div>
          <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1.5">
            Entity types ({entTypes.length})
          </div>
          <div className="space-y-1.5">
            {entTypes.map((t) => (
              <div key={t} className="flex items-start gap-2">
                <span className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: typeColor(t) }} />
                <div className="min-w-0">
                  <div className="text-slate-200">
                    <span className="font-semibold">{t}</span>{" "}
                    <span className="text-slate-500">· {countOf(t)}</span>
                  </div>
                  <div className="text-slate-500 leading-snug">{ENTITY_TYPE_INFO[t]}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1.5">
            Relationship types ({relTypes.length})
          </div>
          <div className="space-y-1">
            {relTypes.map((t) => (
              <div key={t}>
                <span className="text-sky-300 font-mono">{t}</span>
                <span className="text-slate-500"> — {REL_TYPE_INFO[t]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function OntologyStudio() {
  const open = useWorkshopStore((s) => s.studioOpen);
  const close = useWorkshopStore((s) => s.closeStudio);

  const [selectedId, setSelectedId] = useState<string>(STUDIO_DOCS[0].id);
  const [nodes, setNodes] = useState<OntoNode[]>([]);
  const [links, setLinks] = useState<OntoLink[]>([]);
  const [processed, setProcessed] = useState<Set<string>>(new Set());
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [log, setLog] = useState<string[]>([]);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const [showSchema, setShowSchema] = useState(false);
  const cancelRef = useRef<{ cancelled: boolean }>({ cancelled: false });

  const selectedDoc = useMemo(
    () => STUDIO_DOCS.find((d) => d.id === selectedId) ?? STUDIO_DOCS[0],
    [selectedId],
  );

  /* Reset the whole studio to an empty ontology. */
  const reset = useCallback(() => {
    cancelRef.current.cancelled = true;
    setNodes([]);
    setLinks([]);
    setProcessed(new Set());
    setRevealed(new Set());
    setLog([]);
    setStatus("");
    setBusy(false);
    setSelectedEntity(null);
  }, []);

  /* Cancel any running animation when the overlay closes. */
  useEffect(() => {
    if (!open) cancelRef.current.cancelled = true;
  }, [open]);

  const extractDoc = useCallback(
    async (doc: StudioDoc, signal: { cancelled: boolean }) => {
      if (signal.cancelled) return;
      setSelectedId(doc.id);
      setRevealed(new Set());
      setStatus("Reading document…");
      await sleep(650, signal);

      setStatus("Detecting entities…");
      for (const ent of doc.entities) {
        if (signal.cancelled) return;
        setNodes((prev) =>
          prev.some((n) => n.id === ent.id) ? prev : [...prev, { id: ent.id, type: ent.type }],
        );
        setRevealed((prev) => new Set(prev).add(ent.id));
        setLog((prev) => [`+ ${ent.type}  ${ent.id}`, ...prev].slice(0, 60));
        await sleep(STEP_MS, signal);
      }

      setStatus("Linking relationships…");
      for (const rel of doc.relationships) {
        if (signal.cancelled) return;
        setLinks((prev) =>
          prev.some((l) => l.source === rel.source && l.target === rel.target && l.type === rel.type)
            ? prev
            : [...prev, { ...rel }],
        );
        setLog((prev) => [`↳ ${rel.source} —${rel.type}→ ${rel.target}`, ...prev].slice(0, 60));
        await sleep(STEP_MS, signal);
      }

      if (signal.cancelled) return;
      setProcessed((prev) => new Set(prev).add(doc.id));
      setStatus("Merged into ontology ✓");
    },
    [],
  );

  const handleExtract = useCallback(async () => {
    if (busy) return;
    cancelRef.current = { cancelled: false };
    setBusy(true);
    await extractDoc(selectedDoc, cancelRef.current);
    setBusy(false);
  }, [busy, extractDoc, selectedDoc]);

  const handleExtractAll = useCallback(async () => {
    if (busy) return;
    cancelRef.current = { cancelled: false };
    const signal = cancelRef.current;
    setBusy(true);
    for (const doc of STUDIO_DOCS) {
      if (signal.cancelled) break;
      if (processed.has(doc.id)) continue;
      await extractDoc(doc, signal);
      await sleep(500, signal);
    }
    setBusy(false);
  }, [busy, extractDoc, processed]);

  if (!open) return null;

  const typeCount = new Set(nodes.map((n) => n.type)).size;
  const allDone = processed.size === STUDIO_DOCS.length;
  const isDocProcessed = processed.has(selectedDoc.id);
  const revealedForDoc = isDocProcessed
    ? new Set(selectedDoc.entities.map((e) => e.id))
    : revealed;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#0b1220] text-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <span className="text-xl">🧩</span>
          <div>
            <div className="text-sm font-semibold text-white">
              Ontology Studio — From Documents to Knowledge Graph
            </div>
            <div className="text-[11px] text-slate-400">
              How raw operational documents become the graph the agents reason over.
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExtractAll}
            disabled={busy}
            className="flex items-center gap-1.5 rounded-lg bg-sky-500/90 hover:bg-sky-400 disabled:opacity-40
                       px-3 py-1.5 text-xs font-semibold text-white transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5" /> Extract All
          </button>
          <button
            onClick={reset}
            disabled={busy}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-slate-300
                       hover:bg-white/5 disabled:opacity-40 transition-colors"
          >
            Reset
          </button>
          <button
            onClick={close}
            aria-label="Close Ontology Studio"
            className="rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Body: 3 panels */}
      <div className="flex-1 min-h-0 grid grid-cols-[240px_1fr_1fr]">
        {/* Left: document shelf */}
        <div className="min-h-0 overflow-y-auto border-r border-white/10 p-3 space-y-2">
          <div className="flex items-center gap-1.5 px-1 pb-1">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-400/20 text-[9px] font-bold text-sky-300">
              1
            </span>
            <span className="text-[10px] uppercase tracking-wide text-slate-500">Source documents</span>
          </div>
          {STUDIO_DOCS.map((doc) => {
            const isSel = doc.id === selectedId;
            const done = processed.has(doc.id);
            return (
              <button
                key={doc.id}
                onClick={() => !busy && setSelectedId(doc.id)}
                className={`w-full text-left rounded-lg border p-2.5 transition-colors ${
                  isSel
                    ? "border-sky-400/60 bg-sky-400/10"
                    : "border-white/10 bg-white/[0.03] hover:bg-white/[0.06]"
                }`}
              >
                <div className="flex items-start gap-2">
                  <span className="text-lg leading-none">{doc.icon}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-semibold text-slate-100 leading-tight">
                      {doc.title}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <span className="rounded bg-white/10 px-1 py-0.5 text-[9px] uppercase tracking-wide text-slate-300">
                        {doc.docType}
                      </span>
                      {done && (
                        <span className="flex items-center gap-0.5 text-[9px] text-emerald-400">
                          <Check className="h-2.5 w-2.5" /> extracted
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Centre: document viewer */}
        <div className="min-h-0 min-w-0 flex flex-col border-r border-white/10">
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-white/10">
            <div className="flex items-center gap-2 min-w-0">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-400/20 text-[9px] font-bold text-sky-300">
                2
              </span>
              <FileText className="h-4 w-4 text-slate-400 shrink-0" />
              <span className="text-xs font-medium text-slate-200 truncate">{selectedDoc.title}</span>
            </div>
            <button
              onClick={handleExtract}
              disabled={busy}
              className="shrink-0 flex items-center gap-1.5 rounded-lg bg-emerald-500/90 hover:bg-emerald-400
                         disabled:opacity-40 px-3 py-1.5 text-xs font-semibold text-white transition-colors"
            >
              <Sparkles className="h-3.5 w-3.5" />
              {isDocProcessed ? "Re-extract" : "Extract Entities & Relationships"}
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
            <div className="mx-auto max-w-[640px] rounded-lg bg-white/[0.03] border border-white/10 p-5 space-y-4">
              {selectedDoc.sections.map((sec, i) => (
                <div key={i}>
                  <div className="text-[11px] font-bold uppercase tracking-wide text-sky-300/80 mb-1">
                    {sec.heading}
                  </div>
                  <p className="text-[13px] leading-relaxed text-slate-300">
                    <Highlighted text={sec.body} entities={selectedDoc.entities} revealed={revealedForDoc} />
                  </p>
                </div>
              ))}
            </div>
          </div>
          {status && (
            <div className="px-4 py-2 border-t border-white/10 text-[11px] text-sky-300 flex items-center gap-2">
              {busy && <span className="h-2 w-2 rounded-full bg-sky-400 animate-pulse" />}
              {status}
            </div>
          )}
        </div>

        {/* Right: ontology graph */}
        <div className="min-h-0 min-w-0 flex flex-col">
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-white/10">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-sky-400/20 text-[9px] font-bold text-sky-300">
                3
              </span>
              Knowledge graph (ontology)
            </span>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="text-slate-400">
                Entities <span className="font-semibold text-white">{nodes.length}</span>
              </span>
              <span className="text-slate-400">
                Relationships <span className="font-semibold text-white">{links.length}</span>
              </span>
              <span className="text-slate-400">
                Types <span className="font-semibold text-white">{typeCount}</span>
              </span>
              <button
                onClick={() => setShowSchema((v) => !v)}
                className={`rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  showSchema
                    ? "border-sky-400/60 bg-sky-400/15 text-sky-200"
                    : "border-white/15 text-slate-300 hover:bg-white/5"
                }`}
              >
                Schema
              </button>
            </div>
          </div>
          <div className="relative flex-1 min-h-0">
            {nodes.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-center px-6">
                <div className="text-slate-500 text-xs max-w-[280px]">
                  The ontology is empty. Select a document and click{" "}
                  <span className="text-emerald-300 font-medium">Extract</span> to watch entities and
                  relationships assemble into the knowledge graph. Click any node to inspect it.
                </div>
              </div>
            ) : (
              <OntologyCanvas nodes={nodes} links={links} onNodeClick={setSelectedEntity} />
            )}

            {allDone && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 rounded-full bg-emerald-500/15 border border-emerald-400/40 px-3 py-1 text-[11px] text-emerald-200 backdrop-blur-sm whitespace-nowrap">
                {STUDIO_DOCS.length} documents → {nodes.length} entities · {links.length} relationships · {typeCount} types
              </div>
            )}

            {showSchema && <SchemaPanel nodes={nodes} links={links} onClose={() => setShowSchema(false)} />}
            {selectedEntity && (
              <EntityDetail
                id={selectedEntity}
                nodes={nodes}
                links={links}
                onClose={() => setSelectedEntity(null)}
              />
            )}
            {/* Extraction log */}
            {log.length > 0 && (
              <div className="absolute bottom-2 left-2 right-2 max-h-28 overflow-hidden rounded-md bg-black/50 border border-white/10 p-2 font-mono text-[10px] leading-tight text-slate-300 backdrop-blur-sm">
                {log.slice(0, 6).map((line, i) => (
                  <div key={i} className={i === 0 ? "text-sky-300" : "opacity-70"}>
                    {line}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
