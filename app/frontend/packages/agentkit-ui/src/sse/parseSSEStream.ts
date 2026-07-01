/**
 * agentkit-ui / sse — domain-blind Server-Sent-Events frame parser.
 *
 * The wire-level decode loop shared by every streaming consumer: read the
 * `ReadableStream<Uint8Array>` from a `fetch` Response, normalise CRLF,
 * buffer across chunk boundaries, split on the blank-line frame delimiter,
 * parse `event:` / `data:` lines, JSON-decode the data, and hand each frame
 * to the consumer.
 *
 * Domain-blind: knows the SSE *wire shape*, not any event vocabulary. The
 * consumer owns the `switch (frame.event)` dispatch + fetch + auth. This
 * replaces the 5 hand-rolled copies of the same loop across the GridIQ api
 * layer (chat ×2, audit, summary, situations).
 */

/** One decoded SSE frame. `parsed` is `JSON.parse(data)` or `{}` on empty/non-JSON. */
export interface SSEFrame {
  /** The `event:` field value (trimmed). Frames without an event are skipped. */
  event: string;
  /** The raw joined `data:` payload (may be multi-line). */
  data: string;
  /** `JSON.parse(data)` result, or `{}` when data is empty / invalid JSON. */
  parsed: Record<string, unknown>;
}

export interface ParseSSEOptions {
  /**
   * Called when a frame's `data` is non-empty but fails `JSON.parse`.
   * The frame is still delivered with `parsed = {}`. Use for logging /
   * skip policy. Default: silently treat as `{}`.
   */
  onParseError?: (data: string, event: string) => void;
}

/**
 * Consume a fetch Response body as an SSE stream.
 *
 * `onFrame` is invoked once per complete event frame. Return a truthy value
 * (`true`) from `onFrame` to stop processing early (e.g. on a terminal
 * `done` / `complete` / `error` event) — the reader is released and the
 * promise resolves. Otherwise the loop runs until the stream closes.
 *
 * The parser owns the reader lifecycle (acquires the reader, releases the
 * lock in `finally`). It never throws on stream errors except to propagate
 * an `AbortError` so the caller can distinguish cancellation; the caller
 * remains responsible for fetch-level error handling (status, auth).
 *
 * @throws the underlying read error (incl. `DOMException` `AbortError`) so
 *   the caller can branch on `err.name === "AbortError"`.
 */
export async function parseSSEStream(
  body: ReadableStream<Uint8Array>,
  onFrame: (frame: SSEFrame) => boolean | void,
  options: ParseSSEOptions = {},
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Normalise CRLF so the frame/line split is wire-agnostic.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      // Frames are delimited by a blank line. The trailing segment is a
      // possibly-incomplete frame — keep it buffered for the next chunk.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const raw of frames) {
        if (!raw.trim()) continue;

        let event: string | null = null;
        const dataLines: string[] = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event: ")) {
            event = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            dataLines.push(line.slice(6));
          }
        }

        // A frame with no event field carries no dispatchable signal.
        if (!event) continue;

        const data = dataLines.join("\n");
        let parsed: Record<string, unknown> = {};
        if (data) {
          try {
            parsed = JSON.parse(data) as Record<string, unknown>;
          } catch {
            options.onParseError?.(data, event);
          }
        }

        if (onFrame({ event, data, parsed })) {
          return;
        }
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* reader already released — ignore */
    }
  }
}
