#!/usr/bin/env python3
"""dev_sign.py — local Ed25519 keypair manager + request signer.

This script never leaves the operator's machine. The private key it
creates likewise never leaves: it is written to
``~/.gridiq/dev_signing_key`` with file mode ``0600`` and only the
matching public key is intended to be transmitted (to the deployed
app as the ``DEV_PUBLIC_KEY_ED25519`` env var).

The canonical string + header names mirror the server-side devauth
verifier exactly; both sides MUST stay in lockstep.

Subcommands
-----------

``init``       — generate a new keypair. Refuses to overwrite an
                 existing key unless ``--force`` is passed. Prints the
                 public key (base64 of 32 raw bytes) to stdout for
                 pasting into ``az containerapp update --set-env-vars``.

``pubkey``     — print the public key for the existing private key.
                 Useful when re-deploying or onboarding a new server
                 instance without rotating.

``sign``       — given ``METHOD PATH [--body-file FILE] [--context SLUG]``,
                 emit the three header values that the operator (or
                 ``curl``) should attach to the outgoing request.

``request``    — sign and execute the request against
                 ``--base-url`` (default reads ``APP_URL`` env var).
                 Streams stdout. Exits non-zero on non-2xx.

Examples
--------

    # one-time setup
    $ python3 -m agentkit.dev_tools.dev_sign init
    DEV_PUBLIC_KEY_ED25519=Ej...base64...==

    # push to the live app
    $ az containerapp update --name <app> \\
        --resource-group <rg> \\
        --set-env-vars DEV_PUBLIC_KEY_ED25519=Ej...base64...==

    # smoke a GET
    $ python3 -m agentkit.dev_tools.dev_sign request GET /api/sessions

    # smoke a POST (body from stdin or --body-file)
    $ echo '{"content":"hi"}' | python3 -m agentkit.dev_tools.dev_sign \\
        request POST /api/chat/some-session-id

This tool is part of the devauth feature and is deleted in lockstep
with the server-side devauth middleware on production cutover.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

# ``cryptography`` is already a transitive dependency of the repo; no
# extra install required on the operator's PC.
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


# ── Key file location ─────────────────────────────────────────────────────

_KEY_DIR = Path.home() / ".gridiq"
_KEY_FILE = _KEY_DIR / "dev_signing_key"

# The header names match exactly what the server-side devauth
# middleware looks up. Both sides MUST stay in lockstep.
_TS_HEADER = "X-Request-Timestamp"
_SIG_HEADER = "X-Request-Signature"
_CTX_HEADER = "X-Request-Context"


# ── Key file I/O ──────────────────────────────────────────────────────────


def _load_private_key() -> Ed25519PrivateKey:
    """Read the operator's private key. Refuse to read if file mode is
    too permissive — guards against accidental ``chmod 644`` or a copy
    onto a shared drive."""
    if not _KEY_FILE.exists():
        raise SystemExit(
            f"no private key at {_KEY_FILE} — run `dev_sign.py init` first."
        )
    file_mode = stat.S_IMODE(_KEY_FILE.stat().st_mode)
    if file_mode & 0o077:
        raise SystemExit(
            f"refusing to read {_KEY_FILE}: mode is {oct(file_mode)}, "
            f"expected 0600. Fix with `chmod 600 {_KEY_FILE}`."
        )
    raw = _KEY_FILE.read_bytes()
    if len(raw) != 32:
        raise SystemExit(
            f"{_KEY_FILE} is malformed (expected 32 bytes, got {len(raw)})"
        )
    return Ed25519PrivateKey.from_private_bytes(raw)


def _save_private_key(pk: Ed25519PrivateKey) -> None:
    """Atomically write the private key with mode 0600."""
    _KEY_DIR.mkdir(mode=0o700, exist_ok=True)
    raw = pk.private_bytes_raw()
    tmp = _KEY_FILE.with_suffix(".tmp")
    # Open with 0600 from the start; never let the file exist with
    # broader permissions even momentarily.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    tmp.replace(_KEY_FILE)


def _public_b64(pk: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    pub = pk.public_key() if isinstance(pk, Ed25519PrivateKey) else pk
    return base64.b64encode(pub.public_bytes_raw()).decode("ascii")


# ── Canonical string (must mirror _verifier.py exactly) ──────────────────


def _canonical(
    *, method: str, path_and_query: str, ts: str, context_slug: str, body: bytes
) -> bytes:
    body_sha = hashlib.sha256(body).hexdigest()
    return (
        f"{method.upper()}\n"
        f"{path_and_query}\n"
        f"{ts}\n"
        f"{context_slug}\n"
        f"{body_sha}"
    ).encode("ascii")


def _sign_headers(
    *,
    method: str,
    path_and_query: str,
    body: bytes,
    context_slug: str,
) -> dict[str, str]:
    """Produce the three request headers for the given request shape."""
    priv = _load_private_key()
    # Chaos hardening 2026-05-22 (CHAOS-033): microsecond-precision
    # timestamp so two legitimate concurrent requests with identical
    # method/path/body/slug do NOT collide on the same canonical
    # string. The 1-second-precision timestamp used previously meant
    # parallel identical requests produced byte-identical signatures,
    # which the server-side replay cache (CHAOS-026 fix) then rejected
    # as a replay. Microsecond ts naturally diverges and the cache
    # only catches true byte-replays.
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    slug_norm = (context_slug or "").strip().lower()
    msg = _canonical(
        method=method,
        path_and_query=path_and_query,
        ts=ts,
        context_slug=slug_norm,
        body=body,
    )
    sig = priv.sign(msg)
    headers = {
        _TS_HEADER: ts,
        _SIG_HEADER: base64.b64encode(sig).decode("ascii"),
    }
    if slug_norm:
        headers[_CTX_HEADER] = slug_norm
    return headers


# ── Subcommands ──────────────────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    """Generate a new keypair."""
    if _KEY_FILE.exists() and not args.force:
        print(
            f"refusing to overwrite {_KEY_FILE} (pass --force to rotate)",
            file=sys.stderr,
        )
        return 1
    pk = Ed25519PrivateKey.generate()
    _save_private_key(pk)
    print(f"# private key written to {_KEY_FILE} (mode 0600)", file=sys.stderr)
    print(f"DEV_PUBLIC_KEY_ED25519={_public_b64(pk)}")
    return 0


def cmd_pubkey(_args: argparse.Namespace) -> int:
    """Print the public key for the existing private key."""
    priv = _load_private_key()
    print(_public_b64(priv))
    return 0


def _read_body(args: argparse.Namespace) -> bytes:
    """Resolve the request body from ``--body-file`` or stdin."""
    if args.body_file:
        return Path(args.body_file).read_bytes()
    if not sys.stdin.isatty():
        return sys.stdin.buffer.read()
    return b""


def cmd_sign(args: argparse.Namespace) -> int:
    """Print signing headers as ``Name: value`` lines."""
    method = args.method.upper()
    path_q = args.path
    body = _read_body(args)
    headers = _sign_headers(
        method=method,
        path_and_query=path_q,
        body=body,
        context_slug=args.context,
    )
    for k, v in headers.items():
        print(f"{k}: {v}")
    return 0


def cmd_request(args: argparse.Namespace) -> int:
    """Sign and execute the request via stdlib urllib."""
    base = args.base_url or os.environ.get("APP_URL", "")
    if not base:
        print(
            "no base URL — pass --base-url or set APP_URL in the env",
            file=sys.stderr,
        )
        return 2
    method = args.method.upper()
    path_q = args.path
    body = _read_body(args)
    headers = _sign_headers(
        method=method,
        path_and_query=path_q,
        body=body,
        context_slug=args.context,
    )
    if body and "Content-Type" not in headers:
        # JSON is the only body shape this app accepts on the routes we
        # actually need to hit; declare it explicitly so FastAPI parses
        # the body. The Content-Type is not part of the signed string;
        # changing it does not invalidate the signature, but the body
        # itself is fully covered by the SHA-256 in the canonical
        # string.
        headers["Content-Type"] = "application/json"

    # Validate the URL parses (catches typos like "api.gridiq" without
    # scheme) before issuing the request.
    parsed = urlsplit(base + path_q)
    if parsed.scheme not in {"http", "https"}:
        print(f"bad URL: {parsed.geturl()}", file=sys.stderr)
        return 2

    req = urllib.request.Request(
        url=parsed.geturl(),
        data=body if body else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            sys.stdout.write(f"HTTP/{resp.status} {resp.reason}\n")
            sys.stdout.flush()
            # Stream the body to stdout. Works for both JSON responses
            # (small, single chunk) and SSE streams (line-by-line).
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        return 0
    except urllib.error.HTTPError as e:
        sys.stdout.write(f"HTTP/{e.code} {e.reason}\n")
        sys.stdout.flush()
        try:
            sys.stdout.buffer.write(e.read())
        except Exception:
            pass
        return 1


# ── Argparse wiring ──────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dev_sign.py",
        description="Local Ed25519 keypair + request signer for devauth.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="generate a keypair (writes private key)")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing private key",
    )
    p_init.set_defaults(func=cmd_init)

    p_pub = sub.add_parser("pubkey", help="print public key")
    p_pub.set_defaults(func=cmd_pubkey)

    p_sign = sub.add_parser("sign", help="print signing headers for METHOD PATH")
    p_sign.add_argument("method")
    p_sign.add_argument("path", help="path with optional ?query")
    p_sign.add_argument("--body-file", default=None, help="path to body bytes")
    p_sign.add_argument("--context", default="", help="optional user slug")
    p_sign.set_defaults(func=cmd_sign)

    p_req = sub.add_parser("request", help="sign and execute the request")
    p_req.add_argument("method")
    p_req.add_argument("path", help="path with optional ?query")
    p_req.add_argument("--base-url", default=None, help="default: $APP_URL")
    p_req.add_argument("--body-file", default=None, help="path to body bytes")
    p_req.add_argument("--context", default="", help="optional user slug")
    p_req.add_argument("--timeout", type=float, default=120.0)
    p_req.set_defaults(func=cmd_request)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
