# Protocol: Frontend Chat Regression Loop

Standardized live testing for the vm_agent **operator UI** — the browser chat interface (a tab alternate to the CLI terminal), reused from GridIQ. Companion to [regression_protocol.md](regression_protocol.md): that protocol proves the *backend core flow*; this one proves the *operator-visible chat surface renders, streams, and persists correctly*. Run after any change to `ui/`, the chat SSE contract (`api/routers/chat.py`, `models/stream.py`, `runtime/maf/events.py`), or the session store.

**Callable as a single command.** Run autonomously when the user says: *"Run frontend regression"* / *"Test the chat UI"* / *"Does the UI still work?"*.

**Inspiration:** GridIQ's `app/frontend/e2e/` Playwright suite + `regression_loop.md` §4f panel-data discipline (per-render assertions, never trust "it rendered"). Adapted to the vm_agent chat tab.

---

## 0. Why this exists (the failure class it catches)

Backend SSE probes (`acp_chat_smoke.py`, the golden path) prove the *wire contract* — that typed `StreamEvent` frames flow. They do **not** prove an operator sees a populated, correctly-rendered chat: tokens streaming progressively, tool-call cards expanding, the message persisting, the session appearing in the list after reload. This protocol exists to catch the "SSE frames are fine but the UI shows nothing / renders raw JSON / loses the session on reload" class — the exact gap the backend probes cannot see.

**Hard rule (from GridIQ §4f):** per-render assertions, not "the page loaded." A chat that streams 200 frames but renders an empty bubble is a regression the frame-count probe passes and the operator sees as broken.

### 0a. The bypass that shipped a broken login (2026-06-07 — never again)

Image `20260607-155618` (rev `0000261`) passed this protocol 9/9 **while the real browser login was completely broken**: MSAL login failed, every `/api/chat/*` returned 401, the terminal WS would not connect. The suite was green because the Playwright fixture **bypassed auth** — it stubbed `GET /api/_authcfg` → `auth_enabled:false` and injected ed25519 dev-sign headers, so the tests rendered the chat shell directly and never once exercised the real MSAL flow. The actual production-breaker was a served CSP whose `frame-src` listed only `https://login.microsoftonline.com` and **not `'self'`**: MSAL's silent-token iframe renewal redirects back into an iframe on the *app origin*, which the CSP blocked, so silent renewal failed and no bearer was ever acquired.

**The auth path is part of the user experience under test.** Tests MUST exercise the real `/api/_authcfg` config and the real MSAL flow. Stubbing `/api/_authcfg` to `auth_enabled:false`, or injecting dev-sign headers, **as a substitute for the real login path is FORBIDDEN** — that bypass is the failure that shipped a broken login. The dev-sign fixture remains legal ONLY as a *backend-contract* harness for the render/stream/session/tool-call/workspace assertions (§3b–3e-IDE), and is explicitly **not** a substitute for the real-auth UX proof (§3a-REAL).

**Hard rule:** A green run of §3b–3e-IDE over the dev-sign fixture is NOT sign-off. Sign-off requires §3a-REAL (the real-auth-path layer) green AND the §3f manual real-browser acceptance recorded.

---

## 1. Surfaces under test

| Surface | What it is | Live proof |
| --- | --- | --- |
| IDE layout | VS Code-style `allotment` 3-pane: file tree LEFT, Monaco CENTER, Chat RIGHT, Terminal BOTTOM (replaced the old two-tab shell) | panes render + resize, persist sizes |
| SSE stream rendering | `chatApi.ts` consumes typed `StreamEvent`; tokens → `MessageBubble`, tool-calls → `ToolCallDisplay` | progressive tokens + tool-call cards |
| Compiler-card registry | `card_kind`-dispatched bespoke cards (`ui/src/components/chat/cards/`) for workflow-run / verification-gate / asset-contract / discovery / materialization / access-broker; generic card is the unknown-kind floor | `card_kind` → bespoke card; unknown → generic |
| Auth | MSAL Entra login + bearer on `/api/chat/*`; ed25519 dev-sign for headless | unauth → login gate; authed → chat works |
| Session list + resume | `GET /api/chat/sessions` populates the rail; selecting one rehydrates the transcript + tool cards via `GET /api/chat/sessions/{id}/messages`; agent recalls context across redeploy | persists + rehydrates across reload (W2) + cross-redeploy (`SESSION_RESUME_PROBE_OK`) |
| Tool-call cards | `ToolCallDisplay` renders name/args/status/result structurally (not raw JSON) | collapsible card with structured fields |
| Workspace IDE | `react-arborist` tree + editable Monaco (local bundle, no CDN) over the gated `/api/workspace/*` read+write routes | tree/open/edit/save + gated file ops (`WORKSPACE_WRITE_PROBE_OK`) |
| Terminal coexistence | The xterm `/terminal` WS panel still works as the bottom pane | terminal functional alongside chat/editor |

