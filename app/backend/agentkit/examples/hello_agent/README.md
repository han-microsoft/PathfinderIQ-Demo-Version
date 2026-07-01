# agentkit.examples.hello_agent

The zero-infra quickstart — stand up a working streaming, tool-calling agent in a few lines using ONLY agentkit (a stub `AgentClient`, the in-memory store, no consumer import, no Azure infra). This is the pass/fail gate for the project goal.

## Run it
```bash
python3 -m agentkit.examples.hello_agent.app     # headless: prints token/done events
```
Serve over HTTP instead: `build_app().serve()` (needs the `[fastapi]` extra).

## Files
| File | Role |
|---|---|
| `app.py` | `build_app()` — the whole wiring (~7 lines) + an async `_demo()` |
| `agent_config.yaml` | one agent (`hello`), one tool, one prompt — the entire declarative surface |
| `echo_tool.py` | the one tool: a plain `echo(text) -> str` callable |
| `stub_client.py` | `EchoClientFactory` → `EchoAgent` — a stub `AgentClient` (`as_agent`) that streams the input back as SDK-shaped updates; no SDK, no network |
| `prompts/hello.md` | the agent instructions |

## The wiring (`build_app`)
```python
AgentApp(
    BaseAgentSettings(llm_provider="agent", llm_model="echo-1", auth_enabled=False),
    config=_HERE / "agent_config.yaml",
    agent_client=EchoClientFactory(),
    allowed_tool_prefixes=("agentkit.examples.hello_agent.",),
    default_agent_id="hello",
)
```

## How to go further
- **echo → real LLM** → replace `EchoClientFactory()` with a factory backed by `agentkit.sdk.maf_client` (the MAF seam). Change nothing else.
- **add a tool** → add `mypkg.mod:fn` under the agent's `tools:` in the YAML and widen `allowed_tool_prefixes`.
- **add an agent** → a new block under `agents:` in the YAML.

## Gotchas
- `auth_enabled=False` is passed explicitly so the example is env-independent (a sourced `AUTH_ENABLED=true` shell would otherwise ValidationError).
- The stub agent ignores tools/middleware/providers — it only proves the wiring. A real client honours them.

## Zero-domain assertion
The acceptance test (`tests/unit/test_hello_agent_example.py`) runs this example in a fresh interpreter and asserts it imports **zero** consumer package and **zero** Azure SDK. Domain-neutral by construction (echo only).
