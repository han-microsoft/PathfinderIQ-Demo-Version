/**
 * agentkit-ui / sse — domain-blind SSE wire parser.
 *
 * `parseSSEStream` decodes a fetch Response body into event frames; the
 * consumer owns fetch, auth, and the `switch (frame.event)` dispatch.
 */
export { parseSSEStream } from "./parseSSEStream";
export type { SSEFrame, ParseSSEOptions } from "./parseSSEStream";
