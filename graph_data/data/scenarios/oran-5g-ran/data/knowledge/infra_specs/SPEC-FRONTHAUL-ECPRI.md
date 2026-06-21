# Spec: Open Fronthaul (eCPRI, Split 7.2x)

The O-RAN 7.2x fronthaul carries IQ/PRB data between DU and RU over eCPRI.
- Transport: Ethernet/eCPRI over dark fibre or WDM, 10–25 Gbps per carrier.
- Timing: requires tight sync (PTP/SyncE); clock drift degrades performance.
- Health indicators: optical RX power, CRC/FEC error rate, one-way delay.
- Failure mode: rising CRC errors reduce usable capacity → cell PRB congestion →
  RRC setup failures → slice SLA breach if a URLLC slice is carried on the cell.
