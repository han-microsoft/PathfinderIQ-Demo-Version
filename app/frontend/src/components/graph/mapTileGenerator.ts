/**
 * @module mapTileGenerator
 *
 * Generates repeating city-block tile textures for the PathfinderIQ map
 * background. Produces small off-screen canvases that are used as
 * `CanvasPattern` fills — giving the appearance of a dense urban street
 * grid without per-frame draw cost.
 *
 * Each tile variant includes:
 *   - A cream/tan paper base
 *   - A street grid (major + minor streets, some diagonals)
 *   - Tiny building footprint rectangles between streets
 *   - Subtle texture noise for a printed-map feel
 *
 * Multiple variants are generated to reduce visible repetition.
 *
 * @dependents  Used by {@link mapRendering}.drawPaperBackground
 */

// ─── Seeded PRNG (same Mulberry32 as mapRendering) ──────────────────────────
function mulberry32(seed: number): () => number {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ─── Tile constants ─────────────────────────────────────────────────────────

const TILE_SIZE = 256;
const PAPER_BASE = '#F5F0E8';
const PAPER_BLOCK_ALT = '#EFEBE2';
const STREET_COLOR_MAJOR = 'rgba(195,187,175,0.55)';
const STREET_COLOR_MINOR = 'rgba(195,187,175,0.30)';
const STREET_COLOR_LANE  = 'rgba(185,178,166,0.18)';
const BUILDING_COLORS = [
  'rgba(215,207,195,0.35)',
  'rgba(208,200,188,0.30)',
  'rgba(220,214,204,0.25)',
  'rgba(200,193,182,0.28)',
];

/**
 * Generate a single city-block tile canvas.
 *
 * @param variantSeed  Seed for deterministic variation
 * @returns OffscreenCanvas (or regular canvas as fallback)
 */
function generateTileVariant(variantSeed: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = TILE_SIZE;
  canvas.height = TILE_SIZE;
  const ctx = canvas.getContext('2d')!;
  const rng = mulberry32(variantSeed);

  // ─ Paper base ─
  ctx.fillStyle = PAPER_BASE;
  ctx.fillRect(0, 0, TILE_SIZE, TILE_SIZE);

  // ─ Alternate block shading (2×2 quadrants) ─
  const half = TILE_SIZE / 2;
  ctx.fillStyle = PAPER_BLOCK_ALT;
  if (rng() > 0.5) {
    ctx.fillRect(0, 0, half, half);
    ctx.fillRect(half, half, half, half);
  } else {
    ctx.fillRect(half, 0, half, half);
    ctx.fillRect(0, half, half, half);
  }

  // ─ Major streets (thicker, fewer) ─
  ctx.strokeStyle = STREET_COLOR_MAJOR;
  ctx.lineCap = 'butt';

  // Horizontal major streets (2–3)
  const hMajorCount = 2 + (rng() > 0.5 ? 1 : 0);
  const hMajorSpacing = TILE_SIZE / (hMajorCount + 1);
  ctx.lineWidth = 2.0;
  for (let i = 1; i <= hMajorCount; i++) {
    const y = Math.round(hMajorSpacing * i + (rng() - 0.5) * 8);
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(TILE_SIZE, y);
    ctx.stroke();
  }

  // Vertical major streets (2–3)
  const vMajorCount = 2 + (rng() > 0.5 ? 1 : 0);
  const vMajorSpacing = TILE_SIZE / (vMajorCount + 1);
  for (let i = 1; i <= vMajorCount; i++) {
    const x = Math.round(vMajorSpacing * i + (rng() - 0.5) * 8);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, TILE_SIZE);
    ctx.stroke();
  }

  // ─ Minor streets (thinner, denser) ─
  ctx.strokeStyle = STREET_COLOR_MINOR;
  ctx.lineWidth = 1.0;

  const minorSpacing = 18 + rng() * 10; // 18–28 px apart
  // Horizontal minor
  for (let y = minorSpacing; y < TILE_SIZE; y += minorSpacing + rng() * 6) {
    ctx.beginPath();
    ctx.moveTo(0, Math.round(y));
    ctx.lineTo(TILE_SIZE, Math.round(y));
    ctx.stroke();
  }
  // Vertical minor
  for (let x = minorSpacing; x < TILE_SIZE; x += minorSpacing + rng() * 6) {
    ctx.beginPath();
    ctx.moveTo(Math.round(x), 0);
    ctx.lineTo(Math.round(x), TILE_SIZE);
    ctx.stroke();
  }

  // ─ Laneways / alleys (very thin, scattered) ─
  ctx.strokeStyle = STREET_COLOR_LANE;
  ctx.lineWidth = 0.5;
  const laneCount = 6 + Math.floor(rng() * 6);
  for (let i = 0; i < laneCount; i++) {
    const isH = rng() > 0.5;
    const pos = Math.round(rng() * TILE_SIZE);
    const start = Math.round(rng() * TILE_SIZE * 0.3);
    const end = Math.round(start + rng() * TILE_SIZE * 0.5 + TILE_SIZE * 0.2);
    ctx.beginPath();
    if (isH) {
      ctx.moveTo(start, pos);
      ctx.lineTo(Math.min(end, TILE_SIZE), pos);
    } else {
      ctx.moveTo(pos, start);
      ctx.lineTo(pos, Math.min(end, TILE_SIZE));
    }
    ctx.stroke();
  }

  // ─ One or two diagonal streets (adds realism) ─
  if (rng() > 0.3) {
    ctx.strokeStyle = STREET_COLOR_MINOR;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    if (rng() > 0.5) {
      ctx.moveTo(0, Math.round(rng() * TILE_SIZE));
      ctx.lineTo(TILE_SIZE, Math.round(rng() * TILE_SIZE));
    } else {
      // True diagonal
      const sx = Math.round(rng() * TILE_SIZE * 0.3);
      const sy = Math.round(rng() * TILE_SIZE * 0.3);
      ctx.moveTo(sx, sy);
      ctx.lineTo(TILE_SIZE - sx, TILE_SIZE - sy);
    }
    ctx.stroke();
  }

  // ─ Building footprints ─
  const buildingCount = 60 + Math.floor(rng() * 50);
  for (let i = 0; i < buildingCount; i++) {
    const bx = Math.round(rng() * (TILE_SIZE - 8));
    const by = Math.round(rng() * (TILE_SIZE - 8));
    const bw = 3 + Math.floor(rng() * 6);
    const bh = 3 + Math.floor(rng() * 6);
    ctx.fillStyle = BUILDING_COLORS[Math.floor(rng() * BUILDING_COLORS.length)];
    ctx.fillRect(bx, by, bw, bh);
  }

  // ─ Subtle paper grain (noise dots) ─
  const grainCount = 200 + Math.floor(rng() * 200);
  for (let i = 0; i < grainCount; i++) {
    const gx = Math.round(rng() * TILE_SIZE);
    const gy = Math.round(rng() * TILE_SIZE);
    ctx.fillStyle = rng() > 0.5
      ? `rgba(0,0,0,${0.01 + rng() * 0.02})`
      : `rgba(255,255,255,${0.02 + rng() * 0.03})`;
    ctx.fillRect(gx, gy, 1, 1);
  }

  return canvas;
}

