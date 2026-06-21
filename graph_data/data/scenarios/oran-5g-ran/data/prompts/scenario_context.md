# Scenario — O-RAN 5G RAN (Simulated)

**Entity types:** CoreNetwork, gNB, CU, DU, Cell, Slice, SLAPolicy, UE, TransportLink.

**Hierarchy:** CoreNetwork ← gNB `hosts` CU/DU → CU `controls` DU → DU `serves` Cell → Cell `carries` Slice; UE `attached_to` Cell and `uses` Slice; Slice `governed_by` SLAPolicy; TransportLink (fronthaul eCPRI / midhaul F1 / backhaul N3) connects elements via `link_source`/`link_target`.

**Live incident:** a fronthaul (eCPRI) degradation under **DU-MEL-01-2** (gNB-MEL-01, Melbourne) is congesting its cells (PRB > 90%), causing RRC setup failures, and breaching the **SL-URLLC-01** slice SLA (5 ms latency floor, tenant SmartGridCo).

**Flow:** Parse alarms → trace topology (gNB→CU→DU→Cell→Slice) → correlate KPMs → root cause → slice/tenant blast radius + SLA penalty → report.

You MUST call your tools for evidence. Do not answer from memory.
