"""hello_agent — the agentkit quickstart example (increment-9 acceptance gate).

A self-contained, domain-neutral agent that stands up a streaming agent using
ONLY agentkit — no GridIQ import, no Azure infrastructure. It proves the
project goal: *configure an agent, add a tool, in a few lines.*

The neutral "echo" domain is deliberate: it demonstrates the kernel is
domain-blind. The ``EchoClientFactory`` is a stub ``AgentClient`` so the example
(and its test) run headlessly with no network / LLM. In a real deployment you
swap that one argument for a MAF adapter (``agentkit.sdk.maf_client``,
the ``[maf]`` extra) and keep everything else identical.
"""