---

## 2. Pre-flight

```bash
cd /home/hanchoong/CURRENT270425/vm_agent
set -a && source .env && set +a
export VMAGENT_URL  # the live FQDN
export VMAGENT_FE_NONCE="VMAGENT_FE_$(date -u +%Y%m%d_%H%M%S)"
# UI build must be current in the deployed image (Vite build baked in)
curl -sS "${VMAGENT_URL%/}/healthz" | python3 -c 'import sys,json;d=json.load(sys.stdin);print("ok",d["ok"],"image",d["image_sha"])'
```

Two test modes (run both when shipping a UI change):
- **Local preview** — `cd ui && npm run build && npm run preview` against a signed/dev-auth backend (fast iteration, catches render bugs without a deploy).
- **Live** — Playwright against the deployed `pathfinderiq-aemo` FQDN (the real proof; auth, SSE, persistence end-to-end).

---

## 3. Test layers (atomic, one assertion group per step)

Tests live under `ui/e2e/*.spec.ts` (Playwright), modeled on GridIQ's `app/frontend/e2e/`. The §3b–3e-IDE render/stream/session/workspace layers run over the **dev-sign backend-contract fixture** (`e2e/_fixtures.ts`) — labeled as such, NOT a UX proof. The §3a-REAL layer runs over the **raw page with NO bypass**.

### 3a. Build + type gate (cheapest, always first)
```bash
cd ui && npm run build    # tsc + vite build — type errors fail here
npm run test              # vitest unit (component render, SSE parse)
```
- `tsc` MUST pass — the typed `StreamEvent` contract is shared frontend↔backend; a type drift fails the build. This is the compile-time teeth of W1.

### 3a-REAL. Real-auth path (NO bypass — the layer that catches a broken login)

This layer exercises the actual operator login surface with **no `/api/_authcfg` stub and no dev-sign injection**. It is mandatory for sign-off. Two parts: an automatable static layer (\u00a73a-REAL-auto) and a required manual layer (\u00a73f).

**Browserless probe (cheapest, run first, the regression that was missing):**
```bash
python3 scripts/frontend_auth_probe.py --url "$VMAGENT_URL" --nonce "$VMAGENT_FE_NONCE"
# → FRONTEND_AUTH_PROBE_OK <nonce>
```
Plus the equivalent Playwright spec `e2e/00-real-auth.spec.ts` (raw `page`, never `authedPage`):