// ─── Tile Cache ─────────────────────────────────────────────────────────────

const NUM_VARIANTS = 4;
let _tileVariants: HTMLCanvasElement[] | null = null;
let _tilePatterns: Map<string, CanvasPattern> = new Map();

function ensureTiles(): HTMLCanvasElement[] {
  if (!_tileVariants) {
    _tileVariants = [];
    for (let i = 0; i < NUM_VARIANTS; i++) {
      _tileVariants.push(generateTileVariant(1000 + i * 7919));
    }
  }
  return _tileVariants;
}

/**
 * Get (or lazily create) a CanvasPattern for the city tile texture.
 *
 * Uses `ctx.createPattern` with 'repeat' so one `fillRect` covers
 * the entire viewport.
 */
export function getCityTilePattern(ctx: CanvasRenderingContext2D): CanvasPattern | null {
  const id = `ctx-${(ctx.canvas as HTMLCanvasElement).dataset?.patternId ?? 'default'}`;
  const cached = _tilePatterns.get(id);
  if (cached) return cached;

  const tiles = ensureTiles();
  // Use variant 0 for the repeating pattern (it's the most "average" layout)
  const pat = ctx.createPattern(tiles[0], 'repeat');
  if (pat) {
    _tilePatterns.set(id, pat);
  }
  return pat;
}

/**
 * Draw a specific tile variant at arbitrary world position.
 * Used for the 2×2 variant cycling that prevents visible repetition.
 */
export function drawTileVariant(
  ctx: CanvasRenderingContext2D,
  worldX: number,
  worldY: number,
  size: number,
  variantIndex: number,
): void {
  const tiles = ensureTiles();
  const tile = tiles[variantIndex % tiles.length];
  ctx.drawImage(tile, worldX, worldY, size, size);
}

export { TILE_SIZE };
