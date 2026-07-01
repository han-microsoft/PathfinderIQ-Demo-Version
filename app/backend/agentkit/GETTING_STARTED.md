# Getting started with agentkit

Zero → a real streaming, tool-calling agent, one rung at a time. Each rung is
copy-paste runnable and changes only what the heading says. Every signature
below is the real current one (see the cited source file).

Prerequisites: Python ≥ 3.11. agentkit is domain-blind — the examples here use a
neutral echo/word-count domain only.

---

## 1. Install

The base wheel is lean — only `pydantic`, `pydantic-settings`, `pyyaml`,
`httpx` (the four libs the kernel imports unconditionally). Every heavy SDK is
gated behind a pip extra.

```bash
# lean base — enough for the echo quickstart (rung 2), no Azure, no SDK
pip install agentkit

# add a real model client + HTTP/SSE serving
pip install "agentkit[maf,fastapi]"
```

- `[maf]` → `agent-framework` (the Microsoft Agent Framework client, rung 3).
- `[fastapi]` → `fastapi` + `uvicorn[standard]` + `sse-starlette` (serving, rung 7).
- `[azure]` → `azure-identity` for the default credential (rung 3).

Extras are declared in [`pyproject.toml`](pyproject.toml) `[project.optional-dependencies]`.

---

## 2. An echo agent in a few lines

No Azure, no SDK, no infrastructure — a stub client + the in-memory store. This
is the canonical capstone at [`examples/hello_agent/app.py`](examples/hello_agent/app.py).

```python
# app.py
from pathlib import Path

from agentkit.app import AgentApp
from agentkit.config import BaseAgentSettings
from agentkit.examples.hello_agent.stub_client import EchoClientFactory

_HERE = Path(__file__).parent


def build_app() -> AgentApp:
    return AgentApp(
        BaseAgentSettings(llm_provider="agent", llm_model="echo-1", auth_enabled=False),
        config=_HERE / "agent_config.yaml",
        agent_client=EchoClientFactory(),                 # the only SDK seam
        allowed_tool_prefixes=("agentkit.examples.hello_agent.",),
        default_agent_id="hello",
    )
```

The `AgentApp(...)` signature ([`app/agent_app.py`](app/agent_app.py)):

```python
AgentApp(
    settings: BaseAgentSettings,
    config: str | Path,
    tools: list | None = None,
    *,
    agent_client,                                   # () -> client factory (or instance)
    store=None,                                     # default: in-memory
    request_scope_builder=None,
    allowed_tool_prefixes: tuple[str, ...] = (),    # () = fail-closed: forbids all
    default_agent_id: str = "",
    domain_events: tuple[str, ...] = (),
    responses_client=None,
    time_context_note: str = "",
)
```

The matching `agent_config.yaml` (the entire declarative surface):

```yaml
agents:
  default: hello
  hello:
    name: HelloAgent
    description: "A neutral echo agent that proves the wiring end to end."
    instructions:
      - hello.md
    tools:
      - agentkit.examples.hello_agent.echo_tool:echo
```

Run it headless — prints `token` / `done` SSE events:

```bash
python3 -m agentkit.examples.hello_agent.app
```

`AgentApp.chat()` yields `StreamEvent`s; read `event.event.value` + `event.data`:

```python
async for event in app.chat("demo-session", "hello world"):
    print(f"{event.event.value}: {event.data}")
```

---

## 3. Swap to a real Azure model

The echo → real swap **changes nothing else** — only the injected
`agent_client`. Use the Inc A factory
`azure_openai_agent_client` ([`sdk/azure_client.py`](sdk/azure_client.py)):

```python
azure_openai_agent_client(
    *,
    endpoint: str,            # the Azure AI Foundry PROJECT endpoint
    model_deployment: str,    # e.g. "gpt-4o"
    credential=None,          # None → one cached DefaultAzureCredential()
    api_version: str | None = None,
) -> Callable[[], client]     # a zero-arg factory (the registry caches one per agent_id)
```

```python
from agentkit.sdk import azure_openai_agent_client

def build_app() -> AgentApp:
    client_factory = azure_openai_agent_client(
        endpoint="https://my-project.services.ai.azure.com/api/projects/demo",
        model_deployment="gpt-4o",
    )
    return AgentApp(
        BaseAgentSettings(llm_provider="agent", llm_model="gpt-4o", auth_enabled=False),
        config=_HERE / "agent_config.yaml",
        agent_client=client_factory,                # echo → real: this line only
        allowed_tool_prefixes=("agentkit.examples.hello_agent.",),
        default_agent_id="hello",
    )
```

- Needs `pip install "agentkit[maf,azure]"`. The SDK imports happen **lazily
  inside the factory** — importing the module costs nothing.
- `credential=None` builds and caches one `DefaultAzureCredential()` — the same
  code path local (CLI login) and in cloud (workload identity). No keys.
- An empty `endpoint`/`model_deployment` raises `ValueError` eagerly.

---

## 4. The `create_app()` one-liner

`create_app` ([`app/quickstart.py`](app/quickstart.py)) collapses settings +
tool-prefix + client into one keyword call, and fixes the fail-closed allowlist
footgun (a single string prefix is normalised to the tuple the resolver wants):

