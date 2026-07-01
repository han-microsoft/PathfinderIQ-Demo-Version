/**
 * agentkit-ui / chat — the streaming-chat result-rendering scaffold.
 *
 * The standardized template the genericization audit (GENERICIZATION_AUDIT.md
 * U1/U2) calls the strongest single frontend asset:
 *   - ToolResultCard  : the 4-band layout (scope / signal / note / body) +
 *                       typed-error short-circuit. Locks visual coherence once.
 *   - ResultTable     : preview-row cap + prominent-column hint table primitive.
 *   - helpers         : severityColor / parseToolResult / formatCell / extractError.
 *   - ArgumentsGrid   : generic JSON argument renderer.
 *   - JsonFallback    : the JSON-by-design fallback + in-line ToolResultError banner.
 *
 * Domain renderers (SituationResult, AuditReportResult, GridSFM*, …) live in
 * the consumer app and compose these primitives. The domain renderer REGISTRY
 * (TOOL_RENDERERS / TOOL_ARGS_RENDERERS / TOOL_PROMINENT_COLUMNS) also stays in
 * the consumer — this package owns the scaffold, never the domain mapping.
 */
export { ToolResultCard } from "./ToolResultCard";
export type {
  SignalTone,
  NoteTone,
  ScopeBadge,
  SignalChip,
  ToolResultCardProps,
} from "./ToolResultCard";
export { ResultTable } from "./ResultTable";
export type { ResultTableProps } from "./ResultTable";
export { ArgumentsGrid } from "./ArgumentsGrid";
export { JsonFallback, ToolResultError } from "./JsonFallback";
export { severityColor, parseToolResult, formatCell, extractError } from "./helpers";
