/**
 * Maps agent IDs/names to their headshot image paths.
 *
 * Agent headshot files live in /public/images/agents/ with the naming
 * convention: `<lowercase-agent-name>_headshot.png`.
 *
 * This module provides a single helper that converts an agent identifier
 * (id or name, e.g. "nocOrchestrator" or "NOCOrchestrator") to the
 * corresponding image URL.
 */

const AGENTS_DIR = "/images/agents";

/**
 * Return the headshot URL for a given agent identifier.
 *
 * Strips common prefixes/suffixes, lowercases, and maps to the
 * filename convention used in /public/images/agents/.
 *
 * Returns `null` if the identifier is falsy.
 */
export function getAgentHeadshot(agentIdOrName: string | null | undefined): string | null {
  if (!agentIdOrName) return null;
  // Normalise: strip whitespace, lowercase, remove hyphens/underscores/spaces
  const key = agentIdOrName.replace(/[-_\s]/g, "").toLowerCase();
  return `${AGENTS_DIR}/${key}_headshot.png`;
}

/**
 * Return the full-body image URL for a given agent identifier.
 *
 * Uses the filename convention: `<lowercase-agent-name>_fullbody.png`.
 */
export function getAgentFullBody(agentIdOrName: string | null | undefined): string | null {
  if (!agentIdOrName) return null;
  const key = agentIdOrName.replace(/[-_\s]/g, "").toLowerCase();
  return `${AGENTS_DIR}/${key}_fullbody.png`;
}
