# Spec: 3GPP Network Slice Types (S-NSSAI / SST)

A slice is identified by S-NSSAI (SST + optional SD).
- **eMBB (SST 1):** high throughput, latency-tolerant (10–25 ms). Consumer/video.
- **URLLC (SST 2):** ultra-reliable low-latency (≤ 5 ms typical). Industrial, grid, robotics.
- **mMTC (SST 3):** massive IoT, latency-tolerant (≥ 100 ms), low throughput.
Each slice maps to an SLAPolicy (latency floor, throughput floor, penalty, tier).
URLLC GOLD tiers carry the highest penalty exposure on breach.
