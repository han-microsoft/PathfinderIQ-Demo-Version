/**
 * DeveloperNotesOverlay — full-viewport overlay showing version release notes.
 *
 * Fetches /api/config/developer-notes on mount and renders each version
 * entry as a collapsible block with markdown-rendered major_changes.
 */

import { useState, useEffect } from "react";
import { X, ChevronDown, ChevronRight } from "lucide-react";
import { MarkdownRenderer } from "../shared/MarkdownRenderer";
import { BASE } from "@/foundation/constants";
import { authHeaders } from "@/api/client";

interface VersionEntry {
  version: number;
  date: string;
  major_changes: string[];
}

interface DevNotesData {
  name: string;
  Description: string;
  Versions: VersionEntry[];
}

interface Props {
  onClose: () => void;
}

export function DeveloperNotesOverlay({ onClose }: Props) {
  const [data, setData] = useState<DevNotesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<number>>(new Set([0]));

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${BASE}/config/developer-notes`, {
          headers: { ...await authHeaders() },
        });
        if (res.ok) {
          const json = await res.json();
          setData(json);
        }
      } catch {
        /* Fail-silent — overlay shows empty state */
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const toggle = (idx: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const versions = data?.Versions ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center glass-overlay animate-fade-in">
      <div className="relative w-[90vw] max-w-3xl max-h-[85vh] flex flex-col rounded-xl bg-neutral-bg1 border border-border shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-xl font-bold text-text-primary">{data?.name ?? "Developer Notes"}</h2>
            {data?.Description && (
              <p className="text-sm text-text-muted mt-0.5">{data.Description}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-neutral-bg3 text-text-muted hover:text-text-primary transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {loading && <p className="text-text-muted text-center py-8">Loading...</p>}

          {!loading && versions.length === 0 && (
            <p className="text-text-muted text-center py-8">No version notes available.</p>
          )}

          {versions.map((v, idx) => (
            <div key={idx} className="rounded-lg border border-border overflow-hidden">
              {/* Version header — click to expand/collapse */}
              <button
                onClick={() => toggle(idx)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-neutral-bg3 transition-colors text-left"
              >
                {expanded.has(idx) ? (
                  <ChevronDown className="h-4 w-4 text-text-muted shrink-0" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-text-muted shrink-0" />
                )}
                <span className="font-semibold text-brand">Version {v.version}</span>
                <span className="text-sm text-text-muted">{v.date}</span>
              </button>

              {/* Expanded content — changes as markdown bullets */}
              {expanded.has(idx) && (
                <div className="px-4 pb-4 border-t border-border/50">
                  <div className="mt-3 space-y-1">
                    {v.major_changes.map((change, ci) => (
                      <div key={ci} className="text-sm text-text-secondary pl-2 border-l-2 border-brand/30 py-1">
                        <MarkdownRenderer content={change} />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
