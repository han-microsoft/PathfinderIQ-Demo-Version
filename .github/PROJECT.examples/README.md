# PROJECT.examples — filled binding manifests

Copy the closest example over [../PROJECT.md](../PROJECT.md) when seeding a new
project, then adjust. Each fills the `## 0. Bindings` block + the prose tables
for a real project shape. Run `project.py seed` after to confirm readiness.

| Example | Shape |
| --- | --- |
| [python_service.md](python_service.md) | FastAPI/Python backend, Docker + Azure deploy, pytest gate |
| [typescript_frontend.md](typescript_frontend.md) | React/Vite SPA, tsc + vitest gate, static deploy |
| [cli_tool.md](cli_tool.md) | Python CLI, prototype tier, no deploy surface |

These show only the binding-relevant sections. The full PROJECT.md template
(with all prose guidance) stays at [../PROJECT.md](../PROJECT.md); copy the
`## 0. Bindings` block + §1–§8 values from the matching example into it.
