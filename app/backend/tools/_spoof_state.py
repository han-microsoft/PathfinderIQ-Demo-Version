"""Session-scoped mutable state overlay for demo network actions.

Module role:
    Holds ephemeral operational state that spoofed tools write to and
    query tools read from. All state is keyed by session_id to prevent
    cross-user bleed. Reset on process restart.

Role in system:
    Part of the ``tools`` package. Shared state module consumed by
    spoofed action tools (network, incidents) and read by graph_explorer
    tools for overlay-based status overrides.

Key collaborators:
    - tools/network/_reroute_traffic.py  — writes _traffic_routes
    - tools/network/_set_link_status.py  — writes _link_status
    - tools/incidents/_create_ticket.py  — writes to action log
    - tools/incidents/_update_advisory.py — writes _advisories
    - tools/graph_explorer/*             — reads _link_status overlay

Thread safety:
    Single async worker (1 uvicorn worker). Dict operations are atomic
    in CPython. Session-scoped keys prevent cross-user bleed.

Dependents:
    Imported by: network tools, incidents tools, graph explorer overlay,
    test_spoof_state.py
"""

from __future__ import annotations

from datetime import datetime, timezone

# ── Session-scoped state stores ──────────────────────────────────────────────
# Each dict is keyed by session_id, then by entity ID.
# All are ephemeral — cleared on process restart.

_link_status: dict[str, dict[str, dict]] = {}     # session → link → {status, changed_at}
_traffic_routes: dict[str, dict[str, dict]] = {}  # session → path → {is_active, ...}
_advisories: dict[str, dict[str, dict]] = {}      # session → advisory → {...}
_action_log: dict[str, list[dict]] = {}            # session → [action entries]


def get_link_status(session_id: str, link_id: str) -> dict | None:
    """Get the spoofed status of a transport link.

    Args:
        session_id: The session to query.
        link_id: Transport link ID (e.g., "LINK-SYD-MEL-FIBRE-01").

    Returns:
        Status dict with link_id, status, changed_at — or None if no
        override exists for this session+link.

    Side effects:
        None — pure read.
    """
    return _link_status.get(session_id, {}).get(link_id)


def set_link_status(session_id: str, link_id: str, status: str) -> dict:
    """Override a transport link's operational status.

    Args:
        session_id: The session scope.
        link_id: Transport link ID.
        status: Target status ("admin_down" or "admin_up").

    Returns:
        The stored entry dict.

    Side effects:
        Writes to _link_status and appends to _action_log.
    """
    entry = {
        "link_id": link_id,
        "status": status,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    }
    _link_status.setdefault(session_id, {})[link_id] = entry
    _action_log.setdefault(session_id, []).append({"action": "set_link_status", **entry})
    return entry


def activate_route(session_id: str, path_id: str, **kwargs) -> dict:
    """Activate a backup MPLS path for traffic rerouting.

    Args:
        session_id: The session scope.
        path_id: MPLS backup path ID (e.g., "MPLS-BACKUP-02").
        **kwargs: Additional context (reason, etc.).

    Returns:
        The stored entry dict.

    Side effects:
        Writes to _traffic_routes and appends to _action_log.
    """
    entry = {
        "path_id": path_id,
        "is_active": True,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    _traffic_routes.setdefault(session_id, {})[path_id] = entry
    _action_log.setdefault(session_id, []).append({"action": "reroute_traffic", **entry})
    return entry


def post_advisory(session_id: str, advisory_id: str, **kwargs) -> dict:
    """Post a customer-facing service advisory.

    Args:
        session_id: The session scope.
        advisory_id: Generated advisory ID (e.g., "ADV-20260228-120000").
        **kwargs: Additional fields (text, regions, resolution).

    Returns:
        The stored entry dict.

    Side effects:
        Writes to _advisories and appends to _action_log.
    """
    entry = {
        "advisory_id": advisory_id,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
    _advisories.setdefault(session_id, {})[advisory_id] = entry
    _action_log.setdefault(session_id, []).append({"action": "update_advisory", **entry})
    return entry


def log_action(session_id: str, action: str, **kwargs) -> None:
    """Append a generic action entry to the session's action log.

    Args:
        session_id: The session scope.
        action: Action name (e.g., "create_incident_ticket").
        **kwargs: Additional context fields.

    Side effects:
        Appends to _action_log.
    """
    _action_log.setdefault(session_id, []).append(
        {"action": action, "timestamp": datetime.now(timezone.utc).isoformat(), **kwargs}
    )


def get_action_log(session_id: str) -> list[dict]:
    """Return a copy of the session's action log.

    Args:
        session_id: The session to query.

    Returns:
        List of action dicts in chronological order.

    Side effects:
        None — returns a copy to prevent caller mutation.
    """
    return list(_action_log.get(session_id, []))


def reset(session_id: str | None = None) -> None:
    """Clear spoof state — either for one session or globally.

    Args:
        session_id: If provided, clears only that session's state.
                    If None, clears all sessions (process-wide reset).

    Side effects:
        Mutates all four state dicts.
    """
    if session_id:
        for d in (_link_status, _traffic_routes, _advisories, _action_log):
            d.pop(session_id, None)
    else:
        for d in (_link_status, _traffic_routes, _advisories, _action_log):
            d.clear()
