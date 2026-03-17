# Tool: query_graph

Query topology: infrastructure, sensors, GPS, depots, duty rosters.

## Rules
- Entity IDs are UPPERCASE with hyphens: `CORE-SYD-01`, `LINK-SYD-MEL-FIBRE-01`
- One query per call. Multiple queries = multiple calls.
- Query error → read message, fix syntax, retry once.
- Ask for ALL affected entities when tracing blast radius.
