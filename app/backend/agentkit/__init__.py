"""agentkit — domain-blind agent-runtime kernel extracted from GridIQ.

A reusable kernel for building streaming, tool-calling agent applications. It
contains no consumer/domain knowledge (no station codes, no Fabric/KQL/Gremlin
specifics, no situation detector); GridIQ is its first consumer. Every
domain-specific concern is pushed out through an injection seam — the consumer
brings the LLM SDK client, the tools, the domain projection, the durable store,
and the request scope, and agentkit wires them into an agent with a FastAPI/SSE
surface.

Start at ``agentkit/README.md`` (the comprehensive entry point: hard rules,
quickstart, package map, injection seams, extend recipes, pip extras). The
canonical layout + inward-only dependency DAG live in
``genericize/TIER1_EXTRACTION_PLAN.md``; the full extraction history is in the
repo memory note ``/memories/repo/agentkit-extraction.md``.

Subpackages (each has its own README):
    - ``agentkit.contracts``      — wire/error/session types + tool envelope.
    - ``agentkit.config``         — settings base + per-request scope carrier.
    - ``agentkit.resilience``     — circuit breaker + retry + model-fallback queue.
    - ``agentkit.validation``     — input sanitisers + per-request tool ledger.
    - ``agentkit.cloud``          — Azure credential factory.
    - ``agentkit.tokens``         — tiktoken token counter.
    - ``agentkit.core``           — agent runtime (config/registry/resolver/builder/providers).
    - ``agentkit.sdk``            — the only agent-SDK binding (MAF), imported lazily.
    - ``agentkit.hosting``        — SSE transport spine + runtime channel/providers.
    - ``agentkit.persistence``    — session store (Protocol + in-memory + Cosmos base).
    - ``agentkit.observability``  — OTel tracing/metrics/logging + llmops/.
    - ``agentkit.guardrails``     — input/output AI-safety chain.
    - ``agentkit.tools``          — datasource adaptors (KQL/Gremlin/Search/GQL/HTTP).
    - ``agentkit.dev_tools``      — dev_sign + sse_contract_probe CLIs.
    - ``agentkit.app``            — the AgentApp few-lines facade (capstone).
    - ``agentkit.examples``       — the hello_agent zero-infra quickstart.
"""

__all__: list[str] = []
