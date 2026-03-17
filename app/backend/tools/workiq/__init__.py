"""Work IQ tool package — spoofed M365 data access for demo.

Package role:
    Exports ``ask_work_iq``, a spoofed tool that mimics the Work IQ MCP
    server's single-tool interface. Instead of querying real Microsoft 365
    data, it matches the user's question against a catalog of canned
    responses curated for the telecom scenario narrative.

    In production, this would be replaced by an ``MCPStdioTool`` pointing
    at the real Work IQ MCP server (``npx -y @microsoft/workiq mcp``).
    The tool schema is intentionally identical so the agent's behaviour
    is unchanged when switching between spoof and live.

Available backends:
    spoof — Keyword-matched canned responses (default, only)

Dependents:
    Imported by: ``agents`` (AgentRegistry) via importlib from scenario.yaml
    tool spec ``tools.workiq:ask_work_iq``
"""

from tools.workiq._spoof import ask_work_iq  # noqa: F401

__all__ = ["ask_work_iq"]
