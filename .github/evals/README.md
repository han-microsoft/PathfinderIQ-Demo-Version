# evals — live UX-flow evaluations

The standardized evaluations module. Each **flow** mirrors one expected user UX
journey on the live deploy (PROJECT.md §1). Run the whole suite for full
regression, or a named flow / tag subset for fast iteration. This is the runnable
form of regression_protocol.md §4 — capability rows become executable journeys.

Stack: Python/Azure. HTTP via stdlib `urllib` (zero-dep). Synthetic, nonce-owned
data only; cleanup always runs.

## Run

```sh
python3 .github/evals/eval.py list                 # flows + tags
python3 .github/evals/eval.py run                   # whole suite (all flows)
python3 .github/evals/eval.py run authed_crud_journey   # one named flow
python3 .github/evals/eval.py run --tag smoke       # tag subset
python3 .github/evals/eval.py run --target https://staging.example.com   # override target
python3 .github/evals/selftest.py                   # prove the runner (no deploy)
```

Target defaults to `LIVE_TARGET` (PROJECT.md §0). Exit: 0 all pass / 1 any flow
failed / 2 usage or no flows. One metric row per flow appended to
`<FINDINGS_DIR>/evidence/evals.jsonl` (P7).

## Files

| File | Role |
| --- | --- |
| [eval.py](eval.py) | Front door: discover, list, run (whole/selective), record. |
| [flow.py](flow.py) | The flow contract: `Flow`, `Step`, `EvalContext`, `run_flow`. |
| [flows/](flows/) | Flow definitions — one file per area, module-level `FLOWS`. |
| [flows/example_health.py](flows/example_health.py) | Reference flow ("what good looks like"). |
| [selftest.py](selftest.py) | Self-proof: fake service + runner + forced negative path. |

## Authoring a flow

A flow is a named, tagged user-journey. Drop a `.py` in `flows/` exposing a
module-level `FLOWS: list[Flow]`:

```python
from flow import EvalContext, Flow, Step

def _login(ctx: EvalContext) -> str:
    status, body = ctx.post("/auth/login", body={"user": ctx.nonce})
    ctx.expect(status == 200, f"login {status}, want 200")   # falsifiable
    ctx.store["token"] = ...                                  # pass data downstream
    return "logged in"

def _cleanup(ctx: EvalContext) -> None:
    ...   # delete anything ctx.track()'d — runs pass OR fail

FLOWS = [
    Flow(
        name="onboarding",
        description="signup -> verify -> first action",
        tags=("smoke", "onboarding"),
        steps=[Step("login", _login), ...],
        cleanup=_cleanup,
    ),
]
```

Rules (enforced by doctrine, mirrored by `selftest.py`):

- **Every step has a falsifiable assertion** via `ctx.expect(...)`. A flow that
  cannot fail is broken (P7).
- **Steps are gated** — the first failure stops the chain; the digest names the
  step that broke. No hiding a regression inside one opaque loop.
- **Synthetic + nonce-owned** — write only data carrying `ctx.nonce`; register it
  with `ctx.track(kind, id)`; delete it in `cleanup`. Never mutate data the run
  did not create (Ownership And Deletion Law, regression_protocol.md).
- **Mirror a real journey** — a flow is a user path (signup, checkout, query),
  not a single unit assertion. That is the point of the module.

## Seed vs project

Seed ships the **runner + contract + one reference flow**. The project supplies
its **real journeys** in `flows/` — instance data, same principles-vs-instance
split as PROJECT.md. `cartographer` does not own these; `verifier` builds and
maintains them (verifier.agent.md), bound into regression as the selectable
battery.
