# PathfinderIQ eval — O-RAN battery

- scenario: `oran-5g-ran`  agent: `networkInvestigator`  runs/case: 1
- cases: 7

| case | class | sev | split | verdict | G1 | G2 | G3 | tools | over |
|---|---|---|---|---|---|---|---|---|---|
| backhaul-n3-flap | backhaul_flap | serious | held_out | **pass** | 1/1 | 3/3 | 1/1 | 11 |  |
| benign-clock-drift | none | benign | train | **pass** | 1/1 | 2/2 | 1/1 | 11 |  |
| demand-congestion-no-fault | demand_congestion | serious | train | **pass** | 1/1 | 3/3 | 1/1 | 10 |  |
| fronthaul-urllc-breach | fronthaul_degradation | critical | train | **pass** | 2/2 | 5/5 | 2/2 | 8 |  |
| midhaul-f1-congestion | midhaul_congestion | serious | train | **pass** | 1/1 | 3/3 | 1/1 | 10 |  |
| mmtc-signaling-storm | signaling_storm | major | held_out | **pass** | 2/2 | 3/3 | 1/1 | 8 |  |
| pci-collision-rrc | pci_collision | major | held_out | **pass** | 2/2 | 3/3 | 1/1 | 12 |  |

**Pass rate:** 7/7  ·  held-out: 3/3

Gate-1 detection + Gate-2 investigation are scored from the agent's answer (observable-token coverage, negation-aware over-reach check). Gate-3 is a lighter recommendation signal; full Gate-3 synthesis is best seen via the `orchestrator` agent.
