"""Shared fixtures across all test layers."""

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from app.foundation.models import Message, Role, Session


# Force the lightweight provider for tests that import app settings at module load.
os.environ.setdefault("LLM_PROVIDER", "echo")
os.environ.setdefault("OTEL_EXPORT_TARGET", "")
os.environ.setdefault("AUTH_ENABLED", "false")


@pytest.fixture(autouse=True)
def _reset_process_swap_state():
    """Clear process-global swap caches around every test (order isolation).

    The app object is a module singleton shared across the whole suite, so
    per-scenario caches (RequestScope cache, per-user preferences, agent
    config cache) would otherwise bleed across test modules and make results
    order-dependent. Resetting on teardown keeps every test hermetic.
    """
    yield
    try:
        from app import _middleware
        _middleware._scope_cache.clear()
    except Exception:
        pass
    try:
        from app.main import app
        from app.services.preferences import new_default_store
        app.state.preferences = new_default_store()
    except Exception:
        pass
    try:
        from agents._config import invalidate_cache
        invalidate_cache()
    except Exception:
        pass


@pytest.fixture
def sample_messages():
    """A list of messages for context manager tests."""
    return [
        Message(role=Role.USER, content="Hello"),
        Message(role=Role.ASSISTANT, content="Hi there! How can I help?"),
        Message(role=Role.USER, content="What's the status of router CORE-SYD-01?"),
    ]


@pytest.fixture
def sample_session(sample_messages):
    """A session with messages for CRUD tests."""
    return Session(title="Test session", messages=sample_messages)


@pytest.fixture
def temp_scenario():
    """Create a temporary scenario directory under the live graph_data root.

    Returns:
        Callable that creates a scenario and returns its discoverable name.

    Side effects:
        Writes scenario files under graph_data/data/scenarios/ and removes them
        after the test completes.
    """
    from app.scenario._reader import _graph_data_root

    scenarios_root = _graph_data_root() / "data" / "scenarios"
    created_dirs: list[Path] = []

    def _create(
        name: str,
        *,
        display_name: str | None = None,
        graph: str = "fabric",
        topology_node_count: int = 3,
        fabric_config: dict[str, str] | None = None,
        agent_model: str = "gpt-5.2",
    ) -> str:
        scenario_dir = scenarios_root / name
        if scenario_dir.exists():
            shutil.rmtree(scenario_dir)

        scenario_dir.mkdir(parents=True)
        created_dirs.append(scenario_dir)

        prompts_dir = scenario_dir / "data" / "prompts"
        (prompts_dir / "query_language").mkdir(parents=True)
        (prompts_dir / "core_rules.md").write_text("Temporary test prompt.\n", encoding="utf-8")
        (prompts_dir / "query_language" / "cypher.md").write_text("Cypher prompt\n", encoding="utf-8")
        (prompts_dir / "query_language" / "gql.md").write_text("GQL prompt\n", encoding="utf-8")
        (prompts_dir / "query_language" / "gremlin.md").write_text("Gremlin prompt\n", encoding="utf-8")

        manifest = {
            "name": name,
            "display_name": display_name or name,
            "description": f"Temporary scenario {name}",
            "version": "test",
            "services": {"fabric": fabric_config or {}},
            "agents": {
                "default": "orchestrator",
                "orchestrator": {
                    "name": f"{name}-agent",
                    "model": agent_model,
                    "description": "Temporary agent",
                    "instructions": ["core_rules.md"],
                    "tools": ["tools.thinking:thinking"],
                },
            },
        }
        (scenario_dir / "scenario.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )

        topology = {
            "topology_nodes": [{"id": f"node-{index}"} for index in range(topology_node_count)],
            "topology_edges": [],
        }
        (scenario_dir / "topology.json").write_text(json.dumps(topology), encoding="utf-8")
        return name

    yield _create

    for scenario_dir in reversed(created_dirs):
        shutil.rmtree(scenario_dir, ignore_errors=True)
