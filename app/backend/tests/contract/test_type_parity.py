"""Backend→Frontend type parity — every Pydantic field must exist in types.ts.

Phase 1.3: Automated contract test that catches schema drift between backend
Pydantic models (app/models.py) and frontend TypeScript types (api/types.ts).

Strategy:
    - Backend fields must be a SUBSET of frontend fields (frontend may have
      extra rendering-only fields like 'parts', 'status', 'summary').
    - Backend enum values must be a SUBSET of frontend enum values (frontend
      may have additional values like ToolCallStatus).
    - A JSON schema snapshot detects unreviewed model changes.

Dependents:
    Every phase that modifies models.py or types.ts benefits from this safety net.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.foundation.models import (
    ChatRequest,
    CreateSessionRequest,
    Message,
    MessageStatus,
    Role,
    Session,
    SessionSummary,
    StreamEventType,
    StreamMetadata,
    ToolCall,
    UpdateSessionRequest,
)

# ── Path to frontend types ───────────────────────────────────────────────────
# tests/contract/test_type_parity.py → app/backend/tests/contract/
# parents[3] → app/backend/ → parents[1] → app/ → frontend/src/api/types.ts
_TYPES_TS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "types.ts"

# ── Snapshot path for schema drift detection ─────────────────────────────────
_SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"
_SNAPSHOT_PATH = _SNAPSHOT_DIR / "model_schemas.json"


# ── TypeScript parser ────────────────────────────────────────────────────────
# Handles the simple flat-interface format used in types.ts.
# Does NOT handle nested braces, generics, or conditional types.


def _parse_ts_interfaces(content: str) -> dict[str, set[str]]:
    """Parse TypeScript interfaces into {InterfaceName: {field_names}}.

    Extracts field names only (not types). Strips trailing comments,
    optional markers, and semicolons. Returns a set of field names
    per interface.
    """
    interfaces: dict[str, set[str]] = {}
    # Match 'export interface Name { ... }' blocks
    pattern = r"export\s+interface\s+(\w+)\s*\{([^}]*)\}"
    for match in re.finditer(pattern, content, re.DOTALL):
        name = match.group(1)
        body = match.group(2)
        fields: set[str] = set()
        for line in body.strip().split("\n"):
            # Strip comments from the line before parsing
            line = re.sub(r"//.*$", "", line).strip().rstrip(";")
            if not line:
                continue
            # Parse 'fieldName: type' or 'fieldName?: type'
            field_match = re.match(r"(\w+)\??:", line)
            if field_match:
                fields.add(field_match.group(1))
        interfaces[name] = fields
    return interfaces


def _extract_string_union(content: str, type_name: str) -> set[str]:
    """Extract values from a TypeScript string union type alias.

    Parses: export type Foo = "a" | "b" | "c";
    Returns: {"a", "b", "c"}
    """
    # Match across multiple lines (type alias may be multi-line)
    pattern = rf"export\s+type\s+{type_name}\s*=\s*([\s\S]*?);"
    m = re.search(pattern, content)
    if not m:
        return set()
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _pydantic_field_names(model: type) -> set[str]:
    """Extract field names from a Pydantic BaseModel class."""
    return set(model.model_fields.keys())


# ── Model↔Interface mapping ─────────────────────────────────────────────────
# Maps backend Pydantic model classes → frontend TypeScript interface names.
# Only models that cross the wire are included.

_MODEL_MAP: dict[type, str] = {
    ToolCall: "ToolCall",
    Message: "Message",
    Session: "Session",
    SessionSummary: "SessionSummary",
    ChatRequest: "ChatRequest",
    CreateSessionRequest: "CreateSessionRequest",
    UpdateSessionRequest: "UpdateSessionRequest",
    StreamMetadata: "StreamMetadata",
}

# Backend-only StreamEventType values that are intentionally NOT in the
# frontend type alias (reserved for future use or internal-only events).
_BACKEND_ONLY_EVENT_TYPES: set[str] = set()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestFrontendTypesFileExists:
    """Guard: types.ts must exist at the expected path."""

    def test_types_ts_exists(self):
        """Frontend types.ts must be present for contract tests to run."""
        assert _TYPES_TS.exists(), (
            f"Frontend types.ts not found at {_TYPES_TS}. "
            f"Contract tests require the frontend types file."
        )


class TestTypeParity:
    """Every backend Pydantic field must exist in the frontend TypeScript interface."""

    @classmethod
    def setup_class(cls):
        """Parse types.ts once for all tests in this class."""
        if not _TYPES_TS.exists():
            pytest.skip("Frontend types.ts not found")
        cls.ts_content = _TYPES_TS.read_text()
        cls.ts_interfaces = _parse_ts_interfaces(cls.ts_content)

    def test_all_backend_models_have_frontend_counterparts(self):
        """Every mapped Pydantic model has a corresponding TypeScript interface."""
        for model, ts_name in _MODEL_MAP.items():
            assert ts_name in self.ts_interfaces, (
                f"Backend model {model.__name__} maps to '{ts_name}' "
                f"but no 'export interface {ts_name}' found in types.ts"
            )

    @pytest.mark.parametrize(
        "model,ts_name",
        list(_MODEL_MAP.items()),
        ids=[m.__name__ for m in _MODEL_MAP],
    )
    def test_backend_fields_subset_of_frontend(self, model, ts_name):
        """Every field in a backend model must exist in the frontend interface."""
        backend_fields = _pydantic_field_names(model)
        frontend_fields = self.ts_interfaces.get(ts_name, set())
        missing = backend_fields - frontend_fields
        assert not missing, (
            f"{model.__name__} has fields {missing} not in {ts_name}. "
            f"Backend fields: {sorted(backend_fields)}. "
            f"Frontend fields: {sorted(frontend_fields)}."
        )

    def test_role_enum_parity(self):
        """Backend Role enum values must be a subset of frontend Role type."""
        backend = {e.value for e in Role}
        frontend = _extract_string_union(self.ts_content, "Role")
        missing = backend - frontend
        assert not missing, f"Role values {missing} not in frontend type"

    def test_message_status_enum_parity(self):
        """Backend MessageStatus values must be a subset of frontend MessageStatus."""
        backend = {e.value for e in MessageStatus}
        frontend = _extract_string_union(self.ts_content, "MessageStatus")
        missing = backend - frontend
        assert not missing, f"MessageStatus values {missing} not in frontend type"

    def test_stream_event_type_parity(self):
        """Backend StreamEventType values (minus known backend-only) must be in frontend."""
        backend = {e.value for e in StreamEventType} - _BACKEND_ONLY_EVENT_TYPES
        frontend = _extract_string_union(self.ts_content, "StreamEventType")
        missing = backend - frontend
        assert not missing, (
            f"StreamEventType values {missing} not in frontend type. "
            f"If intentionally backend-only, add to _BACKEND_ONLY_EVENT_TYPES."
        )


class TestModelSchemaSnapshot:
    """Detect unreviewed model changes by comparing against a stored snapshot.

    On first run, generates the snapshot file. On subsequent runs, compares
    current schemas against the stored snapshot and fails if they differ.
    To update the snapshot after an intentional change:
        cd app/backend && LLM_PROVIDER=echo OTEL_EXPORT_TARGET= \
          .venv/bin/python -m pytest tests/contract/test_type_parity.py \
          --update-snapshots -v
    """

    @staticmethod
    def _current_schemas() -> dict[str, dict]:
        """Generate JSON schemas for all mapped models."""
        schemas = {}
        for model in _MODEL_MAP:
            schemas[model.__name__] = model.model_json_schema()
        return schemas

    def test_schema_snapshot(self, request):
        """Model JSON schemas must match the stored snapshot."""
        current = self._current_schemas()

        # Check for --update-snapshots flag (custom pytest option or marker)
        update = request.config.getoption("--update-snapshots", default=False)

        if update or not _SNAPSHOT_PATH.exists():
            # Generate or update the snapshot
            _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            _SNAPSHOT_PATH.write_text(
                json.dumps(current, indent=2, sort_keys=True) + "\n"
            )
            if update:
                pytest.skip("Snapshot updated")
            else:
                # First run — snapshot created, pass
                return

        stored = json.loads(_SNAPSHOT_PATH.read_text())
        if current != stored:
            # Find which models changed
            changed = []
            for name in sorted(set(list(current.keys()) + list(stored.keys()))):
                if current.get(name) != stored.get(name):
                    changed.append(name)
            pytest.fail(
                f"Model schemas changed: {changed}. "
                f"Review frontend types.ts for parity, then update snapshot:\n"
                f"  cd app/backend && LLM_PROVIDER=echo OTEL_EXPORT_TARGET= "
                f'.venv/bin/python -m pytest tests/contract/test_type_parity.py '
                f"--update-snapshots"
            )


def pytest_addoption(parser):
    """Add --update-snapshots CLI option for snapshot regeneration."""
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Regenerate contract test schema snapshots",
    )
