# sse_stream — streaming agent orchestration spine

Code-complete reference for the hardest piece of agent plumbing: turning a
streaming LLM agent into a correct Server-Sent-Events frame stream. Lifted +
simplified from a production agentkit whose 5 core modules were **byte-identical
across two independent projects** — the strongest reuse signal there is.

Multi-module on purpose: this is a *hierarchical* pattern, not a snippet. Each
file is one concern; together they form the spine. Stdlib only, no SDK, no web
framework — the agent is duck-typed, transport binding stays in the consumer's
route handler.

## Run the self-proof

```sh
cd .github/reference/python/sse_stream && python3 demo.py
```

Drives a fake agent through three scenarios and asserts the event contract:
happy path (split-argument tool call), stall timeout, client abort.

## Modules

| File | Concern |
| --- | --- |
| [events.py](events.py) | The wire contract: `StreamEventType`, `StreamEvent`, guaranteed order. |
| [tool_buffer.py](tool_buffer.py) | `ToolCallBuffer` — aggregate streamed tool-call fragments into START -> DELTA* -> END. The part naive code gets wrong. |
| [mapper.py](mapper.py) | `map_update_to_events` — duck-typed SDK update -> StreamEvents. |
| [engine.py](engine.py) | `run_agent_stream` — stall timeout, abort race, terminal-frame guarantee. |
| [probe.py](probe.py) | `check_event_sequence` — the executable contract spec. |
| [demo.py](demo.py) | Fake agent + three scenarios + assertions (the self-proof). |

## The contract this enforces

```
no tools:  TOKEN* -> METADATA -> DONE
w/ tools:  TOKEN* -> (TOOL_CALL_START -> TOOL_CALL_DELTA* -> TOOL_CALL_END
                      -> TOOL_RESULT?)* -> TOKEN* -> METADATA -> DONE
failure:   ... -> ERROR      (single terminal)
abort:     ... -> ABORTED    (single terminal)
```

Exactly one terminal frame; nothing follows it; METADATA precedes DONE; every
TOOL_CALL_END has a prior START; open calls are flushed before the terminal.

## Hard problems solved (what a naive `async for` misses)

- **Tool-call fragment aggregation** — args arrive across chunks, under the
  opener's `call_id` or an empty one; parallel calls interleave. The buffer
  reconstructs each call's JSON and closes it eagerly when it parses.
- **Stall detection** — a hung model must not hang the request. Every `__anext__`
  is raced against a timeout; a stall raises cleanly and the stream ends in ERROR.
- **Abort** — a client cancel races the update wait; single-flight claim ends the
  stream in ABORTED without a partial/duplicate terminal.
- **Terminal guarantee** — the stream always ends in exactly one of DONE / ERROR
  / ABORTED, with open tool calls flushed first.

## Injection seams (what the consumer supplies)

| Seam | Purpose |
| --- | --- |
| `agent_factory()` | build/load the agent instance |
| `run_fn(agent, prompt)` | how to invoke it (default: `agent.run(prompt, stream=True)`) |
| `is_update(u)` | filter SDK metadata-only updates |
| `cost_estimator(in, out)` | USD estimate for the METADATA frame (optional) |
| `abort_event` | `asyncio.Event` — set to cancel mid-stream |

## Simplifications vs the production original

Kept faithful: the event contract, tool aggregation, stall, abort, terminal
frames. Omitted for legibility (the real spine adds them): retry + model
fallback, stalled-run revival, a reflection loop, a hidden completion-check pass,
and the optional FastAPI keepalive/disconnect transport layer. The wire contract
is identical; this reference teaches the spine, not the full production surface.

`StreamEvent` is a stdlib dataclass here; the original uses a pydantic model.
Same contract, zero-dep form to honour the seed's rule.
