# Spec: O-RAN / 3GPP KPM Counter Reference

Key Performance Measurement counters used in this scenario:
- **PRBUtilPct** — physical resource block utilisation; > 90% indicates congestion.
- **RRCSuccessPct** — RRC connection setup success; < 95% indicates admission failures.
- **DLThroughputMbps** — cell downlink throughput.
- **LatencyMs (slice)** — slice user-plane latency; compare to SLA floor.
- **CQI / BLERPct (UE)** — channel quality and block error rate; CQI < 6 or BLER > 10% is poor.
KPMs are reported by the E2 nodes (DU/CU) and collected per cell/slice/UE.
