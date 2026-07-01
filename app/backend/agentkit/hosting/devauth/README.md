# agentkit.hosting.devauth — generic Ed25519 signed-request dev auth

Domain-blind transport-layer dev-auth middleware. Verifies Ed25519-signed
requests and attaches a **consumer-built** principal to the ASGI scope. The
consumer injects an `identity_factory`, so this package never imports a domain
identity type. Lifted from GridIQ in Inc14 (the `User`-protocol seam).

## Purpose

Lets a single operator's machine bypass the primary auth path (e.g. Entra ID)
for programmatic testing **without storing any secret on the server** — the
server holds only the Ed25519 *public* key. Replaces a copyable shared-secret
header. See `hosting/fastapi/devauth/README.md` in the GridIQ consumer for the
full threat model and the production-cutover removal procedure.

## Public surface

| Symbol | Role |
|---|---|
| `install_signed_request_auth(app, *, public_key_b64, identity_factory, replay_cache=None, scope_key="devauth_user")` | Idempotent mount. No-op (returns `False`) when `public_key_b64` is empty — the ASGI stack is byte-identical to a build without the feature. |
| `SignedRequestASGIMiddleware` | The pure ASGI middleware. Constructed with `public_key_b64`, `identity_factory`, optional `replay_cache`, `scope_key`. |
| `ReplayCache(ttl_seconds=300.0)` | Per-process single-flight replay cache. `check_and_record(sig) -> bool`. |
| `verify(*, public_key_b64, method, path_and_query, ts, sig_b64, body, user_slug="") -> VerifyResult` | The pure verifier primitive (no I/O, no logging). |
| `VerifyResult(ok, user_slug="")` | Frozen dataclass — the only two bits returned. |

## The seam (why this package is domain-blind)

agentkit owns the crypto/transport: canonical-string reconstruction, Ed25519
verification, single-flight replay protection, and the bare-401 failure shape.
It does **not** know the consumer's identity type. On a verified request it
calls the **injected** `identity_factory(slug)` to materialise an opaque
principal and attaches it to `scope[scope_key]` (default `"devauth_user"`). The
consumer's primary auth dependency reads that scope key.

GridIQ's thin glue (`hosting/fastapi/devauth/_middleware.py`) injects a factory
that builds the concrete `hosting.fastapi.auth.jwt.User` from the verified slug
(`devkey-<slug>` / `__default__` oid namespace). agentkit never imports `User`.

## Wire format

```
canonical = METHOD + "\n" + path_and_query + "\n" + timestamp + "\n" + context_slug + "\n" + sha256_hex(body)
signature = Ed25519.sign(private_key, canonical)
```

Headers: `X-Request-Timestamp` (RFC 3339 UTC), `X-Request-Signature`
(base64), `X-Request-Context` (optional slug). 5-minute skew window;
`sha256(body)` + full path+query covered → tamper-evident.

## Replay protection & CHAOS-025

`ReplayCache` tracks every accepted signature until its TTL elapses and rejects
any second occurrence — single-flight replay protection. It is **per-process**:
under horizontal autoscale a signature replayed against a *different* replica is
not caught. `_middleware.py` carries a `TODO(B-CHAOS-025)` distributed-lease
seam comment marking where a shared lease (Redis SETNX / Cosmos optimistic-etag
/ signed-nonce ledger) would close cross-replica replay. Deliberately NOT solved
here — the single-replica behaviour is preserved exactly.

## Dependencies

`cryptography` (transitively present via `azure-identity`; no new dep) + stdlib.
Imports **zero** GridIQ packages (asserted by `tests/unit/test_agentkit_devauth_lift.py`
via AST + a clean-interpreter subprocess import check).

## Zero-domain assertion

No station codes, equipment ids, telemetry, or domain identity types. The
verified context slug is an opaque string; the consumer's `identity_factory`
turns it into a principal.
