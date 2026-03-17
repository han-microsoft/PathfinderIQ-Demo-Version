/**
 * Message ID synchronization — reconciles temp local IDs with server canonical IDs.
 *
 * Module role:
 *   After a chat stream completes and the session is refreshed from the
 *   server, local messages may have temporary IDs (temp-*, assistant-*,
 *   aborted-*). This function matches them to server messages by role
 *   and position proximity, replacing the temp ID with the canonical one.
 *
 * Algorithm:
 *   For each local message with a temp prefix:
 *     1. Find a server message with the same role
 *     2. Within ±1 index position of the local message
 *     3. Whose server ID is not already used by another local message
 *     4. Replace the local ID with the server's canonical ID
 *
 * Key collaborators:
 *   - api/types.ts — Message type
 *
 * Dependents:
 *   - stores/chatStore.ts — called in onDone and onAborted after session refresh
 */

import type { Message } from "@/api/types";

/** Prefixes that identify temporary IDs created during streaming. */
const TEMP_PREFIXES = ["temp-", "assistant-", "aborted-"];

/**
 * Check whether a message ID is temporary (created during streaming).
 *
 * @param id — the message ID to check
 * @returns true if the ID starts with any of the temp prefixes
 */
function isTempId(id: string): boolean {
  return TEMP_PREFIXES.some((prefix) => id.startsWith(prefix));
}

/**
 * Sync local temporary message IDs with server canonical IDs.
 *
 * Matches local messages to server messages by role + position proximity.
 * Only replaces IDs that start with temp-/assistant-/aborted- prefixes.
 * Preserves all other message fields (content, parts, tool_calls, etc.).
 *
 * @param localMessages — the local message array (may have temp IDs)
 * @param serverMessages — the authoritative server messages (canonical IDs)
 * @returns new array with temp IDs replaced by server IDs where matched
 */
export function syncMessageIds(
  localMessages: Message[],
  serverMessages: Message[],
): Message[] {
  return localMessages.map((local, i) => {
    /* Skip messages with permanent (non-temp) IDs */
    if (!isTempId(local.id)) return local;

    /* Find the best matching server message:
       - Same role (user ↔ user, assistant ↔ assistant)
       - Position within ±1 (tolerates minor reordering)
       - Server ID not already used by another local message
         (prevents stealing an ID from a message that already has it) */
    const serverMatch = serverMessages.find(
      (s: Message, si: number) =>
        s.role === local.role &&
        Math.abs(si - i) <= 1 &&
        !localMessages.some((l, li) => li !== i && l.id === s.id),
    );

    /* Replace temp ID with server canonical ID, keep everything else */
    if (serverMatch) return { ...local, id: serverMatch.id };
    return local;
  });
}
