"""agentkit.hosting.runtime.providers — reference LLM providers.

Two lightweight reference implementations of the streaming-LLM contract
(``async stream_completion(messages, *, abort_event) -> AsyncIterator[StreamEvent]``)
with zero external dependencies:

    - ``EchoLLMService`` — parrots the user's last message token-by-token.
    - ``MockLLMService`` — canned rich response exercising markdown, code
      blocks, tables, and tool-call frames.

Used by quickstarts, frontend dev, demos, latency testing, and SSE
pipeline tests. The concrete provider-selection factory (reading a
settings flag) lives in the consumer's composition root and imports
these classes.
"""

from agentkit.hosting.runtime.providers.echo import EchoLLMService
from agentkit.hosting.runtime.providers.mock import MockLLMService

__all__ = ["EchoLLMService", "MockLLMService"]
