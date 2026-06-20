# Skill: Fault Triage

When an incident arrives, establish the failure class and confidence before
acting.

## Steps
1. Pull the most recent CRITICAL/MAJOR alerts for the named entity
   (`query_alerts`); note `AlertType` and `Timestamp`.
2. Confirm with telemetry (`query_telemetry`): a real outage shows
   OpticalPower ≈ -35 dBm, BER ≈ 1.0, Latency ≈ 9999 ms, Utilization ≈ 0%.
3. Classify: FIBRE_CUT (optical + BER), HIGH_LATENCY (latency only),
   BGP_PEER_DOWN (routing), CAPACITY_EXCEEDED (utilization).
4. State confidence + one open question.

## Tags
triage, incident, classification, alerts, telemetry
