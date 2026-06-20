#!/usr/bin/env python3
"""sse_contract_probe.py — live-equivalent SSE event-sequence assertion harness.

Drives a deployed agentkit app through one chat round trip and asserts the
foreground SSE event-sequence contract:

- Exactly one terminal frame ``DONE | ERROR | ABORTED``.
- No frame follows the terminal.
- Every ``TOOL_CALL_END.id`` has a matching prior ``TOOL_CALL_START.id``.
- ``METADATA`` precedes ``DONE`` when ``DONE`` is the terminal.
- No frame's encoded ``data:`` field exceeds the configured byte cap
  (default 64 KiB, ``MAX_SSE_FRAME_BYTES`` on the deployed app).

This is a probe, not a test. It exercises the live app via Ed25519-signed
requests (same signing path as ``agentkit.dev_tools.dev_sign``). The legal
event vocabulary is ``known_event_names()`` — the generic core plus whatever
domain event names the consumer registered via
``agentkit.hosting.sse.register_domain_events`` before invoking ``main``.

Usage::

    python3 -m agentkit.dev_tools.sse_contract_probe \\
        --base-url https://<app>.<fqdn> \\
        [--max-frame-bytes 65536] [--timeout 180]

Exit codes:
    0 — all assertions pass.
    1 — one or more assertions fail (details printed to stderr).
    2 — probe could not run (no key, network error, non-2xx on session).

Confidentiality:
    The synthetic trigger uses ``STN_A`` / ``CB-101`` / ISO timestamps —
    Synthetic placeholders. Do not edit this script to use real identifiers.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Generic SSE contract core (S2) lives in agentkit. The legal event
# vocabulary is ``known_event_names()``; the consumer registers its domain
# event names via ``register_domain_events`` before calling ``main``.
from agentkit.hosting.probe import check_event_sequence, parse_sse_frames
from agentkit.hosting.sse import GENERIC_TERMINALS, known_event_names


# ── Key + signing (must mirror scripts/dev_sign.py exactly) ──────────────

_KEY_FILE = Path.home() / ".gridiq" / "dev_signing_key"
_TS_HEADER = "X-Request-Timestamp"
_SIG_HEADER = "X-Request-Signature"
_CTX_HEADER = "X-Request-Context"

# Synthetic trigger. Any change here MUST stay within the
# placeholder vocabulary defined in README.md §1.
_TRIGGER_MESSAGE = (
    "Investigate STN_A, 2024-04-15T10:00:00 to 2024-04-15T10:10:00. "
    "Alarm signals: cb_trip=5."
)


def _load_priv() -> Ed25519PrivateKey:
    if not _KEY_FILE.exists():
        raise SystemExit(
            f"no private key at {_KEY_FILE} — run `python3 scripts/dev_sign.py init` first."
        )
    raw = _KEY_FILE.read_bytes()
    return Ed25519PrivateKey.from_private_bytes(raw)


# Context slug used for signing. The deployed app rejects the default
# identity ("Default identity cannot create sessions; sign with a context
# slug."), so the probe signs as a named dev context. Overridable via
# ``--context``; mutated once in ``main``.
_CONTEXT_SLUG = "regress"


def _sign(method: str, path_q: str, body: bytes) -> dict[str, str]:
    # Mirror scripts/dev_sign.py exactly: microsecond-precision timestamp,
    # normalised context slug in BOTH the canonical string and the
    # X-Request-Context header. The canonical is
    # ``METHOD\npath\nts\nslug\nbody_sha256``.
    priv = _load_priv()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    slug = (_CONTEXT_SLUG or "").strip().lower()
    body_sha = hashlib.sha256(body).hexdigest()
    canon = (
        f"{method.upper()}\n{path_q}\n{ts}\n{slug}\n{body_sha}"
    ).encode("ascii")
    sig = priv.sign(canon)
    headers = {
        _TS_HEADER: ts,
        _SIG_HEADER: base64.b64encode(sig).decode("ascii"),
    }
    if slug:
        headers[_CTX_HEADER] = slug
    return headers


# ── HTTP helpers ─────────────────────────────────────────────────────────


def _request(
    method: str, base: str, path_q: str, body: bytes | None, timeout: float
) -> tuple[int, bytes]:
    headers = _sign(method, path_q, body or b"")
    if body:
        headers["Content-Type"] = "application/json"
    url = base.rstrip("/") + path_q
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit(f"bad URL: {url}")
    req = urllib.request.Request(
        url=parsed.geturl(), data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _stream(
    base: str, path_q: str, body: bytes, timeout: float
) -> "Iterable[tuple[str, str]]":
    """Yield ``(event_name, data_json_str)`` pairs from an SSE stream."""
    headers = _sign("POST", path_q, body)
    headers["Content-Type"] = "application/json"
    headers["Accept"] = "text/event-stream"
    url = base.rstrip("/") + path_q
    parsed = urlsplit(url)
    req = urllib.request.Request(
        url=parsed.geturl(), data=body, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise SystemExit(f"chat POST returned HTTP {resp.status}")
        # Parse via the generic agentkit SSE frame parser so wire-format
        # handling stays single-sourced with the kit.
        yield from parse_sse_frames(resp)


# ── Assertions ───────────────────────────────────────────────────────────

# Terminal frame names + the full assertion are single-sourced from
# agentkit; the vocabulary check uses ``known_event_names()`` (generic core
# plus any domain events the consumer registered before invoking main).
_TERMINALS = set(GENERIC_TERMINALS)


def _check_sequence(
    frames: list[tuple[str, str]], max_frame_bytes: int
) -> list[str]:
    """Delegate to the generic agentkit contract checker.

    Returns a list of failure messages (empty = all assertions pass). The
    legal event vocabulary is ``known_event_names()`` — generic core plus
    any domain events registered by the consumer.
    """
    return check_event_sequence(
        frames, max_frame_bytes, allowed_events=known_event_names()
    )


# ── Main ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base-url",
        default=os.environ.get("APP_URL", ""),
        help="App base URL, e.g. https://pathfinderiq-aemo.<fqdn>",
    )
    parser.add_argument(
        "--max-frame-bytes",
        type=int,
        default=int(os.environ.get("MAX_SSE_FRAME_BYTES", "65536")),
        help="Upper bound on the encoded data: field per SSE frame.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--agent-id",
        default="",
        help="Optional agent_id query string for the chat POST.",
    )
    parser.add_argument(
        "--context",
        default=os.environ.get("PROBE_CONTEXT", "regress"),
        help="Dev context slug to sign as (the app rejects the default identity).",
    )
    args = parser.parse_args(argv)

    # Bind the signing context for all subsequent _sign calls.
    global _CONTEXT_SLUG
    _CONTEXT_SLUG = args.context

    if not args.base_url:
        print("no base URL — pass --base-url or set APP_URL", file=sys.stderr)
        return 2

    # 1) Create a session.
    status, body = _request(
        "POST", args.base_url, "/api/sessions", b"{}", args.timeout
    )
    if status not in (200, 201):
        print(
            f"session create failed: HTTP {status}: {body!r}", file=sys.stderr
        )
        return 2
    try:
        session_id = json.loads(body).get("id") or json.loads(body).get("session_id")
    except json.JSONDecodeError:
        print(f"session create returned non-JSON body: {body!r}", file=sys.stderr)
        return 2
    if not session_id:
        print(f"session create returned no id: {body!r}", file=sys.stderr)
        return 2

    # 2) Drive one chat round trip and collect frames.
    chat_path = f"/api/chat/{session_id}"
    if args.agent_id:
        chat_path += f"?agent_id={args.agent_id}"
    chat_body = json.dumps({"content": _TRIGGER_MESSAGE}).encode("utf-8")
    frames: list[tuple[str, str]] = []
    try:
        for name, data in _stream(
            args.base_url, chat_path, chat_body, args.timeout
        ):
            frames.append((name, data))
            if name in _TERMINALS:
                break
    except (urllib.error.URLError, ConnectionError) as exc:
        print(f"stream error: {exc}", file=sys.stderr)
        return 2

    # 3) Best-effort cleanup. Failure here does not affect the verdict.
    try:
        _request("DELETE", args.base_url, f"/api/sessions/{session_id}", None, 10.0)
    except Exception:
        pass

    # 4) Assert.
    failures = _check_sequence(frames, args.max_frame_bytes)
    if failures:
        print("SSE contract probe: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        print(f"  frames seen: {len(frames)}", file=sys.stderr)
        return 1
    print(f"SSE contract probe: PASS ({len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
