# agentkit.dev_tools

Headless developer/CI tooling for exercising a deployed agentkit app. Zero consumer (domain) imports.

## Purpose
- `dev_sign` — a local Ed25519 keypair manager + signed-request CLI for the devauth side-channel (no server secrets; only the public key is transmitted).
- `sse_contract_probe` — a headless SSE event-sequence contract tester that drives a live app and asserts the wire contract.

## Public API
Both modules expose a `main(argv)` entrypoint — run as `python3 -m agentkit.dev_tools.<tool>`.

### `agentkit.dev_tools.dev_sign`
| Subcommand | Does |
|---|---|
| `init` | generate a keypair (`~/.gridiq/dev_signing_key`, mode `0600`); print `DEV_PUBLIC_KEY_ED25519=<base64>`; refuses overwrite without `--force` |
| `pubkey` | print the public key for the existing private key |
| `sign` | `METHOD PATH [--body-file F] [--context SLUG]` → the three signing header values |
| `request` | sign **and** execute against `--base-url` (default `APP_URL` env); streams stdout; non-zero on non-2xx |

Canonical string: `METHOD\npath\nts\nSLUG\nbody_sha` (microsecond ts), with the slug also in the `X-Request-Context` header. Byte-identical to the server-side devauth verifier — both sides must stay in lockstep.

### `agentkit.dev_tools.sse_contract_probe`
Drives one chat round-trip and asserts: exactly one terminal frame (`DONE|ERROR|ABORTED`), no frame after the terminal, every `TOOL_CALL_END.id` has a prior `TOOL_CALL_START.id`, `METADATA` precedes `DONE`, no frame exceeds the byte cap. Legal vocabulary = `known_event_names()` (generic ∪ whatever the consumer registered via `register_domain_events` before calling `main`). Exit `0` pass / `1` fail / `2` could-not-run.

## Dependencies
- Within agentkit: `agentkit.hosting` (probe uses `known_event_names`).
- External: `cryptography` (Ed25519), `httpx`. No pip extra declared specifically; both are present in the GridIQ base env.

## Injection seams
- The probe's vocabulary is injected by the consumer: register domain events before calling `main`. The agentkit module itself only knows the generic vocabulary.

## Extend recipe
- **Ship a thin CLI** → a consumer keeps `scripts/<tool>.py` as a 3-line entrypoint that (for the probe) imports its `domain_events` module to register vocabulary, then calls `agentkit.dev_tools.<tool>.main(sys.argv[1:])`. The entrypoint is **not** a shim — it's the CLI surface.

## Gotchas
- The private key never leaves the operator machine; only the public key is pushed to the app. After every full deploy (which strips the key), re-push `DEV_PUBLIC_KEY_ED25519`.
- Tests patch `agentkit.dev_tools.dev_sign._KEY_DIR` / `_KEY_FILE`.
- The probe predates the context-slug requirement historically — signing with an empty context yields a 403; always pass `--context`.

## Zero-domain assertion
Imports `agentkit.hosting` / `cryptography` / stdlib only — zero consumer imports. Domain SSE vocabulary is registered by the consumer's entrypoint, not here.
