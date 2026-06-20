/**
 * agentkit-ui / foundation / severity — generic severity ranking + bucket fold.
 *
 * Domain-blind vocabulary engine: a worst-first ranked band set + a coarse
 * operator-facing bucket fold, with defensive unknown-band fallbacks. Pure
 * constants + functions, zero styling — a consumer layers its own Tailwind
 * class maps on top (GridIQ does this in its `src/lib/severity.ts`).
 *
 * The default band vocabulary matches the common 5-band incident scale
 * (CRITICAL · MAJOR · SERIOUS · INVESTIGATE · minor) folded to 4 operator
 * buckets (Critical · Major · Minor · Suspect). A different domain can
 * ignore these and build its own ranked set with the same helpers.
 */

/** Raw 5-band severity union. */
export type RawSeverity = "CRITICAL" | "MAJOR" | "SERIOUS" | "INVESTIGATE" | "minor";

/** Canonical worst-first ordering. Rank + iteration order both derive from this. */
export const SEVERITIES_BY_RANK: readonly RawSeverity[] = [
  "CRITICAL",
  "MAJOR",
  "SERIOUS",
  "INVESTIGATE",
  "minor",
] as const;

/** Numeric rank (lower == worse), derived from the tuple above. */
export const SEVERITY_RANK: Record<RawSeverity, number> = Object.fromEntries(
  SEVERITIES_BY_RANK.map((s, i) => [s, i]),
) as Record<RawSeverity, number>;

/**
 * Resolve a rank for an arbitrary string. Unknown bands fall back to the
 * last-rank slot (`minor`) so a comparator never throws on a stale/hand-
 * edited value.
 */
export function rankFor(raw: string): number {
  return SEVERITY_RANK[raw as RawSeverity] ?? SEVERITY_RANK.minor;
}

/** Operator-facing 4-bucket fold. */
export type Bucket = "Critical" | "Major" | "Minor" | "Suspect";
export const BUCKETS: readonly Bucket[] = ["Critical", "Major", "Minor", "Suspect"] as const;

/** Raw band → operator bucket. SERIOUS + INVESTIGATE collapse to `Minor`. */
export const BUCKET_FROM_RAW: Record<RawSeverity, Bucket> = {
  CRITICAL: "Critical",
  MAJOR: "Major",
  SERIOUS: "Minor",
  INVESTIGATE: "Minor",
  minor: "Suspect",
};

/** Resolve the operator bucket for any raw band string. Unknown → `Suspect`. */
export function bucketFor(raw: string): Bucket {
  return BUCKET_FROM_RAW[raw as RawSeverity] ?? "Suspect";
}
