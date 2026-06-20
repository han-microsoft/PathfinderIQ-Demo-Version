"""hello_agent quickstart — stand up a streaming agent in a few lines.

Run headlessly:  python3 -m agentkit.examples.hello_agent.app
Serve over HTTP: AgentApp(...).serve()   (needs the [fastapi] extra)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from agentkit.app import AgentApp
from agentkit.config import BaseAgentSettings
from agentkit.examples.hello_agent.stub_client import EchoClientFactory

_HERE = Path(__file__).parent


def build_app() -> AgentApp:
    """Build the hello_agent — the whole wiring, in a few lines."""
    return AgentApp(
        BaseAgentSettings(llm_provider="agent", llm_model="echo-1", auth_enabled=False),
        config=_HERE / "agent_config.yaml",
        agent_client=EchoClientFactory(),
        allowed_tool_prefixes=("agentkit.examples.hello_agent.",),
        default_agent_id="hello",
    )


async def _demo() -> None:
    app = build_app()
    async for event in app.chat("demo-session", "hello world"):
        print(f"{event.event.value}: {event.data}")


if __name__ == "__main__":
    asyncio.run(_demo())
