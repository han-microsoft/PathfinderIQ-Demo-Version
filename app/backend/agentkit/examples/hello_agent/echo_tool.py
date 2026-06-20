"""The one tool for the hello_agent example.

A plain callable is all a tool is — the resolver imports ``module:function``
and hands the callable to the SDK client. Domain-neutral on purpose. It uses
the agentkit-owned ``@tool`` decorator (zero SDK import): the marker is stamped
but, because the echo client is not a MAF client, the binding step ignores it
and uses the raw callable — proving the decorator works SDK-free.
"""

from __future__ import annotations

from agentkit.tools import tool


@tool()
def echo(text: str) -> str:
    """Return the supplied text unchanged.

    Args:
        text: The text to echo back.

    Returns:
        The same text, prefixed so a caller can see the tool ran.
    """
    return f"echo: {text}"
