#!/usr/bin/env python3
"""duck_typed_adapter — adapt foreign objects without importing the SDK.

Reference exemplar (PATTERNS.md §4). Lifted from a production agentkit's stream
event-mapping, where SDK chunk objects are read by attribute without importing
the SDK type. The core boots without the SDK installed; swapping vendors edits
one seam, not the whole codebase (P2).

What good looks like:
    - read external objects via getattr(obj, "field", default), never isinstance
      against an imported SDK class;
    - tolerate shape variation across vendors/versions (missing attrs -> default);
    - keep the hard SDK import isolated in ONE named seam module elsewhere.

Stdlib only. Run `python3 duck_typed_adapter.py` for the self-proof.
"""
from __future__ import annotations

from typing import Any


def adapt_tool_call(content: Any) -> dict:
    """Normalize ANY object exposing call_id/name/arguments into a flat dict.

    No SDK import, no isinstance. Works on a vendor SDK chunk, a dict-like shim,
    a test double — anything with the right attributes (or none).
    """
    return {
        "call_id": getattr(content, "call_id", None) or "",
        "name": getattr(content, "name", None) or "",
        "arguments": getattr(content, "arguments", None) or {},
    }


def extract_usage(content: Any) -> dict:
    """Read token usage off a foreign response object, tolerating absence."""
    raw = getattr(content, "usage_details", None)
    if raw is None:
        return {"input": 0, "output": 0}
    return {
        "input": getattr(raw, "input_token_count", 0) or 0,
        "output": getattr(raw, "output_token_count", 0) or 0,
    }


__all__ = ["adapt_tool_call", "extract_usage"]


def _selfproof() -> None:
    # 1. A "vendor SDK" object (simulated) with the expected attributes.
    class VendorChunk:
        call_id = "call_abc"
        name = "search"
        arguments = {"q": "x"}
    out = adapt_tool_call(VendorChunk())
    assert out == {"call_id": "call_abc", "name": "search", "arguments": {"q": "x"}}

    # 2. A DIFFERENT vendor's shape, missing `arguments` -> graceful default.
    class OtherVendor:
        call_id = "id2"
        name = "lookup"
    assert adapt_tool_call(OtherVendor())["arguments"] == {}

    # 3. A bare object with none of the fields -> all defaults, no crash.
    assert adapt_tool_call(object()) == {"call_id": "", "name": "", "arguments": {}}

    # 4. Usage extraction tolerates a missing usage block.
    class Resp:
        class usage_details:
            input_token_count = 12
            output_token_count = 34
    assert extract_usage(Resp()) == {"input": 12, "output": 34}
    assert extract_usage(object()) == {"input": 0, "output": 0}

    # The point: four different object shapes, zero SDK imports, zero isinstance.
    print("duck_typed_adapter self-proof: PASS")


if __name__ == "__main__":
    _selfproof()
