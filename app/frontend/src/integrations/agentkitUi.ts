/**
 * agentkit-ui adoption seam.
 *
 * PathfinderIQ consumes the reusable, domain-blind **agentkit-ui** kit
 * (vendored at `packages/agentkit-ui`, imported via the `@agentkit-ui/*`
 * path alias). This module is the single point where the app pulls primitives
 * out of the kit, so the surface area of the adoption is explicit and the
 * remaining component-level migration can proceed incrementally.
 *
 * Adopted today:
 *   - `parseSSEStream` — the kit's canonical SSE frame parser, re-exported as
 *     the app's SSE parser (replaces ad-hoc line splitting in new code paths).
 *   - `severityBucket` — the kit's domain-blind severity→bucket helper.
 */

import { parseSSEStream, type SSEFrame } from "@agentkit-ui/sse";
import { bucketFor, type Bucket } from "@agentkit-ui/foundation";

export { parseSSEStream, bucketFor };
export type { SSEFrame, Bucket };

/** Fold an alert/telemetry severity string into the kit's coarse bucket. */
export function severityBucket(raw: string): Bucket {
  return bucketFor(raw);
}

/** Marker so the bundler keeps the adoption live and tooling can assert it. */
export const AGENTKIT_UI_ADOPTED = true;
