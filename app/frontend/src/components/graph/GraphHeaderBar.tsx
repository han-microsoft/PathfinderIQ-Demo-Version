/**
 * @module GraphHeaderBar
 *
 * Graph panel header bar — title, filtered counts, search, Aa label
 * style popover, node/edge toolbar toggles, and simulation controls.
 *
 * @dependents
 *   Rendered by {@link GraphTopologyViewer} at the top of the graph panel.
 */
import { useState, useRef } from 'react';
import { Search } from 'lucide-react';
import { ColorEditor } from './ColorEditor';
import { useTranslation } from '@/hooks/useTranslation';

interface GraphHeaderBarProps {
  loading: boolean;
  isPaused?: boolean;
  onTogglePause?: () => void;
  onZoomToFit: () => void;
  onRefresh: () => void;
  showNodeBar: boolean;
  onToggleNodeBar: () => void;
  showEdgeBar: boolean;
  onToggleEdgeBar: () => void;
  onSearch?: (query: string) => void;
  /** 'graph' | 'map' view toggle */
  viewMode?: 'graph' | 'map';
  onToggleViewMode?: () => void;
  /** Fill corners — zoom map to fill entire panel with no padding */
  onFillCorners?: () => void;
  /** Incident Focus — emphasise blast-radius nodes; shown only when topology has `_incident` nodes */
  hasIncident?: boolean;
  incidentFocus?: boolean;
  onToggleIncidentFocus?: () => void;
  visibleNodeCount: number;
  totalNodeCount: number;
  visibleEdgeCount: number;
  totalEdgeCount: number;
  nodeLabelFontSize?: number | null;
  onNodeLabelFontSizeChange?: (size: number | null) => void;
  nodeLabelColor?: string | null;
  onNodeLabelColorChange?: (color: string | null) => void;
  edgeLabelFontSize?: number | null;
  onEdgeLabelFontSizeChange?: (size: number | null) => void;
  edgeLabelColor?: string | null;
  onEdgeLabelColorChange?: (color: string | null) => void;
  nodeScale?: number;
  onNodeScaleChange?: (scale: number) => void;
  edgeWidth?: number;
  onEdgeWidthChange?: (width: number) => void;
  /** Color editor props */
  nodeLabels?: string[];
  edgeLabels?: string[];
  nodeColorOverride?: Record<string, string>;
  edgeColorOverride?: Record<string, string>;
  getNodeColor?: (label: string) => string;
  getEdgeColor?: (label: string) => string;
  onSetNodeColor?: (label: string, color: string) => void;
  onSetEdgeColor?: (label: string, color: string) => void;
}