| # | Assertion | Why |
| --- | --- | --- |
| R1 | The served `Content-Security-Policy` HTTP header has `frame-src` containing BOTH `'self'` **and** `https://login.microsoftonline.com`, and `connect-src` containing `wss:` **and** the login origin. | `frame-src` missing `'self'` is the exact shipped production-breaker — MSAL silent-iframe renewal redirects to the app origin in an iframe and is blocked. A static header assertion, no browser needed. |
| R2 | `GET /api/_authcfg` returns the REAL config: `auth_enabled:true`, non-empty `client_id` / `tenant_id` / `authority` (a `login.microsoftonline.com` URL) / scope. | The forbidden bypass stubbed this to `false`. Asserting the real value makes the bypass impossible to pass off as a UX proof. |
| R3 | The login screen renders against the real config; clicking **Sign in with Microsoft** initiates an MSAL authorize **TOP-LEVEL REDIRECT** (`loginRedirect`, not a popup — popups are blocked in the deploy host) to `login.microsoftonline.com/.../oauth2/v2.0/authorize` with `client_id` = the real client_id and `redirect_uri` = the app origin (FQDN). | Closest automatable proxy for interactive login. Headless Entra credential entry is NOT automatable (see §3f). |
| R4 | Unauthenticated `GET /api/chat/sessions` → **401** (the gate is never weakened; we fix token acquisition, not remove auth). | Guards against a "fix" that disables auth. |
| R5 | The INTERACTIVE auth path is **redirect-based + single-flight + loop-broken** (structural, `ui/tests/authGuard.test.ts` + grep): (a) the token path has ZERO `acquireTokenPopup`/`loginPopup`/`logoutPopup` CALL-sites in `ui/src/` (popups blocked → redirect-only); (b) ALL interactive escalation — silent-fail in `useAuth.acquire()`, the `client.ts` 401 handler, and the explicit Sign-in — funnels through ONE `requestInteractiveAuth` guard (module in-flight flag + `sessionStorage['vmagent.auth.redirecting']` marker) so concurrent callers collapse onto one `loginRedirect` (no `interaction_in_progress`); (c) `initAuth` awaits `handleRedirectPromise()` before render; (d) a post-redirect attempt that STILL fails latches the loop-breaker and renders a `<LoginScreen loopBroken>` instead of re-redirecting. | This is the AADSTS160021 login-loop class (2026-06-08). Popup-fallback + ungated per-caller 401→redirect + no `handleRedirectPromise` looped forever when the AAD session expired. Real MSAL is NOT exercised by the dev-sign e2e, so this is the structural teeth that stop a regression; the human §3f step proves the live outcome. |

