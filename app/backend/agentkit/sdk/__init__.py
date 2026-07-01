"""agentkit.sdk — concrete agent-SDK bindings (isolate-SDK-quirks doctrine).

Each module here wraps exactly one external *agent framework* SDK so that
``agentkit.core`` stays free of any hard SDK import. Today the only binding is
the Microsoft Agent Framework seam in ``maf_client``; swapping the SDK means
writing a sibling module here, not editing core.

Naming note:
    This package is the agent-runtime **SDK client** seam. It is distinct from
    ``agentkit.tools.adapters`` (the datasource *tool* adaptors: KQL / Gremlin /
    Search / Graph / HTTP). "SDK binding" ≠ "datasource adaptor"; the split in
    names is deliberate.

Imports here are intentionally lazy at the call boundary — importing this
package does not import the SDK. The base wheel boots without ``agent_framework``
installed; the MAF strategies/middleware degrade to ``None``/``[]`` when the
SDK is absent (matching the prior GridIQ behaviour).

Convenience factory:
    ``azure_openai_agent_client`` (in ``azure_client``) is the batteries-included
    one-liner that builds a ready-to-inject zero-arg Azure ``AgentClient``
    factory — the heavy SDK imports stay lazy inside the returned factory, so
    importing it here keeps the package import-light.
"""

from agentkit.sdk.azure_client import azure_openai_agent_client

__all__ = ["azure_openai_agent_client"]
