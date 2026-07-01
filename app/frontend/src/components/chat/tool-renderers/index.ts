/**
 * Tool result renderer dispatcher.
 *
 * Maps tool names to specialized React renderers. Each tool type gets
 * a purpose-built display component optimized for its result shape:
 *
 *   - Graph queries (tabular data)    → TabularResult
 *   - Telemetry queries (tabular)     → TabularResult
 *   - Search tools (document cards)   → SearchResultCards
 *   - Dispatch (action summary)       → DispatchSummary
 *   - Unknown tools                   → JsonFallback
 *
 * To add a renderer for a new tool:
 *   1. Create a component in this directory
 *   2. Add a mapping in TOOL_RENDERERS below
 *   3. Export from here if needed externally
 */

import type { ComponentType } from "react";
import { TabularResult } from "./TabularResult";
import { SearchResultCards } from "./SearchResultCards";
import { DispatchSummary } from "./DispatchSummary";
import { ActionResult } from "./ActionResult";
import { BlastRadiusResult } from "./BlastRadiusResult";
import { EmailSummary } from "./EmailSummary";
import { DelegationResult } from "./DelegationResult";
import { IncidentReportArgs } from "./IncidentReportArgs";
import { QueryArgs } from "./QueryArgs";
import { DelegationArgs } from "./DelegationArgs";
import { JsonFallback } from "./JsonFallback";
import { OptionsCard } from "./OptionsCard";
import { WorkIqResult } from "./WorkIqResult";

export { ArgumentsGrid } from "./ArgumentsGrid";

/** Props shared by all result renderers. */
export interface ToolResultProps {
  result: string;
}

/**
 * Registry mapping tool names to their result renderer component.
 * The key is the tool function name as it appears in the SSE stream.
 */
const TOOL_RENDERERS: Record<string, ComponentType<ToolResultProps>> = {
  /* Graph tools — all return {columns, data} tabular shape */
  query_graph: TabularResult,
  query_graph_local: TabularResult,
  query_cosmos_graph: TabularResult,

  /* Telemetry — returns {columns, rows} tabular shape */
  query_telemetry: TabularResult,
  query_alerts: TabularResult,

  /* Search tools — return {results, count} document cards */
  search_runbooks: SearchResultCards,
  search_tickets: SearchResultCards,
  search_equipment: SearchResultCards,
  search_infra_specs: SearchResultCards,

  /* Dispatch — returns structured action summary */
  dispatch_field_engineer: DispatchSummary,

  /* Action tools — mutate/create something, return a small status envelope */
  reroute_traffic: ActionResult,
  set_link_status: ActionResult,
  create_incident_ticket: ActionResult,
  update_advisory: ActionResult,

  /* Blast radius — executive impact / financial-exposure card */
  estimate_blast_radius: BlastRadiusResult,

  /* Call engineer — result handled by CallEngineerRenderer inline in ToolCallDisplay.
     Registered here as JsonFallback so expanded view still works if someone expands it. */
  call_engineer: JsonFallback,

  /* Email — returns send confirmation */
  send_incident_report: EmailSummary,

  /* Delegation — specialist agent response with markdown body */
  delegate_to_agent: DelegationResult,

  /* Options — structured decision choices with clickable buttons */
  present_options: OptionsCard,

  /* Work IQ (Microsoft 365) — natural-language context card */
  ask_work_iq: WorkIqResult,
};

/**
 * Get the appropriate renderer component for a tool name.
 * Returns JsonFallback if no specialized renderer is registered.
 */
export function getToolResultRenderer(
  toolName: string
): ComponentType<ToolResultProps> {
  return TOOL_RENDERERS[toolName] ?? JsonFallback;
}

/** Props for custom arguments renderers. */
export interface ToolArgsProps {
  args: Record<string, unknown>;
}

/**
 * Registry mapping tool names to custom arguments renderers.
 * Tools not listed here use the default ArgumentsGrid.
 */
const TOOL_ARGS_RENDERERS: Record<string, ComponentType<ToolArgsProps>> = {
  send_incident_report: IncidentReportArgs,
  query_graph: QueryArgs,
  query_graph_local: QueryArgs,
  query_telemetry: QueryArgs,
  query_alerts: QueryArgs,
  delegate_to_agent: DelegationArgs,
};

/**
 * Get a custom arguments renderer for a tool, or null for default grid.
 */
export function getToolArgsRenderer(
  toolName: string
): ComponentType<ToolArgsProps> | null {
  return TOOL_ARGS_RENDERERS[toolName] ?? null;
}