**Hard rule:** R1–R5 must pass against the LIVE deployed FQDN (R5's structural legs run locally over `ui/`). They run with the real `/api/_authcfg`; any test that stubs it to `auth_enabled:false` is rejected at review.

### 3b. Chat render smoke (Playwright, live or preview — dev-sign BACKEND-CONTRACT fixture)

> These assertions run over `e2e/_fixtures.ts` (dev-sign). They prove the **backend contract + render pipeline**, NOT the real-auth UX. \u00a73a-REAL is the auth-UX proof; this layer assumes a valid principal and tests what renders given one.
| # | Assertion |
| --- | --- |
| 1 | App loads; MSAL login card renders when unauthed; authed (or dev-sign fixture) lands on the chat tab. |
| 2 | The Chat pane, the Monaco editor pane, the file-tree pane and the Terminal pane all coexist in the `allotment` layout; resizing a sash does not blank a neighbor. |
| 3 | Send a prompt → a user `MessageBubble` appears immediately; an assistant bubble begins streaming. |
| 4 | Tokens render **progressively** (assert the assistant bubble text grows across ≥2 polled snapshots — not one final dump). This is the streaming-render proof; a batched render is a regression. |
| 5 | `done` event → the assistant bubble finalizes; `StreamingIndicator` clears. |

### 3c. Tool-call rendering (the distinctive part)
| # | Assertion |
| --- | --- |
| 6 | A prompt that drives a tool call → a `ToolCallDisplay` card appears with the tool name (not raw JSON). |
| 7 | The card shows structured fields (args + status pending→done + result), collapsible. Assert the result is NOT a raw JSON string dump in a text bubble. |
| 8 | A compiler-flow tool result carrying a stable `card_kind` (one of `workflow_run` / `verification_gate` / `asset_contract` / `discovery` / `materialization` / `access_broker`) resolves through the **card registry** (`ui/src/components/chat/cards/`) to its bespoke card — NOT the generic card, NOT unparsed text. Assert a card-specific field renders (e.g. verification pass/fail, contract `asset_id` + location). |
| 8b | **Unknown-kind fallback (regression guard):** a tool result with no/unrecognized `card_kind` falls through to the generic `ToolCallDisplay` and does NOT throw or blank the transcript. (This is the registry's floor — adding a card must never break unknown kinds; authored per [renderer_protocol.md](renderer_protocol.md).) |

### 3d. Session persistence + resume (W2 + durable-resume — the durability proof)
| # | Assertion |
| --- | --- |
| 9 | After a completed turn, the session appears in the session rail (`GET /api/chat/sessions`). |
| 10 | **Reload the page** → the session is STILL listed; selecting it fetches `GET /api/chat/sessions/{id}/messages` and **rehydrates the full transcript** — user + assistant text AND prior tool-call/compiler cards re-render from history (not a blank shell). (W2 keystone + the 2026-06-08 thread-history GET; pre-fix, selecting a session reset the transcript to blank.) |
| 11 | A second browser context / fresh load, same user, sees the same session (durable, not per-tab memory). |
| 11b | **Ownership scope:** `GET /api/chat/sessions/{id}/messages` for a session the caller does not own → `404` (no existence leak), unauth → `401`. (Live ownership-deny is unit-covered — dev-sign collapses callers to one principal — so this row is asserted via `tests/test_session_resume.py`, not the browser.) |
| 11c | **Cross-redeploy resume (signed probe, not browser):** `SESSION_RESUME_PROBE_OK` — a fact told pre-redeploy is recalled post-`--mode full` redeploy without restating it. Backend agent-context-reseed proof; cite the marker in the report when a chat/session change ships. |

### 3e. Error + auth edges

### 3e-IDE. Workspace IDE surface (VS Code-style layout — file tree + editable Monaco + terminal)

> The UI is a 3-pane `allotment` IDE (tree LEFT, Monaco CENTER, Chat RIGHT, Terminal BOTTOM), not the old two-tab shell. These run over the dev-sign backend-contract fixture (backend contract, not real-auth UX).

| # | Assertion |
| --- | --- |
| 15 | The file tree (`react-arborist`) renders from `GET /api/workspace/tree`; a dir node lazy-expands its children; a file node opens in a read-only-or-editable Monaco tab via `GET /api/workspace/file`. |
| 16 | Monaco loads from the **local bundle** (no jsDelivr/CDN request — assert no network call to `cdn.jsdelivr.net`); the editor chunk is lazy (not in the entry bundle). |
| 17 | Editing a file sets the per-tab dirty dot; `Ctrl/Cmd-S` (or Save) fires `PUT /api/workspace/file` and clears dirty. |
| 18 | Tree context-menu ops fire the gated routes: New File/Folder (`POST /api/workspace/file|dir`), Rename (`POST /api/workspace/rename`), Delete (`DELETE /api/workspace/path`); a protected-path target (`/sandbox/.vmagent/**`) surfaces the `403 protected_path` toast, not a crash. (Backend gate proven by `WORKSPACE_WRITE_PROBE_OK`: escape→`400`, protected→`403`, unauth→`401`.) |

### 3f. Manual real-browser acceptance (REQUIRED for sign-off — not automatable headlessly)

Headless MSAL interactive login (Entra credential entry, MFA) cannot be driven in CI. The automatable §3a-REAL proves the *machinery* (CSP, config, redirect initiation); a human must prove the *outcome*. This step is **required** and its result **recorded** in the final report.

Operator steps:
1. Open the live FQDN in a real browser (not the e2e harness).
2. Click **Sign in with Microsoft**; complete the Entra login (real credentials/MFA).
3. Confirm ALL of:
   - login completes and the chat shell renders (no login loop, no CSP error in console);
   - `POST /api/chat/sessions` returns **200** (not 401) — check the Network tab;
   - `GET /api/chat/sessions` returns 200 and lists the session;
   - send a prompt → assistant tokens stream;
   - switch to the terminal tab → the WS connects (`wss://<fqdn>/terminal`, status "terminal connected"), a shell command echoes.
4. Record PASS/FAIL + the observed `/api/chat/sessions` status in the final report.

A green §3a-REAL with a FAIL here is NOT sign-off.

---

## 4. Pass criteria

- Build + `tsc` + vitest green (3a).
- **§3a-REAL green** (R1–R4 + `FRONTEND_AUTH_PROBE_OK`) against the live FQDN — the real-auth-path proof. A run without it is NOT sign-off, regardless of §3b–3e.
- **§3f manual real-browser acceptance recorded PASS** — login succeeds, `/api/chat/sessions` 200, terminal WS connects.
- Every dev-sign backend-contract assertion (1–14) passes against the **live** deployed app (preview-only is iteration, not sign-off). These prove render/stream/persistence given a valid principal — NOT the auth UX.
- **Progressive streaming proven** (assertion 4) — the load-bearing render proof; a green run without it is not a pass.
- **Session survives reload** (assertion 10) — the W2 keystone.
- Tool-calls render structurally (6–8), not as raw JSON.
- The CLI terminal tab still works (assertion 2) — the UI is *additive*, it does not break the existing terminal.
- No screenshots/traces retained beyond pass/fail + timing (mirror GridIQ §3 ops-data hygiene — though vm_agent's sandbox is synthetic, keep the discipline).

---

## 5. Final report

| layer | ok / total | notes |
| --- | --- | --- |
| build + tsc + vitest | n/n | type contract intact |
| real-auth path (§3a-REAL) | 4/4 + probe | CSP frame-src 'self' OK, real authcfg, authorize redirect OK, unauth 401 |
| manual real-browser acceptance (§3f) | PASS/FAIL | login OK, /api/chat/sessions 200, terminal WS connects |
| chat render smoke (dev-sign) | 5/5 | progressive streaming proven |
| tool-call rendering (dev-sign) | 3/3 | structural, not raw JSON |
| session persistence (dev-sign) | 3/3 | survives reload (W2) |
| error + auth edges (dev-sign) | 3/3 | |
| terminal coexistence | 1/1 | CLI tab unaffected |

Include: image sha + revision, UI build hash, nonce, wall-clock, any failed assertion, and the deployed FQDN tested.

Completion line:
```text
vmagent_frontend_regression PASS -- image <sha>, revision <rev>, ui <build-hash>, nonce <nonce>, progressive-stream OK, session-reload OK, terminal-coexist OK, wall <Xm>
```

---

## 6. Fix-forward loop

- Any failed assertion → STOP, diagnose (frontend render bug vs backend contract bug — the typed `StreamEvent` boundary tells you which side), fix, rebuild/redeploy, rerun from 3a.
- A type error in 3a is a CONTRACT drift between `models/stream.py` and the frontend `types.ts` — fix the contract, not the test.
- Max 3 iterations before reporting a structural blocker.

---

## 7. Hard rules

- **Auth is part of the UX under test — NEVER bypass it for sign-off.** Stubbing `/api/_authcfg` to `auth_enabled:false` or injecting dev-sign headers as a substitute for the real login path is FORBIDDEN; that bypass shipped a broken login (§0a). Dev-sign is legal ONLY as the backend-contract harness for §3b–3e, explicitly not a UX proof.
- **§3a-REAL (R1–R4 + `FRONTEND_AUTH_PROBE_OK`) is mandatory** — the served CSP header must allow MSAL framing (`frame-src 'self' https://login.microsoftonline.com`) and `wss:` connect; the real `/api/_authcfg` must be `auth_enabled:true`; the login must initiate the authorize redirect with the right `client_id`/`redirect_uri`; unauth must still 401.
- **§3f manual real-browser acceptance is required and recorded** — a green automatable layer with no human login proof is not sign-off.
- **Never trust "it streamed" — assert progressive render (4) and structural tool-cards (7).** Frame-count alone is a backend metric; the operator sees pixels.
- **Never sign off without the session-reload proof (10).** In-memory sessions pass everything else and fail the one thing a UI needs.
- **The chat tab is additive — never let a UI change break the CLI terminal tab (2).**
- **Live proof for sign-off.** Preview-mode is iteration; the deployed FQDN is the acceptance surface.
- **Run after any change to:** `ui/`, the served CSP (`api/static.py`), the auth bootstrap (`ui/src/auth/*`, `api/auth_config.py`), `api/routers/chat.py`, `models/stream.py`, `runtime/maf/events.py`, the session store, or `api/streaming.py`.
