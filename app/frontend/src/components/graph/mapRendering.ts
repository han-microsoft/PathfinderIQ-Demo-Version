/**
 * @module mapRendering
 *
 * Procedural map-style rendering utilities for the PathfinderIQ map view.
 *
 * **Hybrid approach (Option C):**
 *   1. Repeating city-block tile texture (via mapTileGenerator)
 *      fills the entire viewport for a dense "printed map" base.
 *   2. District regions (noise-perturbed boundaries)
 *      around node clusters provide coloured suburb areas.
 *   3. Topology roads draw thick + bold on top as main highways.
 *   4. Town markers have glow halos so they pop over the busy background.
 *   5. Decorative overlays: compass rose, banner, legend.
 *
 * All functions are pure canvas operations — no React dependencies.
 *
 * @dependents  Used by MapCanvas.
 */

import { getCityTilePattern } from './mapTileGenerator';

// ─── Seeded PRNG (Mulberry32) ────────────────────────────────────────────────
function mulberry32(seed: number): () => number {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RoadStyle {
  outerWidth: number;
  innerWidth: number;
  outerColor: string;
  innerColor: string;
  centerLine?: boolean;
}

export interface ViewportBounds {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ParkFeature {
  kind: 'park';
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;   // radians
  name: string;
}

export interface WaterFeature {
  kind: 'water';
  points: Array<{ x: number; y: number }>;
  width: number;
  name: string;
}

export interface LakeFeature {
  kind: 'lake';
  x: number;
  y: number;
  rx: number;
  ry: number;
  name: string;
}

export type MapFeatureItem = ParkFeature | WaterFeature | LakeFeature;

export interface MapFeatures {
  items: MapFeatureItem[];
  centroidX: number;
  centroidY: number;
  spread: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const MAP_COLORS = {
  paper:         '#F5F0E8',
  paperBlock:    '#EFE9DE',
  gridMajor:     'rgba(180,170,155,0.22)',
  gridMinor:     'rgba(180,170,155,0.08)',
  foldLine:      'rgba(160,150,135,0.12)',
  shadow:        'rgba(0,0,0,0.12)',
  calloutBg:     'rgba(255,255,255,0.96)',
  calloutBorder: 'rgba(80,72,64,0.45)',
  calloutText:   '#2D2A26',
  roadLabelBg:   'rgba(255,255,255,0.92)',
  roadLabelText: '#3D3A36',
  titleBg:       '#1B4D8B',
  titleText:     '#FFFFFF',
  compassNorth:  '#D32F2F',
  compassBody:   '#4A4540',
};

const PARK_FILL   = 'rgba(160,210,100,0.22)';
const PARK_BORDER = 'rgba(100,160,55,0.35)';
const PARK_TREE   = 'rgba(75,145,40,0.35)';
const WATER_FILL   = 'rgba(130,195,225,0.45)';
const WATER_STROKE = 'rgba(70,150,195,0.35)';
const LAKE_FILL    = 'rgba(130,200,230,0.38)';
const LAKE_BORDER  = 'rgba(60,140,185,0.40)';
const FEATURE_LABEL_COLOR = 'rgba(50,100,40,0.55)';
const WATER_LABEL_COLOR   = 'rgba(30,80,150,0.55)';

const PARK_NAMES = [
  'Reserve', 'Gardens', 'Park', 'Green', 'Common',
  'Oval', 'Recreation', 'Memorial Pk', 'Sports Ground',
];
const CREEK_NAMES = [
  'Creek', 'River', 'Brook', 'Run', 'Waterway', 'Canal', 'Drain',
];
const LAKE_NAMES = [
  'Lake', 'Reservoir', 'Pond', 'Lagoon', 'Basin', 'Dam',
];

export const ROAD_STYLES: Record<string, RoadStyle> = {
  highway: {
    outerWidth: 14,
    innerWidth: 10,
    outerColor: '#6B1414',
    innerColor: '#D32F2F',
    centerLine: true,
  },
  major: {
    outerWidth: 10,
    innerWidth: 7,
    outerColor: '#153070',
    innerColor: '#2E6CC5',
  },
  secondary: {
    outerWidth: 8,
    innerWidth: 5.5,
    outerColor: '#225528',
    innerColor: '#43A047',
  },
  minor: {
    outerWidth: 6,
    innerWidth: 4,
    outerColor: '#8B6800',
    innerColor: '#E8B830',
  },
  default: {
    outerWidth: 5,
    innerWidth: 3,
    outerColor: '#5A5550',
    innerColor: '#8E8880',
  },
};

const ROAD_CODE_PREFIX: Record<string, string> = {
  highway: 'M',
  major: 'A',
  secondary: 'B',
  minor: 'C',
  default: 'L',
};

// ─── Road classification ─────────────────────────────────────────────────────

export function classifyRoad(label: string): string {
  const l = label.toLowerCase();
  if (/backbone|core|primary|trunk|main|mpls/.test(l)) return 'highway';
  if (/aggregat|peer|connect|bgp|link|fib[re]/.test(l)) return 'major';
  if (/depend|service|conduit|path|govern/.test(l)) return 'secondary';
  if (/monitor|sensor|temp|duty|depot/.test(l)) return 'minor';
  return 'default';
}

export function roadCode(edgeId: string, roadType: string): string {
  const prefix = ROAD_CODE_PREFIX[roadType] ?? 'L';
  const num = (hashStr(edgeId) % 99) + 1;
  return `${prefix}${num}`;
}

// ─── Viewport bounds helper ──────────────────────────────────────────────────

export function getViewportBounds(
  ctx: CanvasRenderingContext2D,
  canvasWidth: number,
  canvasHeight: number,
): ViewportBounds {
  const t = ctx.getTransform();
  const inv = 1 / t.a;
  const x0 = -t.e * inv;
  const y0 = -t.f * inv;
  return { x0, y0, x1: x0 + canvasWidth * inv, y1: y0 + canvasHeight * inv };
}

// ─── Overlap helpers ─────────────────────────────────────────────────────────

function parksOverlap(a: ParkFeature, b: ParkFeature): boolean {
  const gap = 15;
  return Math.abs(a.x - b.x) < (a.w / 2 + b.w / 2 + gap)
      && Math.abs(a.y - b.y) < (a.h / 2 + b.h / 2 + gap);
}

function lakesOverlap(a: LakeFeature, b: LakeFeature): boolean {
  const gap = 20;
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  const minDist = Math.max(a.rx, a.ry) + Math.max(b.rx, b.ry) + gap;
  return dist < minDist;
}

// ─── Procedural map features ─────────────────────────────────────────────────

export function computeMapFeatures(
  nodes: Array<{ id: string; x?: number; y?: number; properties: Record<string, unknown> }>,
): MapFeatures {
  const empty: MapFeatures = { items: [], centroidX: 0, centroidY: 0, spread: 200 };
  if (nodes.length === 0) return empty;
  const positioned = nodes.filter((n) => n.x != null && n.y != null);
  if (positioned.length === 0) return empty;

  const cx = positioned.reduce((s, n) => s + n.x!, 0) / positioned.length;
  const cy = positioned.reduce((s, n) => s + n.y!, 0) / positioned.length;
  const spread = Math.max(
    ...positioned.map((n) => Math.hypot(n.x! - cx, n.y! - cy)),
    200,
  );

  const rng = mulberry32(42);
  const items: MapFeatureItem[] = [];

  // ─ Rectangular parks near ~18% of nodes (no overlap) ─
  for (let i = 0; i < positioned.length; i++) {
    if (rng() > 0.18) continue;           // only a few nodes
    const n = positioned[i];
    const w = 30 + rng() * 55;            // 30–85 world units wide
    const h = 22 + rng() * 40;            // 22–62 tall
    const rot = (rng() - 0.5) * 0.3;
    const candidate: ParkFeature = {
      kind: 'park',
      x: n.x! + (rng() - 0.5) * 120,     // push further from node
      y: n.y! + (rng() - 0.5) * 120,
      w, h, rotation: rot,
      name: PARK_NAMES[Math.floor(rng() * PARK_NAMES.length)],
    };
    const existingParks = items.filter((it): it is ParkFeature => it.kind === 'park');
    if (!existingParks.some(p => parksOverlap(p, candidate))) {
      items.push(candidate);
    }
  }

  // ─ Extra parks scattered widely (no overlap) ─
  for (let i = 0; i < 14; i++) {
    const angle = rng() * Math.PI * 2;
    const dist = spread * (0.3 + rng() * 0.8); // go further out
    const w = 35 + rng() * 65;
    const h = 25 + rng() * 50;
    const candidate: ParkFeature = {
      kind: 'park',
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      w, h,
      rotation: (rng() - 0.5) * 0.35,
      name: PARK_NAMES[Math.floor(rng() * PARK_NAMES.length)],
    };
    const existingParks = items.filter((it): it is ParkFeature => it.kind === 'park');
    if (!existingParks.some(p => parksOverlap(p, candidate))) {
      items.push(candidate);
    }
  }

  // ─ Rivers / creeks (thin meandering lines) ─
  const riverCount = 3 + Math.floor(rng() * 3);  // 3-5
  for (let i = 0; i < riverCount; i++) {
    const startAngle = rng() * Math.PI * 2;
    const sx = cx + Math.cos(startAngle) * spread * (0.5 + rng() * 0.5);
    const sy = cy + Math.sin(startAngle) * spread * (0.5 + rng() * 0.5);
    const pts: Array<{ x: number; y: number }> = [{ x: sx, y: sy }];
    let px = sx, py = sy;
    const heading = startAngle + Math.PI + (rng() - 0.5) * 1.2;
    let h = heading;
    const segLen = 30 + rng() * 25;
    const segCount = 10 + Math.floor(rng() * 12);
    for (let s = 0; s < segCount; s++) {
      h += (rng() - 0.5) * 0.7;           // meander more
      px += Math.cos(h) * segLen;
      py += Math.sin(h) * segLen;
      pts.push({ x: px, y: py });
    }
    items.push({
      kind: 'water',
      points: pts,
      width: 1.5 + rng() * 2,             // 1.5–3.5 world units (thin!)
      name: CREEK_NAMES[Math.floor(rng() * CREEK_NAMES.length)],
    });
  }

  // ─ Lakes (bigger, more prominent — no overlap) ─
  const lakeCount = 3 + Math.floor(rng() * 3);   // 3-5
  for (let i = 0; i < lakeCount; i++) {
    const angle = rng() * Math.PI * 2;
    const dist = spread * (0.2 + rng() * 0.65);
    const candidate: LakeFeature = {
      kind: 'lake',
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      rx: 40 + rng() * 80,
      ry: 25 + rng() * 55,
      name: LAKE_NAMES[Math.floor(rng() * LAKE_NAMES.length)],
    };
    const existingLakes = items.filter((it): it is LakeFeature => it.kind === 'lake');
    if (!existingLakes.some(l => lakesOverlap(l, candidate))) {
      items.push(candidate);
    }
  }

  return { items, centroidX: cx, centroidY: cy, spread };
}

// ─── Drawing helpers for map features ────────────────────────────────────────

function drawPark(ctx: CanvasRenderingContext2D, p: ParkFeature): void {
  ctx.save();
  ctx.translate(p.x, p.y);
  ctx.rotate(p.rotation);

  // Filled rectangle with rounded corners
  const r = 4;
  const hw = p.w / 2, hh = p.h / 2;
  ctx.beginPath();
  ctx.moveTo(-hw + r, -hh);
  ctx.lineTo(hw - r, -hh);
  ctx.arcTo(hw, -hh, hw, -hh + r, r);
  ctx.lineTo(hw, hh - r);
  ctx.arcTo(hw, hh, hw - r, hh, r);
  ctx.lineTo(-hw + r, hh);
  ctx.arcTo(-hw, hh, -hw, hh - r, r);
  ctx.lineTo(-hw, -hh + r);
  ctx.arcTo(-hw, -hh, -hw + r, -hh, r);
  ctx.closePath();

  ctx.fillStyle = PARK_FILL;
  ctx.fill();
  ctx.strokeStyle = PARK_BORDER;
  ctx.lineWidth = 1.4;
  ctx.stroke();

  // Tree dots inside
  const prng = mulberry32(hashStr(`pk${p.x.toFixed(0)}${p.y.toFixed(0)}`));
  const count = Math.floor((p.w * p.h) / 350);
  for (let i = 0; i < count; i++) {
    const tx = (prng() - 0.5) * p.w * 0.85;
    const ty = (prng() - 0.5) * p.h * 0.85;
    const tr = 2 + prng() * 2.5;
    ctx.beginPath();
    ctx.arc(tx, ty, tr, 0, Math.PI * 2);
    ctx.fillStyle = PARK_TREE;
    ctx.fill();
  }

  // Label
  ctx.rotate(-p.rotation);  // un-rotate for upright text
  ctx.font = 'italic 7px Georgia, serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = FEATURE_LABEL_COLOR;
  ctx.fillText(p.name, 0, 0);

  ctx.restore();
}

function drawRiver(ctx: CanvasRenderingContext2D, w: WaterFeature): void {
  if (w.points.length < 2) return;
  ctx.save();

  // Outer stroke (bank)
  ctx.beginPath();
  ctx.moveTo(w.points[0].x, w.points[0].y);
  for (let i = 1; i < w.points.length; i++) {
    const prev = w.points[i - 1];
    const cur = w.points[i];
    const mx = (prev.x + cur.x) / 2;
    const my = (prev.y + cur.y) / 2;
    ctx.quadraticCurveTo(prev.x, prev.y, mx, my);
  }
  const last = w.points[w.points.length - 1];
  ctx.lineTo(last.x, last.y);
  ctx.strokeStyle = WATER_STROKE;
  ctx.lineWidth = w.width + 1.5;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Inner fill (water)
  ctx.beginPath();
  ctx.moveTo(w.points[0].x, w.points[0].y);
  for (let i = 1; i < w.points.length; i++) {
    const prev = w.points[i - 1];
    const cur = w.points[i];
    const mx = (prev.x + cur.x) / 2;
    const my = (prev.y + cur.y) / 2;
    ctx.quadraticCurveTo(prev.x, prev.y, mx, my);
  }
  ctx.lineTo(last.x, last.y);
  ctx.strokeStyle = WATER_FILL;
  ctx.lineWidth = w.width;
  ctx.stroke();

  // Label at midpoint
  const mid = w.points[Math.floor(w.points.length / 2)];
  const next = w.points[Math.min(Math.floor(w.points.length / 2) + 1, w.points.length - 1)];
  const angle = Math.atan2(next.y - mid.y, next.x - mid.x);
  ctx.save();
  ctx.translate(mid.x, mid.y);
  ctx.rotate(angle);
  ctx.font = 'italic 6px Georgia, serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillStyle = WATER_LABEL_COLOR;
  ctx.fillText(w.name, 0, -w.width);
  ctx.restore();

  ctx.restore();
}

function drawLake(ctx: CanvasRenderingContext2D, lk: LakeFeature): void {
  ctx.save();

  // Noisy ellipse
  const prng = mulberry32(hashStr(`lk${lk.x.toFixed(0)}${lk.y.toFixed(0)}`));
  const steps = 32;
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * Math.PI * 2;
    const nr = 0.85 + prng() * 0.3;
    const x = lk.x + Math.cos(a) * lk.rx * nr;
    const y = lk.y + Math.sin(a) * lk.ry * nr;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = LAKE_FILL;
  ctx.fill();
  ctx.strokeStyle = LAKE_BORDER;
  ctx.lineWidth = 1.4;
  ctx.stroke();

  // Wavy interior lines
  ctx.strokeStyle = 'rgba(60,140,190,0.22)';
  ctx.lineWidth = 0.8;
  for (let i = 0; i < 4; i++) {
    const wy = lk.y - lk.ry * 0.4 + prng() * lk.ry * 0.8;
    ctx.beginPath();
    ctx.moveTo(lk.x - lk.rx * 0.5, wy);
    for (let s = 1; s <= 6; s++) {
      ctx.lineTo(
        lk.x - lk.rx * 0.5 + (lk.rx / 6) * s,
        wy + (prng() - 0.5) * 4,
      );
    }
    ctx.stroke();
  }

  // Label
  ctx.font = 'italic 6px Georgia, serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = WATER_LABEL_COLOR;
  ctx.fillText(lk.name, lk.x, lk.y);

  ctx.restore();
}

// ─── Background ──────────────────────────────────────────────────────────────

let _canvasIdCounter = 0;
function ensureCanvasId(canvas: HTMLCanvasElement): void {
  if (!canvas.dataset) return;
  if (!canvas.dataset.patternId) {
    canvas.dataset.patternId = String(++_canvasIdCounter);
  }
}

export function drawPaperBackground(
  ctx: CanvasRenderingContext2D,
  bounds: ViewportBounds,
  globalScale: number,
  features: MapFeatures,
): void {
  const { x0, y0, x1, y1 } = bounds;
  const pad = 600 / globalScale;
  const drawX0 = x0 - pad;
  const drawY0 = y0 - pad;
  const drawW = (x1 - x0) + 2 * pad;
  const drawH = (y1 - y0) + 2 * pad;

  // 1) City tile texture fill
  ensureCanvasId(ctx.canvas as HTMLCanvasElement);

  if (globalScale >= 0.3) {
    const pattern = getCityTilePattern(ctx);
    if (pattern) {
      ctx.save();
      pattern.setTransform(new DOMMatrix());
      ctx.fillStyle = pattern;
      ctx.fillRect(drawX0, drawY0, drawW, drawH);
      ctx.restore();
    } else {
      ctx.fillStyle = MAP_COLORS.paper;
      ctx.fillRect(drawX0, drawY0, drawW, drawH);
    }
  } else {
    // Too zoomed out — solid paper + faint grid
    ctx.fillStyle = MAP_COLORS.paper;
    ctx.fillRect(drawX0, drawY0, drawW, drawH);

    const majorStep = 640;
    const gx0 = Math.floor(drawX0 / majorStep) * majorStep;
    const gy0 = Math.floor(drawY0 / majorStep) * majorStep;
    ctx.strokeStyle = MAP_COLORS.gridMajor;
    ctx.lineWidth = 0.8 / globalScale;
    ctx.beginPath();
    for (let gx = gx0; gx <= x1 + pad; gx += majorStep) {
      ctx.moveTo(gx, drawY0);
      ctx.lineTo(gx, drawY0 + drawH);
    }
    for (let gy = gy0; gy <= y1 + pad; gy += majorStep) {
      ctx.moveTo(drawX0, gy);
      ctx.lineTo(drawX0 + drawW, gy);
    }
    ctx.stroke();
  }

  // 2) Map features: parks, rivers, lakes
  const safeItems = features.items ?? [];
  for (const item of safeItems) {
    if (item.kind === 'park') {
      const maxD = Math.max(item.w, item.h) * 0.8;
      if (item.x + maxD < x0 - pad || item.x - maxD > x1 + pad) continue;
      if (item.y + maxD < y0 - pad || item.y - maxD > y1 + pad) continue;
      drawPark(ctx, item);
    } else if (item.kind === 'water') {
      drawRiver(ctx, item);
    } else if (item.kind === 'lake') {
      const maxR = Math.max(item.rx, item.ry) * 1.3;
      if (item.x + maxR < x0 - pad || item.x - maxR > x1 + pad) continue;
      if (item.y + maxR < y0 - pad || item.y - maxR > y1 + pad) continue;
      drawLake(ctx, item);
    }
  }

  // 3) Realistic fold creases — grid pattern like a folded paper map
  if (features.centroidX !== 0 || features.centroidY !== 0) {
    const foldSpreadX = features.spread * 1.1;
    const foldSpreadY = features.spread * 0.85;
    const vFolds = [
      features.centroidX - foldSpreadX * 0.5,
      features.centroidX,
      features.centroidX + foldSpreadX * 0.5,
    ];
    const hFolds = [
      features.centroidY - foldSpreadY * 0.5,
      features.centroidY,
      features.centroidY + foldSpreadY * 0.5,
    ];

    for (const fx of vFolds) {
      drawFoldCrease(ctx, fx, drawY0, fx, drawY0 + drawH, globalScale);
    }
    for (const fy of hFolds) {
      drawFoldCrease(ctx, drawX0, fy, drawX0 + drawW, fy, globalScale);
    }
  }
}

// ─── Fold crease helper ──────────────────────────────────────────────────────

function drawFoldCrease(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number, x2: number, y2: number,
  _globalScale: number,
): void {
  ctx.save();

  // Shadow side (dark line)
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = 'rgba(120,110,95,0.12)';
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // Main crease line
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = 'rgba(140,130,115,0.14)';
  ctx.lineWidth = 1.0;
  ctx.setLineDash([18, 8]);
  ctx.stroke();
  ctx.setLineDash([]);

  // Highlight side (light line offset by ~1px)
  const isVertical = Math.abs(x2 - x1) < Math.abs(y2 - y1);
  const off = 1.5;
  ctx.beginPath();
  if (isVertical) {
    ctx.moveTo(x1 + off, y1);
    ctx.lineTo(x2 + off, y2);
  } else {
    ctx.moveTo(x1, y1 + off);
    ctx.lineTo(x2, y2 + off);
  }
  ctx.strokeStyle = 'rgba(255,255,245,0.18)';
  ctx.lineWidth = 1.0;
  ctx.stroke();

  ctx.restore();
}

// ─── Paper edge overlay ──────────────────────────────────────────────────────

export function drawPaperEdge(
  ctx: CanvasRenderingContext2D,
  cw: number,
  ch: number,
  dpr: number,
): void {
  ctx.save();

  const borderW = 6 * dpr;

  // Cream-white border band around the entire canvas edge
  ctx.strokeStyle = '#E8E2D6';
  ctx.lineWidth = borderW;
  ctx.strokeRect(borderW / 2, borderW / 2, cw - borderW, ch - borderW);

  // Thin inner line
  ctx.strokeStyle = 'rgba(160,148,130,0.40)';
  ctx.lineWidth = 1.2 * dpr;
  const inset = borderW + 2 * dpr;
  ctx.strokeRect(inset, inset, cw - inset * 2, ch - inset * 2);

  // Corner shadows (slight darkening in the corners for a worn look)
  const cornerR = 80 * dpr;
  const corners = [
    [0, 0],
    [cw, 0],
    [0, ch],
    [cw, ch],
  ];
  for (const [cx, cy] of corners) {
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, cornerR);
    grad.addColorStop(0, 'rgba(0,0,0,0.06)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(
      cx - cornerR, cy - cornerR,
      cornerR * 2, cornerR * 2,
    );
  }

  // Edge vignette — subtle darkening around the entire perimeter
  // Top edge
  let grad = ctx.createLinearGradient(0, 0, 0, 30 * dpr);
  grad.addColorStop(0, 'rgba(0,0,0,0.05)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, cw, 30 * dpr);

  // Bottom edge
  grad = ctx.createLinearGradient(0, ch, 0, ch - 30 * dpr);
  grad.addColorStop(0, 'rgba(0,0,0,0.05)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, ch - 30 * dpr, cw, 30 * dpr);

  // Left edge
  grad = ctx.createLinearGradient(0, 0, 30 * dpr, 0);
  grad.addColorStop(0, 'rgba(0,0,0,0.05)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 30 * dpr, ch);

  // Right edge
  grad = ctx.createLinearGradient(cw, 0, cw - 30 * dpr, 0);
  grad.addColorStop(0, 'rgba(0,0,0,0.05)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(cw - 30 * dpr, 0, 30 * dpr, ch);

  ctx.restore();
}

// ─── Road drawing ────────────────────────────────────────────────────────────

function roadControlPoint(
  x1: number, y1: number, x2: number, y2: number, seed: number,
): { cx: number; cy: number } {
  const rng = mulberry32(seed);
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const px = -dy / len;
  const py = dx / len;
  const mag = (0.05 + rng() * 0.10) * len * (rng() > 0.5 ? 1 : -1);
  return { cx: mx + px * mag, cy: my + py * mag };
}

export function drawRoad(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number, x2: number, y2: number,
  style: RoadStyle,
  globalScale: number,
  seed: number,
): void {
  const { cx, cy } = roadControlPoint(x1, y1, x2, y2, seed);
  const scale = Math.min(globalScale, 3);

  // Road glow/shadow
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.quadraticCurveTo(cx, cy, x2, y2);
  ctx.strokeStyle = 'rgba(0,0,0,0.08)';
  ctx.lineWidth = (style.outerWidth + 4) / scale;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();
  ctx.restore();

  // Outer casing
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.quadraticCurveTo(cx, cy, x2, y2);
  ctx.strokeStyle = style.outerColor;
  ctx.lineWidth = style.outerWidth / scale;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Inner fill
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.quadraticCurveTo(cx, cy, x2, y2);
  ctx.strokeStyle = style.innerColor;
  ctx.lineWidth = style.innerWidth / scale;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Center dashed line for highways
  if (style.centerLine) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.quadraticCurveTo(cx, cy, x2, y2);
    ctx.strokeStyle = 'rgba(255,255,255,0.65)';
    ctx.lineWidth = 1.2 / scale;
    ctx.setLineDash([7 / scale, 5 / scale]);
    ctx.lineCap = 'butt';
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }
}

export function drawRoadLabel(
  ctx: CanvasRenderingContext2D,
  x1: number, y1: number, x2: number, y2: number,
  label: string,
  globalScale: number,
  seed: number,
): void {
  if (globalScale < 0.25) return;

  const { cx, cy } = roadControlPoint(x1, y1, x2, y2, seed);
  const mx = 0.25 * x1 + 0.5 * cx + 0.25 * x2;
  const my = 0.25 * y1 + 0.5 * cy + 0.25 * y2;

  const fontSize = Math.max(3.5, Math.min(11, 10 / globalScale));
  ctx.save();
  ctx.font = `bold ${fontSize}px 'Segoe UI', system-ui, sans-serif`;

  const metrics = ctx.measureText(label);
  const tw = metrics.width;
  const th = fontSize;
  const padX = 3.5 / globalScale;
  const padY = 2.5 / globalScale;
  const r = 2.5 / globalScale;

  const dx = x2 - x1;
  const dy = y2 - y1;
  let angle = Math.atan2(dy, dx);
  if (angle > Math.PI / 2) angle -= Math.PI;
  if (angle < -Math.PI / 2) angle += Math.PI;

  ctx.translate(mx, my);
  ctx.rotate(angle);

  const bx = -tw / 2 - padX;
  const by = -th / 2 - padY;
  const bw = tw + padX * 2;
  const bh = th + padY * 2;
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, r);
  ctx.fillStyle = MAP_COLORS.roadLabelBg;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.15)';
  ctx.lineWidth = 0.4 / globalScale;
  ctx.stroke();

  ctx.fillStyle = MAP_COLORS.roadLabelText;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, 0, 0);
  ctx.restore();
}

// ─── Town marker ─────────────────────────────────────────────────────────────

export function drawTownMarker(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  size: number,
  color: string,
  label: string,
  globalScale: number,
): void {
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  const s = Math.min(globalScale, 4);

  // Glow halo
  const glowRadius = size * 2.5;
  const grad = ctx.createRadialGradient(x, y, size * 0.5, x, y, glowRadius / s);
  grad.addColorStop(0, 'rgba(255,255,255,0.55)');
  grad.addColorStop(0.5, 'rgba(255,255,255,0.18)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.beginPath();
  ctx.arc(x, y, glowRadius / s, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();

  // Pin shadow
  ctx.beginPath();
  ctx.ellipse(x + 1.5 / s, y + size + 3 / s, size * 0.75, size * 0.3, 0, 0, Math.PI * 2);
  ctx.fillStyle = MAP_COLORS.shadow;
  ctx.fill();

  // Pin body
  ctx.beginPath();
  ctx.arc(x, y, size, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = '#FFFFFF';
  ctx.lineWidth = 2.8 / s;
  ctx.stroke();
  ctx.strokeStyle = 'rgba(0,0,0,0.22)';
  ctx.lineWidth = 0.8 / s;
  ctx.stroke();

  // Inner highlight
  ctx.beginPath();
  ctx.arc(x - size * 0.22, y - size * 0.22, size * 0.28, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.50)';
  ctx.fill();

  // Callout label
  if (globalScale < 0.12) return;
  const fontSize = Math.max(3.5, Math.min(13, 11 / s));
  ctx.save();
  ctx.font = `600 ${fontSize}px 'Segoe UI', system-ui, sans-serif`;
  const metrics = ctx.measureText(label);
  const tw = metrics.width;
  const th = fontSize;
  const padX = 5 / s;
  const padY = 3 / s;
  const r = 3.5 / s;
  const calloutY = y - size - 7 / s - th / 2 - padY;

  const bx = x - tw / 2 - padX;
  const by = calloutY - th / 2 - padY;
  const bw = tw + padX * 2;
  const bh = th + padY * 2;

  // Shadow
  ctx.fillStyle = 'rgba(0,0,0,0.12)';
  ctx.beginPath();
  ctx.roundRect(bx + 1.2 / s, by + 1.8 / s, bw, bh, r);
  ctx.fill();

  // White box
  ctx.fillStyle = MAP_COLORS.calloutBg;
  ctx.beginPath();
  ctx.roundRect(bx, by, bw, bh, r);
  ctx.fill();
  ctx.strokeStyle = MAP_COLORS.calloutBorder;
  ctx.lineWidth = 0.6 / s;
  ctx.stroke();

  // Triangle pointer
  const triSize = 3.5 / s;
  ctx.fillStyle = MAP_COLORS.calloutBg;
  ctx.beginPath();
  ctx.moveTo(x - triSize, by + bh);
  ctx.lineTo(x, by + bh + triSize);
  ctx.lineTo(x + triSize, by + bh);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = MAP_COLORS.calloutBorder;
  ctx.lineWidth = 0.6 / s;
  ctx.beginPath();
  ctx.moveTo(x - triSize, by + bh);
  ctx.lineTo(x, by + bh + triSize);
  ctx.lineTo(x + triSize, by + bh);
  ctx.stroke();

  // Text
  ctx.fillStyle = MAP_COLORS.calloutText;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, x, calloutY);

  ctx.restore();
}

// ─── Compass Rose ────────────────────────────────────────────────────────────

export function drawCompassRose(
  ctx: CanvasRenderingContext2D,
  screenX: number, screenY: number,
  size: number,
): void {
  ctx.save();
  ctx.translate(screenX, screenY);

  const r = size;
  const inner = r * 0.25;

  ctx.beginPath();
  ctx.moveTo(0, -r); ctx.lineTo(-inner, 0); ctx.lineTo(0, inner * 0.5);
  ctx.closePath(); ctx.fillStyle = MAP_COLORS.compassNorth; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(0, -r); ctx.lineTo(inner, 0); ctx.lineTo(0, inner * 0.5);
  ctx.closePath(); ctx.fillStyle = '#E57373'; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(0, r); ctx.lineTo(-inner, 0); ctx.lineTo(0, -inner * 0.5);
  ctx.closePath(); ctx.fillStyle = MAP_COLORS.compassBody; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(0, r); ctx.lineTo(inner, 0); ctx.lineTo(0, -inner * 0.5);
  ctx.closePath(); ctx.fillStyle = '#7A7570'; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(r, 0); ctx.lineTo(0, -inner); ctx.lineTo(-inner * 0.5, 0);
  ctx.closePath(); ctx.fillStyle = '#7A7570'; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(r, 0); ctx.lineTo(0, inner); ctx.lineTo(-inner * 0.5, 0);
  ctx.closePath(); ctx.fillStyle = MAP_COLORS.compassBody; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(-r, 0); ctx.lineTo(0, -inner); ctx.lineTo(inner * 0.5, 0);
  ctx.closePath(); ctx.fillStyle = MAP_COLORS.compassBody; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(-r, 0); ctx.lineTo(0, inner); ctx.lineTo(inner * 0.5, 0);
  ctx.closePath(); ctx.fillStyle = '#7A7570'; ctx.fill();

  ctx.beginPath();
  ctx.arc(0, 0, inner * 0.6, 0, Math.PI * 2);
  ctx.fillStyle = '#FFF'; ctx.fill();
  ctx.strokeStyle = MAP_COLORS.compassBody; ctx.lineWidth = 1; ctx.stroke();

  ctx.font = `bold ${size * 0.35}px 'Segoe UI', system-ui, sans-serif`;
  ctx.fillStyle = MAP_COLORS.compassNorth;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  ctx.fillText('N', 0, -r - 3);

  ctx.restore();
}

// ─── PathfinderIQ Banner ─────────────────────────────────────────────────────

export function drawMapBanner(
  ctx: CanvasRenderingContext2D,
  screenX: number, screenY: number,
): void {
  ctx.save();
  const text = 'Pathfinder IQ';
  const fontSize = 32;
  ctx.font = `bold ${fontSize}px 'Segoe UI', system-ui, sans-serif`;
  const tw = ctx.measureText(text).width;
  const padX = 28;
  const padY = 12;
  const bw = tw + padX * 2;
  const bh = fontSize + padY * 2;
  const bx = screenX;
  const by = screenY;
  const r = 8;

  ctx.fillStyle = 'rgba(0,0,0,0.15)';
  ctx.beginPath(); ctx.roundRect(bx + 2, by + 2, bw, bh, r); ctx.fill();

  ctx.fillStyle = MAP_COLORS.titleBg;
  ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, r); ctx.fill();

  ctx.fillStyle = MAP_COLORS.titleText;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, bx + padX, by + bh / 2);

  ctx.restore();
}

// ─── Map Legend ──────────────────────────────────────────────────────────────

export function drawMapLegend(
  ctx: CanvasRenderingContext2D,
  screenX: number, screenY: number,
): void {
  ctx.save();
  const entries: Array<[string, RoadStyle]> = [
    ['Highway (Core)', ROAD_STYLES.highway],
    ['Major (Link)', ROAD_STYLES.major],
    ['Secondary (Service)', ROAD_STYLES.secondary],
    ['Minor (Sensor)', ROAD_STYLES.minor],
    ['Local', ROAD_STYLES.default],
  ];

  const fontSize = 20;
  const lineH = 36;
  const padX = 20;
  const padY = 16;
  const sampleW = 48;
  const totalH = entries.length * lineH + padY * 2 + 28;
  const totalW = 320;
  const r = 10;

  ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;

  ctx.fillStyle = 'rgba(255,255,255,0.94)';
  ctx.beginPath(); ctx.roundRect(screenX, screenY, totalW, totalH, r); ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.15)'; ctx.lineWidth = 1; ctx.stroke();

  ctx.font = `bold 22px 'Segoe UI', system-ui, sans-serif`;
  ctx.fillStyle = '#3D3A36';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('Legend', screenX + padX, screenY + padY);

  ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
  entries.forEach(([name, style], i) => {
    const ey = screenY + padY + 32 + i * lineH;

    ctx.beginPath();
    ctx.moveTo(screenX + padX, ey + 10);
    ctx.lineTo(screenX + padX + sampleW, ey + 10);
    ctx.strokeStyle = style.outerColor;
    ctx.lineWidth = style.outerWidth * 1.0;
    ctx.lineCap = 'round';
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(screenX + padX, ey + 10);
    ctx.lineTo(screenX + padX + sampleW, ey + 10);
    ctx.strokeStyle = style.innerColor;
    ctx.lineWidth = style.innerWidth * 1.0;
    ctx.lineCap = 'round';
    ctx.stroke();

    ctx.fillStyle = '#4A4540';
    ctx.textBaseline = 'middle';
    ctx.fillText(name, screenX + padX + sampleW + 16, ey + 10);
  });

  ctx.restore();
}

// ─── Parallax Clouds ─────────────────────────────────────────────────────────

const CLOUD_POSITIONS: Array<{ x: number; y: number; scale: number; opacity: number }> = (() => {
  const rng = mulberry32(7777);
  const clouds: Array<{ x: number; y: number; scale: number; opacity: number }> = [];
  for (let i = 0; i < 6; i++) {
    clouds.push({
      x: rng() * 1.4 - 0.2,
      y: rng() * 1.0 - 0.1,
      scale: 0.5 + rng() * 0.7,
      opacity: 0.045 + rng() * 0.045,   // 4.5–9% — very translucent
    });
  }
  return clouds;
})();

function drawSingleCloud(
  ctx: CanvasRenderingContext2D,
  cx: number, cy: number,
  scale: number, opacity: number,
): void {
  ctx.save();
  ctx.globalAlpha = opacity;
  ctx.fillStyle = '#FFFFFF';

  const blobs = [
    { dx: 0, dy: 0, rx: 70, ry: 28 },
    { dx: -48, dy: 6, rx: 44, ry: 22 },
    { dx: 52, dy: 4, rx: 48, ry: 22 },
    { dx: -20, dy: -13, rx: 38, ry: 20 },
    { dx: 26, dy: -11, rx: 40, ry: 21 },
    { dx: 8, dy: 10, rx: 52, ry: 18 },
  ];

  for (const b of blobs) {
    ctx.beginPath();
    ctx.ellipse(
      cx + b.dx * scale, cy + b.dy * scale,
      b.rx * scale, b.ry * scale,
      0, 0, Math.PI * 2,
    );
    ctx.fill();
  }

  ctx.restore();
}

export function drawClouds(
  ctx: CanvasRenderingContext2D,
  canvasWidth: number,
  canvasHeight: number,
  mapTranslateX: number,
  mapTranslateY: number,
  dpr: number,
): void {
  const parallaxRatio = 0.12;  // clouds shift at 12% of map pan

  for (const cloud of CLOUD_POSITIONS) {
    const baseX = cloud.x * canvasWidth;
    const baseY = cloud.y * canvasHeight;
    const px = baseX + mapTranslateX * parallaxRatio;
    const py = baseY + mapTranslateY * parallaxRatio;
    drawSingleCloud(ctx, px, py, cloud.scale * dpr, cloud.opacity);
  }
}
