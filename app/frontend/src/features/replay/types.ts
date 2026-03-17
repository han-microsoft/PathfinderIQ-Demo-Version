/**
 * Replay event types — shared shape for all pre-recorded agent data.
 *
 * Each ReplayEvent maps 1:1 to a call into chatStore.handleDelegationEvent()
 * or chatStore.startReplayStream(). The replayEngine iterates through these
 * events, waits for delayMs, then dispatches.
 */

/** A single event to replay into the chat store. */
export interface ReplayEvent {
  /** Milliseconds to wait BEFORE dispatching this event. */
  delayMs: number;
  /** The event type passed to handleDelegationEvent(). */
  eventType: string;
  /** The data payload passed to handleDelegationEvent(). */
  data: Record<string, unknown>;
}

/**
 * A step in the replay script. Each step targets a specific agent.
 * Steps are executed sequentially by the replay engine.
 */
export interface ReplayStep {
  /** Agent ID receiving the events. */
  agentId: string;
  /** Ordered events to feed to this agent's chat slice. */
  events: ReplayEvent[];
  /** Optional: switch to this agent's tab when starting this step. */
  switchTab?: boolean;
}
