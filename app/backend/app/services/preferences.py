"""User preferences — per-user scenario selection (runtime swap persistence).

Module role:
    In-memory, per-user (OID-keyed) store of the selected scenario. Backs the
    runtime scenario-swap so a user's choice survives a page refresh without a
    header, while staying isolated from other users. Mirrors the InMemory
    session-store posture: process-local, no cloud dependency.

    Preferences are intentionally scenario-only (the single user-owned runtime
    selector). The effective graph backend + model are derived from the
    scenario, not stored here.

Dependents:
    - app.routers.preferences        — GET /api/preferences
    - app.routers.scenario           — POST /api/scenarios/select
    - app._middleware                — tier-2 scenario resolution (no header)
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from app.foundation.config import settings

logger = logging.getLogger(__name__)


@dataclass
class UserPreferences:
    """A single user's runtime preferences (scenario-only)."""

    scenario_name: str = ""


class InMemoryPreferencesStore:
    """Process-local, OID-keyed scenario preferences. Thread-safe.

    Constructed with a ``UserPreferences`` default that supplies the scenario
    for any user who has not made a choice. Recreating the store (restart)
    resets every user back to that default.
    """

    def __init__(self, defaults: UserPreferences | None = None) -> None:
        self._default = defaults or UserPreferences(scenario_name=settings.scenario_name or "")
        self._prefs: dict[str, UserPreferences] = {}
        self._lock = threading.Lock()

    def get_scenario(self, oid: str) -> str:
        """Return the user's selected scenario, or the operator default."""
        with self._lock:
            rec = self._prefs.get(oid)
        stored = rec.scenario_name if rec else ""
        return stored or self._default.scenario_name

    def get(self, oid: str) -> dict[str, str]:
        """Return the JSON-safe preferences payload (scenario-only)."""
        return {"scenario_name": self.get_scenario(oid)}

    def set_scenario(self, oid: str, scenario_name: str) -> None:
        """Persist the user's scenario choice (process lifetime)."""
        with self._lock:
            self._prefs[oid] = UserPreferences(scenario_name=scenario_name)
        logger.info("preferences.scenario_set oid=%s scenario=%s", oid, scenario_name)

    def clear(self) -> None:
        """Drop all stored preferences (test hygiene)."""
        with self._lock:
            self._prefs.clear()


def new_default_store() -> InMemoryPreferencesStore:
    """Build a store seeded from the operator default (``settings.scenario_name``)."""
    return InMemoryPreferencesStore(UserPreferences(scenario_name=settings.scenario_name or ""))


def get_preferences_store(request) -> InMemoryPreferencesStore:
    """Return the live preferences store, lazily attaching one to app.state.

    Reading from ``app.state.preferences`` (not a module singleton) means a
    restart — which replaces ``app.state.preferences`` — resets all per-user
    state, exactly as the isolation contract requires.
    """
    store = getattr(request.app.state, "preferences", None)
    if store is None:
        store = new_default_store()
        request.app.state.preferences = store
    return store