export function GraphHeaderBar({
  loading,
  isPaused, onTogglePause,
  onZoomToFit, onRefresh,
  showNodeBar, onToggleNodeBar,
  showEdgeBar, onToggleEdgeBar,
  onSearch,
  visibleNodeCount, totalNodeCount,
  visibleEdgeCount, totalEdgeCount,
  nodeLabelFontSize, onNodeLabelFontSizeChange,
  nodeLabelColor, onNodeLabelColorChange,
  edgeLabelFontSize, onEdgeLabelFontSizeChange,
  edgeLabelColor, onEdgeLabelColorChange,
  nodeScale, onNodeScaleChange,
  edgeWidth, onEdgeWidthChange,
  nodeLabels, edgeLabels,
  getNodeColor, getEdgeColor, onSetNodeColor, onSetEdgeColor,
  viewMode, onToggleViewMode, onFillCorners,
  hasIncident, incidentFocus, onToggleIncidentFocus,
}: GraphHeaderBarProps) {
  const [searchText, setSearchText] = useState('');
  const [showLabelPopover, setShowLabelPopover] = useState(false);
  const [showColorEditor, setShowColorEditor] = useState(false);
  const [showMore, setShowMore] = useState(false);
  const aaBtnRef = useRef<HTMLButtonElement>(null);
  const colorBtnRef = useRef<HTMLButtonElement>(null);
  const moreBtnRef = useRef<HTMLButtonElement>(null);
  const [aaAnchor, setAaAnchor] = useState<DOMRect | null>(null);
  const [colorAnchor, setColorAnchor] = useState<DOMRect | null>(null);
  const { t } = useTranslation();

  const handleSearchSubmit = () => {
    const q = searchText.trim();
    if (q && onSearch) onSearch(q);
  };

  const toggleLabelPopover = () => {
    if (aaBtnRef.current) setAaAnchor(aaBtnRef.current.getBoundingClientRect());
    setShowLabelPopover((v) => !v);
    setShowColorEditor(false);
  };

  const toggleColorEditor = () => {
    if (colorBtnRef.current) setColorAnchor(colorBtnRef.current.getBoundingClientRect());
    setShowColorEditor((v) => !v);
    setShowLabelPopover(false);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-header-bg shrink-0 overflow-x-auto">
      <span className="text-base font-bold text-header-text whitespace-nowrap flex items-center gap-1.5"><img src="/images/graph-icon.png" alt="" className="h-5 w-5" /> {viewMode === 'map' ? t('graph.map') : t('graph.graph')}</span>

      {onToggleViewMode && (
        <button
          onClick={onToggleViewMode}
          className={`text-xs px-2 py-1 rounded border transition-colors inline-flex items-center gap-1 ${
            viewMode === 'map'
              ? 'border-brand/40 text-brand bg-brand/10 hover:bg-brand/15'
              : 'border-border text-text-muted hover:bg-neutral-bg3'
          }`}
          title={viewMode === 'map' ? t('graph.switchToGraph') : t('graph.switchToMap')}
        >
          {viewMode === 'map' ? t('graph.switchGraph') : t('graph.switchMap')}
        </button>
      )}

      {hasIncident && onToggleIncidentFocus && (
        <button
          onClick={onToggleIncidentFocus}
          className={`text-xs px-2 py-1 rounded border transition-colors inline-flex items-center gap-1 ${
            incidentFocus
              ? 'border-amber-500/50 text-amber-600 bg-amber-500/15 hover:bg-amber-500/20'
              : 'border-border text-text-muted hover:bg-neutral-bg3'
          }`}
          title="Highlight the incident blast radius on the graph"
        >
          ◎ Incident Focus
        </button>
      )}

      {onFillCorners && viewMode === 'map' && (
        <button
          onClick={onFillCorners}
          className="text-xs px-2 py-1 rounded border border-border text-text-muted hover:bg-neutral-bg3 transition-colors inline-flex items-center gap-1"
          title={t('graph.zoomFill')}
        >
          {t('graph.fillCorners')}
        </button>
      )}

      <span className="text-xs text-text-muted whitespace-nowrap ml-1">
        {visibleNodeCount}/{totalNodeCount} {t('graph.nodes')} | {visibleEdgeCount}/{totalEdgeCount} {t('graph.edges')}
      </span>

      {onSearch && (
        <div className="flex items-center gap-1 ml-2">
          <input
            type="text"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearchSubmit(); }}
            placeholder={t('graph.findNode')}
            className="bg-neutral-bg3 border border-border rounded px-2 py-0.5 text-xs text-text-primary placeholder-text-muted outline-none focus:border-brand/50 transition-colors"
            style={{ width: '140px' }}
          />
          <button
            onClick={handleSearchSubmit}
            className="text-text-muted hover:text-text-primary transition-colors p-0.5"
            title={t('graph.search')}
          >
            <Search className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <div className="flex-1" />

      {/* Overflow menu — power-user / styling controls tucked away to keep the
          bar clean for the demo. */}
      <button
        ref={moreBtnRef}
        onClick={() => setShowMore((v) => !v)}
        className={`text-sm px-2 py-1 rounded border transition-colors ${
          showMore
            ? 'border-brand/30 text-brand bg-brand/5'
            : 'border-border text-text-muted hover:bg-neutral-bg3'
        }`}
        title="More controls"
        aria-label="More controls"
      >⋯</button>

      <div
        className={`items-center gap-1.5 ${showMore ? 'flex' : 'hidden'}`}
      >
      {/* Aa — consolidated label style */}
      {onNodeLabelFontSizeChange && (
        <button
          ref={aaBtnRef}
          onClick={toggleLabelPopover}
          className={`text-sm px-2 py-1 rounded border transition-colors ${
            showLabelPopover
              ? 'border-brand/30 text-brand bg-brand/5'
              : 'border-border text-text-muted hover:bg-neutral-bg3'
          }`}
          title={t('graph.labelStyle')}
        >Aa</button>
      )}

      {showLabelPopover && aaAnchor && (
        <div
          className="fixed z-50 bg-neutral-bg3 border border-border rounded-lg p-3 shadow-xl space-y-3"
          style={{ top: aaAnchor.bottom + 4, left: aaAnchor.left - 60 }}
        >
          {onNodeScaleChange && (
            <div className="space-y-1">
              <div className="text-[10px] text-text-muted uppercase tracking-wider font-medium">{t('graph.nodeSize')}</div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-secondary w-10">{t('graph.scale')}</span>
                <input type="range" min={0.3} max={3} step={0.1}
                  value={nodeScale ?? 1}
                  onChange={(e) => onNodeScaleChange(parseFloat(e.target.value))}
                  className="w-24 accent-brand" />
                <span className="text-[10px] text-text-muted w-6">{(nodeScale ?? 1).toFixed(1)}×</span>
              </div>
            </div>
          )}
          <div className="border-t border-border" />
          {onNodeLabelFontSizeChange && onNodeLabelColorChange && (
            <div className="space-y-1">
              <div className="text-[10px] text-text-muted uppercase tracking-wider font-medium">{t('graph.nodeLabels')}</div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-secondary w-10">{t('graph.size')}</span>
                <input type="range" min={0} max={30} step={0.5}
                  value={nodeLabelFontSize ?? 10}
                  onChange={(e) => { const v = parseFloat(e.target.value); onNodeLabelFontSizeChange(v === 10 ? null : v); }}
                  className="w-24 accent-brand" />
                <span className="text-[10px] text-text-muted w-6">{nodeLabelFontSize ?? 'auto'}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-secondary w-10">{t('graph.color')}</span>
                <button className="h-4 w-4 rounded-full border border-border cursor-pointer hover:scale-125 transition-transform"
                  style={{ backgroundColor: nodeLabelColor ?? '#ccc' }}
                  onClick={() => onNodeLabelColorChange(nodeLabelColor === '#fff' ? null : '#fff')} title="Toggle node label color" />
                {nodeLabelColor && (
                  <button className="text-[10px] text-text-muted hover:text-text-primary" onClick={() => onNodeLabelColorChange(null)}>{t('graph.reset')}</button>
                )}
              </div>
            </div>
          )}
          <div className="border-t border-border" />
          {onEdgeLabelFontSizeChange && onEdgeLabelColorChange && (
            <div className="space-y-1">
              <div className="text-[10px] text-text-muted uppercase tracking-wider font-medium">{t('graph.edgeLabels')}</div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-secondary w-10">{t('graph.size')}</span>
                <input type="range" min={0} max={20} step={0.5}
                  value={edgeLabelFontSize ?? 8}
                  onChange={(e) => { const v = parseFloat(e.target.value); onEdgeLabelFontSizeChange(v === 8 ? null : v); }}
                  className="w-24 accent-brand" />
                <span className="text-[10px] text-text-muted w-6">{edgeLabelFontSize ?? 'auto'}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-text-secondary w-10">{t('graph.color')}</span>
                <button className="h-4 w-4 rounded-full border border-border cursor-pointer hover:scale-125 transition-transform"
                  style={{ backgroundColor: edgeLabelColor ?? '#888' }}
                  onClick={() => onEdgeLabelColorChange(edgeLabelColor === '#fff' ? null : '#fff')} title="Toggle edge label color" />
                {edgeLabelColor && (
                  <button className="text-[10px] text-text-muted hover:text-text-primary" onClick={() => onEdgeLabelColorChange(null)}>{t('graph.reset')}</button>
                )}
              </div>
            </div>
          )}
          {onEdgeWidthChange && (
            <>
              <div className="border-t border-border" />
              <div className="space-y-1">
                <div className="text-[10px] text-text-muted uppercase tracking-wider font-medium">{t('graph.edgeWidth')}</div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-text-secondary w-10">{t('graph.width')}</span>
                  <input type="range" min={0.5} max={6} step={0.5}
                    value={edgeWidth ?? 1.5}
                    onChange={(e) => onEdgeWidthChange(parseFloat(e.target.value))}
                    className="w-24 accent-brand" />
                  <span className="text-[10px] text-text-muted w-6">{(edgeWidth ?? 1.5).toFixed(1)}</span>
                </div>
              </div>
            </>
          )}
          <button className="text-[10px] text-text-muted hover:text-text-primary" onClick={() => setShowLabelPopover(false)}>{t('common.close')}</button>
        </div>
      )}

      {/* 🎨 Color editor — node/edge type colors */}
      {onSetNodeColor && (
        <button
          ref={colorBtnRef}
          onClick={toggleColorEditor}
          className={`text-sm px-2 py-1 rounded border transition-colors ${
            showColorEditor
              ? 'border-brand/30 text-brand bg-brand/5'
              : 'border-border text-text-muted hover:bg-neutral-bg3'
          }`}
          title={t('graph.editColors')}
        >🎨</button>
      )}

      {showColorEditor && colorAnchor && nodeLabels && edgeLabels && getNodeColor && getEdgeColor && onSetNodeColor && onSetEdgeColor && (
        <div style={{ position: 'fixed', top: colorAnchor.bottom + 4, left: Math.max(4, colorAnchor.left - 180), zIndex: 50 }}>
          <ColorEditor
            nodeLabels={nodeLabels}
            edgeLabels={edgeLabels}
            getNodeColor={getNodeColor}
            getEdgeColor={getEdgeColor}
            onSetNodeColor={onSetNodeColor}
            onSetEdgeColor={onSetEdgeColor}
            onClose={() => setShowColorEditor(false)}
            excludeRef={colorBtnRef}
          />
        </div>
      )}

      <button
        onClick={onToggleNodeBar}
        className={`text-xs px-2 py-1 rounded border transition-colors inline-flex items-center gap-1 ${
          showNodeBar
            ? 'border-brand/30 text-brand bg-brand/5 hover:bg-brand/10'
            : 'border-border text-text-muted hover:bg-neutral-bg3'
        }`}
        title={showNodeBar ? 'Hide node filter bar' : 'Show node filter bar'}
      >
        <span className="text-[10px]">●</span> {t('graph.nodes')}
      </button>
      <button
        onClick={onToggleEdgeBar}
        className={`text-xs px-2 py-1 rounded border transition-colors inline-flex items-center gap-1 ${
          showEdgeBar
            ? 'border-brand/30 text-brand bg-brand/5 hover:bg-brand/10'
            : 'border-border text-text-muted hover:bg-neutral-bg3'
        }`}
        title={showEdgeBar ? t('graph.edgeToolbar') : t('graph.edgeToolbar')}
      >
        <span className="text-[10px]">━</span> {t('graph.edges')}
      </button>
      <div className="w-px h-4 bg-border mx-0.5" />
      {onTogglePause && (
        <button
          onClick={onTogglePause}
          className={`text-xs px-1 transition-colors ${
            isPaused ? 'text-brand hover:text-brand/80' : 'text-text-muted hover:text-text-primary'
          }`}
          title={isPaused ? t('graph.resumeSim') : t('graph.pauseSim')}
        >{isPaused ? '▶' : '⏸'}</button>
      )}
      <button
        onClick={onZoomToFit}
        className="text-text-muted hover:text-text-primary text-xs px-1"
        title={t('graph.fitToView')}
      >⤢</button>
      <button
        onClick={onRefresh}
        className={`text-text-muted hover:text-text-primary text-xs px-1
                   ${loading ? 'animate-spin' : ''}`}
        title={t('graph.refresh')}
      >⟳</button>
      </div>
    </div>
  );
}
