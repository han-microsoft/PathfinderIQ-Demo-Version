#!/usr/bin/env python3
"""demo — self-proof of the SSE streaming spine. Run: `python3 demo.py`.

Drives the spine with a fake agent (no SDK, no network) and asserts the event
contract holds across three scenarios: happy path with a split-argument tool
call, a stall, and a client abort. This is the self-proving bar (P7): if the
demo can't prove the spine, the spine isn't a reference.

Run from this directory: `python3 demo.py`  (the package dir is on sys.path).
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import run_agent_stream  # noqa: E402
from probe import check_event_sequence  # noqa: E402


# ── fake SDK objects (duck-typed; the spine reads these by attribute) ────────

@dataclass
class FakeContent:
    type: str
    call_id: str = ""
    name: str = ""
    arguments: Any = None
    result: Any = None
    input: int = 0
    output: int = 0


@dataclass
class FakeUpdate:
    text: str | None = None
    author_name: str = "agent"
    contents: list[FakeContent] = field(default_factory=list)


class HappyAgent:
    """Emits: token, token, a tool call whose JSON args arrive in TWO chunks,
    a tool result, a closing token, then a usage record."""

    async def run(self, prompt: str, stream: bool = True):
        yield FakeUpdate(text="Let me ")
        yield FakeUpdate(text="check. ")
        # tool call opens with partial JSON args (does not parse yet)
        yield FakeUpdate(contents=[FakeContent(
            type="function_call", call_id="c1", name="add", arguments='{"a": 1')])
        # remaining args arrive under empty call_id -> attach to trailing open
        yield FakeUpdate(contents=[FakeContent(
            type="function_call", call_id="", arguments=', "b": 2}')])
        yield FakeUpdate(contents=[FakeContent(
            type="function_result", call_id="c1", name="add", result="3")])
        yield FakeUpdate(text="The answer is 3.")
        yield FakeUpdate(contents=[FakeContent(type="usage", input=12, output=8)])


class StallAgent:
    """Emits one token, then hangs forever — triggers the stall timeout."""

    async def run(self, prompt: str, stream: bool = True):
        yield FakeUpdate(text="working")
        await asyncio.sleep(3600)
        yield FakeUpdate(text="never reached")


class AbortAgent:
    """Streams slowly so an abort event can fire mid-stream."""

    async def run(self, prompt: str, stream: bool = True):
        for i in range(50):
            yield FakeUpdate(text=f"chunk{i} ")
            await asyncio.sleep(0.02)


async def _collect(stream) -> list[tuple[str, str]]:
    frames = []
    async for ev in stream:
        frames.append(ev.to_wire())
    return frames


async def _scenario_happy() -> None:
    frames = await _collect(run_agent_stream(
        "add 1 + 2", HappyAgent,
        cost_estimator=lambda i, o: round((i + o) * 1e-6, 8)))
    names = [n for n, _ in frames]
    assert check_event_sequence(frames) == [], frames
    # tool call lifecycle present and ordered
    assert "tool_call_start" in names and "tool_call_end" in names
    assert names.index("tool_call_start") < names.index("tool_call_end")
    # split args reconstructed into the full dict on END
    import json
    end = next(d for n, d in frames if n == "tool_call_end")
    assert json.loads(end)["arguments"] == {"a": 1, "b": 2}, end
    # terminal contract: metadata then done, usage accumulated
    assert names[-2:] == ["metadata", "done"], names
    meta = json.loads(next(d for n, d in frames if n == "metadata"))
    assert meta["usage"]["total"] == 20, meta
    print("  happy-path: PASS")


async def _scenario_stall() -> None:
    frames = await _collect(run_agent_stream(
        "hang", StallAgent, stall_timeout_s=0.05))
    names = [n for n, _ in frames]
    assert check_event_sequence(frames) == [], frames
    assert names[-1] == "error", names          # stall -> single ERROR terminal
    assert "token" in names                      # partial output still streamed
    print("  stall: PASS")


async def _scenario_abort() -> None:
    abort = asyncio.Event()

    async def fire_abort():
        await asyncio.sleep(0.05)
        abort.set()

    task = asyncio.create_task(fire_abort())
    frames = await _collect(run_agent_stream(
        "long", AbortAgent, stall_timeout_s=5.0, abort_event=abort))
    await task
    names = [n for n, _ in frames]
    assert check_event_sequence(frames) == [], frames
    assert names[-1] == "aborted", names         # abort -> single ABORTED terminal
    print("  abort: PASS")


async def _main() -> None:
    await _scenario_happy()
    await _scenario_stall()
    await _scenario_abort()
    print("sse_stream self-proof: PASS")


if __name__ == "__main__":
    asyncio.run(_main())