```python
create_app(
    *,
    settings: BaseAgentSettings | None = None,    # None → BaseAgentSettings.from_env()
    config: str | Path,
    agent_client,
    tools_prefix: str | tuple[str, ...] | list[str] | None = None,
    store=None,
    default_agent_id: str | None = None,
    domain_events: tuple[str, ...] = (),
    tools: list | None = None,
    request_scope_builder=None,
    responses_client=None,
    time_context_note: str = "",
) -> AgentApp
```

```python
from agentkit.app import create_app
from agentkit.sdk import azure_openai_agent_client

app = create_app(
    config="control/agent_config.yaml",
    agent_client=azure_openai_agent_client(
        endpoint="https://my-project.services.ai.azure.com/api/projects/demo",
        model_deployment="gpt-4o",
    ),
    tools_prefix="agentkit.examples.hello_agent.",   # bare str → ("...",), no footgun
    default_agent_id="hello",
)
```

`settings=None` builds via `BaseAgentSettings.from_env()` (rung 6). For an
env-independent quickstart, pass an explicit `settings=` so ambient
`AUTH_ENABLED` cannot ValidationError the build.

---

## 5. Add a custom tool

A tool is a plain callable. Decorate it with `@tool` from `agentkit.tools`
([`tools/__init__.py`](tools/__init__.py)) and declare it in the YAML.

```python
tool(*, approval_mode: str = "never_require", description: str | None = None)
```

The marker → bind flow: `@tool` does **not** wrap the function — it stamps
`fn.__agentkit_tool__ = {"approval_mode", "description"}` and returns the same
callable unchanged. The concrete SDK binding is applied later, at agent-build
time, by `agentkit.sdk.maf_client.bind_tools` (it reads the marker and applies
the real SDK `@tool`). So the same tool script works against the MAF client, the
echo/mock stub, or a future SDK — no edit. Place `@tool` **outermost** if you
stack inner decorators (e.g. `@traced_tool`).

```python
# my_tools.py
from agentkit.tools import tool


@tool()
def count_words(text: str) -> str:
    """Count the words in the given text."""
    return f"word_count={len(text.split())}"
```

One YAML line under the agent's `tools:` (the entry is `module:function`, and
its module must sit under an `allowed_tool_prefixes` / `tools_prefix` entry):

```yaml
agents:
  default: hello
  hello:
    name: HelloAgent
    instructions:
      - hello.md
    tools:
      - agentkit.examples.hello_agent.echo_tool:echo
      - my_package.my_tools:count_words          # the new tool
```

Then widen the allowlist so the resolver may import it:

```python
allowed_tool_prefixes=("agentkit.examples.hello_agent.", "my_package.")
```

The allowlist is fail-closed: `()` forbids every tool import, and an
unresolvable / out-of-prefix spec fails loud at build.

---

## 6. Settings from env

`BaseAgentSettings.from_env` ([`config/settings.py`](config/settings.py)) builds
from the environment with explicit overrides applied **correctly**:

```python
BaseAgentSettings.from_env(**overrides) -> BaseAgentSettings
```

```python
from agentkit.config import BaseAgentSettings, configure_settings

settings = BaseAgentSettings.from_env(auth_enabled=False)
configure_settings(settings)            # register the process-wide snapshot
```

Two documented traps:

- **Lazy bare-build / ValidationError.** A bare `BaseAgentSettings()` (which
  `get_settings()` builds when nothing is registered) `ValidationError`s on
  required provider/auth fields in an isolated context. `from_env` does **not**
  auto-register — pair it with `configure_settings(...)`. In tests,
  snapshot/restore the raw `agentkit.config.settings._active_settings` module
  global around `configure_settings`, never via `get_settings()`.
- **`validation_alias`-only fields ignore kwargs.** A field declared with
  `validation_alias` and no `populate_by_name` (e.g.
  `llmops_backend = Field(validation_alias=AliasChoices("LLMOPS_BACKEND"))`) can
  be set **only** via its env-var alias — a bare `llmops_backend="..."` kwarg to
  `cls(...)` is dropped silently. `from_env` detects these and routes the
  override through `os.environ` (set → build → restore) so it actually takes
  effect.

---

## 7. Go durable / serve

- **Durable store.** The default store is pure in-memory (zero-infra). Inject a
  `SessionStore` ([`persistence/`](persistence/README.md)) for durability:
  `AgentApp(..., store=my_store)`. Subclass `CosmosContainerStore` (inject the
  Cosmos client behind your credential seam) or implement the `SessionStore`
  Protocol for any backend. The two-phase in-memory → durable warmup stays the
  consumer's concern.
- **Mount on FastAPI.** `app.router()` returns a mountable `APIRouter`
  (`POST /chat/{sid}` SSE + `GET /sessions`):

  ```python
  from fastapi import FastAPI
  api = FastAPI()
  api.include_router(build_app().router(), prefix="/api")
  ```

- **Run uvicorn.** `app.serve()` is the one-call quickstart server.

Both `.router()` and `.serve()` need the `[fastapi]` extra (imported lazily).
For depth on any layer, see the per-subpackage READMEs linked from
[`README.md`](README.md).
