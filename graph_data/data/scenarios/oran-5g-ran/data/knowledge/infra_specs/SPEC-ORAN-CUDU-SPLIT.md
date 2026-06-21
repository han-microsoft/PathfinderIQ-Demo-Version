# Spec: O-RAN CU/DU Functional Split

The O-RAN architecture decomposes the gNB into CU, DU, and RU.
- **CU** hosts higher-layer functions (RRC, SDAP, PDCP), connects to the 5GC over N2/N3.
- **DU** hosts RLC/MAC/High-PHY; connects to CU over the F1 midhaul interface.
- **RU** hosts Low-PHY/RF; connects to DU over the open fronthaul (split 7.2x, eCPRI).
Open fronthaul enables multi-vendor RU/DU. Fronthaul faults propagate downstream as
cell-level PRB congestion and RRC setup failures.
