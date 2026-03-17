#!/usr/bin/env python3
"""Generate all three telemetry CSVs: SensorReadings, LinkTelemetry, AlertStream.

Architecture: baseline generators + event injectors.
  - Baseline generators produce days of normal-looking data.
  - Event injectors splice incident signatures at a given timestamp.

Usage: python3 scripts/generate_telemetry.py
  (run from the scenario root directory)

Output:
  data/telemetry/SensorReadings.csv
  data/telemetry/LinkTelemetry.csv
  data/telemetry/AlertStream.csv
"""

from __future__ import annotations

import csv
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── Config ──────────────────────────────────────────────────────────────────

SCENARIO_ROOT = Path(__file__).resolve().parent.parent
ENTITY_DIR = SCENARIO_ROOT / "data" / "entities"
OUTPUT_DIR = SCENARIO_ROOT / "data" / "telemetry"

OBSERVATION_START = datetime(2026, 2, 4, 0, 0, 0, tzinfo=timezone.utc)
OBSERVATION_END = datetime(2026, 2, 6, 23, 59, 59, tzinfo=timezone.utc)
INCIDENT_TIME = datetime(2026, 2, 6, 14, 31, 14, tzinfo=timezone.utc)

INTERVAL_MIN = 5  # baseline reading interval in minutes
SEED = 42

# ── Sensor baseline profiles ───────────────────────────────────────────────
# Keyed by SensorId. Each defines: mean, sigma, unit.
# Sensors not listed here use a default based on SensorType.

SENSOR_DEFAULTS = {
    "OpticalPower": {"mean": -10.5, "sigma": 0.5, "unit": "dBm"},
    "BitErrorRate": {"mean": 2.5e-12, "sigma": 1.5e-12, "unit": "ratio"},
    "Temperature": {"mean": 32.0, "sigma": 3.0, "unit": "°C"},
    "CPULoad": {"mean": 35.0, "sigma": 10.0, "unit": "%"},
}

SENSOR_OVERRIDES = {
    "SENS-SYD-MEL-F1-OPT-001": {"mean": -10.2, "sigma": 0.5},
    "SENS-SYD-MEL-F1-OPT-002": {"mean": -11.8, "sigma": 0.5},
    "SENS-SYD-MEL-F1-OPT-003": {"mean": -10.9, "sigma": 0.5},
    "SENS-SYD-MEL-F1-BER-001": {"mean": 2.0e-12, "sigma": 1.0e-12},
    "SENS-SYD-MEL-F1-BER-002": {"mean": 3.0e-12, "sigma": 1.5e-12},
    "SENS-SYD-MEL-F2-OPT-001": {"mean": -10.5, "sigma": 0.5},
    "SENS-SYD-MEL-F2-OPT-002": {"mean": -11.0, "sigma": 0.5},
    "SENS-CORE-SYD-01-CPU-001": {"mean": 35.0, "sigma": 10.0},
    "SENS-CORE-MEL-01-CPU-001": {"mean": 33.0, "sigma": 10.0},
    "SENS-CORE-BNE-01-TEMP-001": {"mean": 34.0, "sigma": 3.0},
}

# ── Link baseline profiles ─────────────────────────────────────────────────

LINK_PROFILES = {
    "LINK-SYD-MEL-FIBRE-01": {"util": (50, 8), "opt": (-2.8, 0.5), "ber": (3e-12, 2e-12), "lat": (6, 2)},
    "LINK-SYD-MEL-FIBRE-02": {"util": (25, 5), "opt": (-3.0, 0.4), "ber": (4e-12, 2e-12), "lat": (7, 2)},
    "LINK-SYD-BNE-FIBRE-01": {"util": (40, 6), "opt": (-2.5, 0.4), "ber": (2e-12, 1e-12), "lat": (12, 3)},
    "LINK-MEL-BNE-FIBRE-01": {"util": (35, 6), "opt": (-2.7, 0.4), "ber": (3e-12, 2e-12), "lat": (14, 3)},
    "LINK-SYD-AGG-NORTH-01": {"util": (30, 5), "opt": (-1.5, 0.3), "ber": (1e-12, 0.5e-12), "lat": (1, 0.5)},
    "LINK-SYD-AGG-SOUTH-01": {"util": (28, 5), "opt": (-1.6, 0.3), "ber": (1e-12, 0.5e-12), "lat": (1, 0.5)},
    "LINK-MEL-AGG-EAST-01": {"util": (32, 5), "opt": (-1.4, 0.3), "ber": (2e-12, 1e-12), "lat": (1, 0.5)},
    "LINK-MEL-AGG-WEST-01": {"util": (27, 5), "opt": (-1.5, 0.3), "ber": (1e-12, 0.5e-12), "lat": (1, 0.5)},
    "LINK-BNE-AGG-CENTRAL-01": {"util": (22, 4), "opt": (-1.3, 0.3), "ber": (1e-12, 0.5e-12), "lat": (1, 0.5)},
    "LINK-BNE-AGG-SOUTH-01": {"util": (20, 4), "opt": (-1.4, 0.3), "ber": (1e-12, 0.5e-12), "lat": (1, 0.5)},
}

# ── Alert storm specification ──────────────────────────────────────────────

FIBRE_CUT_STORM = [
    {"source": "MOB-5G-MEL-3011", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 77},
    {"source": "MOB-5G-SYD-2042", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 124},
    {"source": "VPN-ACME-CORP", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 133},
    {"source": "VPN-BIGBANK", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 161},
    {"source": "MOB-5G-SYD-2041", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 185},
    {"source": "MOB-5G-MEL-3011", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 222},
    {"source": "VPN-ACME-CORP", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 259},
    {"source": "BB-BUNDLE-SYD-NORTH", "type": "SERVICE_DEGRADATION", "sev": "MAJOR", "desc": "Customer broadband degraded — upstream path impacted", "ts_offset_ms": 289},
    {"source": "BB-BUNDLE-MEL-EAST", "type": "SERVICE_DEGRADATION", "sev": "MAJOR", "desc": "Customer broadband degraded — upstream path impacted", "ts_offset_ms": 518},
    {"source": "MOB-5G-MEL-3011", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 551},
    {"source": "MOB-5G-SYD-2042", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 558},
    {"source": "MOB-5G-SYD-2041", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 565},
    {"source": "VPN-ACME-CORP", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 657},
    {"source": "VPN-BIGBANK", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 704},
    {"source": "BB-BUNDLE-MEL-EAST", "type": "SERVICE_DEGRADATION", "sev": "MAJOR", "desc": "Customer broadband degraded — upstream path impacted", "ts_offset_ms": 808},
    {"source": "VPN-BIGBANK", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 847},
    {"source": "MOB-5G-SYD-2041", "type": "SERVICE_DEGRADATION", "sev": "WARNING", "desc": "Backhaul degradation — voice quality MOS below threshold", "ts_offset_ms": 847},
    {"source": "BB-BUNDLE-MEL-EAST", "type": "SERVICE_DEGRADATION", "sev": "MAJOR", "desc": "Customer broadband degraded — upstream path impacted", "ts_offset_ms": 902},
    {"source": "VPN-ACME-CORP", "type": "SERVICE_DEGRADATION", "sev": "CRITICAL", "desc": "VPN tunnel unreachable — primary MPLS path down", "ts_offset_ms": 968},
    {"source": "BB-BUNDLE-MEL-EAST", "type": "SERVICE_DEGRADATION", "sev": "MAJOR", "desc": "Customer broadband degraded — upstream path impacted", "ts_offset_ms": 986},
]

# Secondary alerts after the storm (symptoms, not root causes)
SECONDARY_ALERTS = [
    {"source": "LINK-SYD-MEL-FIBRE-01", "stype": "TransportLink", "type": "FIBRE_CUT", "sev": "CRITICAL", "desc": "Loss of light — total signal failure on DWDM trunk", "delay_s": 1},
    {"source": "BGP-SYD-MEL-01", "stype": "BGPSession", "type": "BGP_PEER_DOWN", "sev": "CRITICAL", "desc": "BGP peer unreachable — adjacency lost after link failure", "delay_s": 3},
    {"source": "CORE-SYD-01", "stype": "CoreRouter", "type": "HIGH_CPU", "sev": "MAJOR", "desc": "CPU utilisation spike — routing table reconvergence in progress", "delay_s": 5},
    {"source": "CORE-MEL-01", "stype": "CoreRouter", "type": "HIGH_CPU", "sev": "MAJOR", "desc": "CPU utilisation spike — routing table reconvergence in progress", "delay_s": 5},
    {"source": "LINK-SYD-MEL-FIBRE-01", "stype": "TransportLink", "type": "HIGH_BER", "sev": "CRITICAL", "desc": "Bit error rate at maximum — total link failure", "delay_s": 1},
]

# ── Noise alert distribution ────────────────────────────────────────────────

NOISE_SOURCES = [
    ("LINK-SYD-MEL-FIBRE-01", "TransportLink"),
    ("LINK-SYD-MEL-FIBRE-02", "TransportLink"),
    ("LINK-SYD-BNE-FIBRE-01", "TransportLink"),
    ("LINK-MEL-BNE-FIBRE-01", "TransportLink"),
    ("LINK-SYD-AGG-NORTH-01", "TransportLink"),
    ("LINK-SYD-AGG-SOUTH-01", "TransportLink"),
    ("LINK-MEL-AGG-EAST-01", "TransportLink"),
    ("LINK-MEL-AGG-WEST-01", "TransportLink"),
    ("LINK-BNE-AGG-CENTRAL-01", "TransportLink"),
    ("LINK-BNE-AGG-SOUTH-01", "TransportLink"),
    ("GNB-SYD-2041", "BaseStation"),
    ("GNB-SYD-2042", "BaseStation"),
    ("GNB-SYD-2043", "BaseStation"),
    ("GNB-MEL-3011", "BaseStation"),
    ("GNB-MEL-3012", "BaseStation"),
    ("GNB-MEL-3021", "BaseStation"),
    ("GNB-BNE-4011", "BaseStation"),
    ("GNB-BNE-4012", "BaseStation"),
]

NOISE_TYPES = [
    ("DUPLICATE_ALERT", "MINOR", "Periodic keepalive timeout — auto-recovered"),
    ("PACKET_LOSS_THRESHOLD", "MINOR", "Packet loss {pct:.2f}% — transient microloop"),
    ("HIGH_CPU", "MINOR", "CPU utilisation {pct:.1f}% — brief convergence spike"),
    ("DUPLICATE_ALERT", "MINOR", "Duplicate alarm suppressed — flapping interface"),
]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _ts(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with milliseconds and Z suffix."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _ts_sec(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with seconds and Z suffix (no millis)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def _alert_id(dt: datetime) -> str:
    """Generate an alert ID in the format ALT-YYYYMMDD-NNNNNN."""
    return f"ALT-{dt.strftime('%Y%m%d')}-{random.randint(0, 999999):06d}"


def _reading_id(dt: datetime) -> str:
    """Generate a reading ID in the format RD-YYYYMMDD-NNNNNN."""
    return f"RD-{dt.strftime('%Y%m%d')}-{random.randint(0, 999999):06d}"


def _clamp(val: float, lo: float, hi: float) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, val))


def _timestamps(start: datetime, end: datetime, interval_min: int) -> list[datetime]:
    """Generate a list of timestamps from start to end at interval_min intervals."""
    result = []
    t = start
    delta = timedelta(minutes=interval_min)
    while t <= end:
        result.append(t)
        t += delta
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Baseline generators
# ═══════════════════════════════════════════════════════════════════════════


def generate_sensor_baseline(
    sensors: list[dict[str, str]],
    start: datetime,
    end: datetime,
    interval_min: int,
) -> list[dict[str, Any]]:
    """Generate normal sensor readings for all sensors over the time window."""
    timestamps = _timestamps(start, end, interval_min)
    rows: list[dict[str, Any]] = []

    for sensor in sensors:
        sid = sensor["SensorId"]
        stype = sensor["SensorType"]
        defaults = SENSOR_DEFAULTS.get(stype, {"mean": 0, "sigma": 1, "unit": "?"})
        overrides = SENSOR_OVERRIDES.get(sid, {})
        mean = overrides.get("mean", defaults["mean"])
        sigma = overrides.get("sigma", defaults["sigma"])
        unit = defaults["unit"]

        for ts in timestamps:
            value = random.gauss(mean, sigma)
            # Clamp values to realistic ranges
            if stype == "OpticalPower":
                value = _clamp(value, -15.0, -5.0)
            elif stype == "BitErrorRate":
                value = max(1e-14, value)
            elif stype == "Temperature":
                value = _clamp(value, 18.0, 50.0)
            elif stype == "CPULoad":
                value = _clamp(value, 5.0, 65.0)

            rows.append({
                "ReadingId": _reading_id(ts),
                "Timestamp": _ts_sec(ts),
                "SensorId": sid,
                "SensorType": stype,
                "Value": round(value, 4) if stype == "BitErrorRate" else round(value, 1),
                "Unit": unit,
                "Status": "NORMAL",
            })

    return rows


def generate_link_baseline(
    links: list[str],
    start: datetime,
    end: datetime,
    interval_min: int,
) -> list[dict[str, Any]]:
    """Generate normal link telemetry for all links over the time window."""
    timestamps = _timestamps(start, end, interval_min)
    rows: list[dict[str, Any]] = []

    for link_id in links:
        profile = LINK_PROFILES.get(link_id)
        if not profile:
            continue
        u_mean, u_sigma = profile["util"]
        o_mean, o_sigma = profile["opt"]
        b_mean, b_sigma = profile["ber"]
        l_mean, l_sigma = profile["lat"]

        for ts in timestamps:
            rows.append({
                "LinkId": link_id,
                "Timestamp": _ts_sec(ts).replace("+00:00", ".000Z"),
                "UtilizationPct": round(_clamp(random.gauss(u_mean, u_sigma), 5, 95), 1),
                "OpticalPowerDbm": round(_clamp(random.gauss(o_mean, o_sigma), -8, 0), 1),
                "BitErrorRate": f"{max(1e-14, random.gauss(b_mean, b_sigma)):.3e}",
                "LatencyMs": round(max(0.5, random.gauss(l_mean, l_sigma)), 1),
            })

    return rows


def generate_alert_noise(
    start: datetime,
    end: datetime,
    rate_per_hour: float = 50,
) -> list[dict[str, Any]]:
    """Generate background noise alerts across all nodes."""
    rows: list[dict[str, Any]] = []
    total_hours = (end - start).total_seconds() / 3600
    total_alerts = int(total_hours * rate_per_hour)

    for _ in range(total_alerts):
        # Random timestamp within window
        offset_secs = random.uniform(0, (end - start).total_seconds())
        ts = start + timedelta(seconds=offset_secs)

        source_id, source_type = random.choice(NOISE_SOURCES)
        alert_type, severity, desc_template = random.choice(NOISE_TYPES)

        # Generate random metric values in normal ranges
        opt_power = round(random.gauss(-2.8, 0.5), 1)
        ber = f"{max(1e-14, random.gauss(5e-12, 3e-12)):.3e}"
        cpu = round(_clamp(random.gauss(35, 12), 10, 75), 1)
        pkt_loss = round(_clamp(random.gauss(0.3, 0.3), 0.001, 1.5), 3)

        desc = desc_template.format(pct=random.uniform(0.3, 1.5))

        rows.append({
            "AlertId": _alert_id(ts),
            "Timestamp": _ts(ts),
            "SourceNodeId": source_id,
            "SourceNodeType": source_type,
            "AlertType": alert_type,
            "Severity": severity,
            "Description": desc,
            "OpticalPowerDbm": opt_power,
            "BitErrorRate": ber,
            "CPUUtilPct": cpu,
            "PacketLossPct": pkt_loss,
        })

    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Event injectors
# ═══════════════════════════════════════════════════════════════════════════


def inject_fibre_cut(
    rows: list[dict[str, Any]],
    cut_time: datetime,
    affected_sensors: list[str],
    ber_sensors: list[str],
) -> list[dict[str, Any]]:
    """Inject loss-of-light cliff on affected optical/BER sensors at cut_time.

    Affected sensors drop to critical values. Unaffected sensors are untouched.
    Also switches to 1-minute readings for 30 minutes post-incident on affected sensors.
    """
    # Modify existing rows after cut_time for affected sensors
    for row in rows:
        if row["Timestamp"] < _ts_sec(cut_time):
            continue
        sid = row["SensorId"]
        if sid in affected_sensors:
            row["Value"] = round(random.uniform(-33.0, -31.0), 1)
            row["Status"] = "CRITICAL"
        elif sid in ber_sensors:
            row["Value"] = round(random.uniform(0.8, 1.0), 4)
            row["Status"] = "CRITICAL"

    # Add high-resolution readings (1-min) for 30 min post-incident on affected sensors
    extra_rows = []
    for minute_offset in range(1, 31):
        ts = cut_time + timedelta(minutes=minute_offset)
        for sid in affected_sensors:
            extra_rows.append({
                "ReadingId": _reading_id(ts),
                "Timestamp": _ts_sec(ts),
                "SensorId": sid,
                "SensorType": "OpticalPower",
                "Value": round(random.uniform(-33.0, -31.0), 1),
                "Unit": "dBm",
                "Status": "CRITICAL",
            })
        for sid in ber_sensors:
            extra_rows.append({
                "ReadingId": _reading_id(ts),
                "Timestamp": _ts_sec(ts),
                "SensorId": sid,
                "SensorType": "BitErrorRate",
                "Value": round(random.uniform(0.8, 1.0), 4),
                "Unit": "ratio",
                "Status": "CRITICAL",
            })

    rows.extend(extra_rows)
    return rows


def inject_cpu_spike(
    rows: list[dict[str, Any]],
    sensor_id: str,
    spike_time: datetime,
    peak_pct: float,
    duration_min: int = 5,
) -> list[dict[str, Any]]:
    """Inject a CPU spike on a sensor around spike_time."""
    spike_end = spike_time + timedelta(minutes=duration_min)
    for row in rows:
        if row["SensorId"] != sensor_id:
            continue
        ts_str = row["Timestamp"]
        # Parse timestamp for comparison
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if spike_time <= ts <= spike_end:
            row["Value"] = round(random.uniform(peak_pct - 5, peak_pct + 3), 1)
    return rows


def inject_link_down(
    rows: list[dict[str, Any]],
    link_id: str,
    down_time: datetime,
) -> list[dict[str, Any]]:
    """Set a link to loss-of-light state after down_time."""
    for row in rows:
        if row["LinkId"] != link_id:
            continue
        ts_str = row["Timestamp"]
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts >= down_time:
            row["UtilizationPct"] = 0.0
            row["OpticalPowerDbm"] = -35.0
            row["BitErrorRate"] = "1.000e+00"
            row["LatencyMs"] = 9999.0
    return rows


def inject_traffic_shift(
    rows: list[dict[str, Any]],
    link_ids: list[str],
    shift_time: datetime,
    increase_pct: float,
) -> list[dict[str, Any]]:
    """Increase utilization on specified links after shift_time (traffic reroute)."""
    for row in rows:
        if row["LinkId"] not in link_ids:
            continue
        ts_str = row["Timestamp"]
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts >= shift_time:
            current_util = row["UtilizationPct"]
            row["UtilizationPct"] = round(min(95, current_util + increase_pct), 1)
    return rows


def inject_alert_storm(
    rows: list[dict[str, Any]],
    storm_time: datetime,
) -> list[dict[str, Any]]:
    """Insert the 20-alert fibre cut storm at storm_time."""
    for spec in FIBRE_CUT_STORM:
        ts = storm_time + timedelta(milliseconds=spec["ts_offset_ms"])
        rows.append({
            "AlertId": _alert_id(ts),
            "Timestamp": _ts(ts),
            "SourceNodeId": spec["source"],
            "SourceNodeType": "Service",
            "AlertType": spec["type"],
            "Severity": spec["sev"],
            "Description": spec["desc"],
            "OpticalPowerDbm": round(random.gauss(-3.0, 0.4), 1),
            "BitErrorRate": f"{max(1e-14, random.gauss(5e-12, 3e-12)):.3e}",
            "CPUUtilPct": round(_clamp(random.gauss(55, 10), 40, 75), 1),
            "PacketLossPct": round(_clamp(random.gauss(12, 8), 1.5, 25), 2),
        })
    return rows


def inject_secondary_alerts(
    rows: list[dict[str, Any]],
    storm_time: datetime,
) -> list[dict[str, Any]]:
    """Insert post-storm secondary symptom alerts."""
    for spec in SECONDARY_ALERTS:
        ts = storm_time + timedelta(seconds=spec["delay_s"])
        # Add some jitter
        ts += timedelta(milliseconds=random.randint(0, 500))
        rows.append({
            "AlertId": _alert_id(ts),
            "Timestamp": _ts(ts),
            "SourceNodeId": spec["source"],
            "SourceNodeType": spec["stype"],
            "AlertType": spec["type"],
            "Severity": spec["sev"],
            "Description": spec["desc"],
            "OpticalPowerDbm": round(random.gauss(-3.0, 0.5), 1),
            "BitErrorRate": f"{max(1e-14, random.gauss(5e-12, 3e-12)):.3e}",
            "CPUUtilPct": round(_clamp(random.gauss(70, 10), 50, 92), 1),
            "PacketLossPct": round(_clamp(random.gauss(5, 3), 0.5, 15), 2),
        })

    # Add ~45 more secondary alerts spread over 14:31:15 to 14:35:00
    secondary_sources = [
        ("VPN-ACME-CORP", "Service", "SERVICE_DEGRADATION", "CRITICAL"),
        ("VPN-BIGBANK", "Service", "SERVICE_DEGRADATION", "CRITICAL"),
        ("BB-BUNDLE-SYD-NORTH", "Service", "SERVICE_DEGRADATION", "MAJOR"),
        ("BB-BUNDLE-MEL-EAST", "Service", "SERVICE_DEGRADATION", "MAJOR"),
        ("MOB-5G-SYD-2041", "Service", "SERVICE_DEGRADATION", "WARNING"),
        ("MOB-5G-SYD-2042", "Service", "SERVICE_DEGRADATION", "WARNING"),
        ("MOB-5G-MEL-3011", "Service", "SERVICE_DEGRADATION", "WARNING"),
        ("CORE-SYD-01", "CoreRouter", "HIGH_CPU", "MAJOR"),
        ("CORE-MEL-01", "CoreRouter", "HIGH_CPU", "MAJOR"),
    ]
    descs = [
        "Sustained service degradation — primary path unavailable",
        "Failover path activated — increased latency detected",
        "Routing reconvergence — transient packet loss",
        "Customer impact ongoing — ticket escalation recommended",
    ]

    for i in range(45):
        delay_s = random.uniform(2, 230)  # 2 seconds to ~4 minutes after storm
        ts = storm_time + timedelta(seconds=delay_s)
        src, stype, atype, sev = random.choice(secondary_sources)
        rows.append({
            "AlertId": _alert_id(ts),
            "Timestamp": _ts(ts),
            "SourceNodeId": src,
            "SourceNodeType": stype,
            "AlertType": atype,
            "Severity": sev,
            "Description": random.choice(descs),
            "OpticalPowerDbm": round(random.gauss(-3.0, 0.5), 1),
            "BitErrorRate": f"{max(1e-14, random.gauss(5e-12, 3e-12)):.3e}",
            "CPUUtilPct": round(_clamp(random.gauss(60, 12), 30, 90), 1),
            "PacketLossPct": round(_clamp(random.gauss(8, 5), 0.5, 20), 2),
        })

    return rows


# ═══════════════════════════════════════════════════════════════════════════
# CSV writers
# ═══════════════════════════════════════════════════════════════════════════


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write rows to a CSV file, sorted by Timestamp."""
    rows.sort(key=lambda r: r.get("Timestamp", ""))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    """Generate all three telemetry CSVs."""
    random.seed(SEED)
    print("Generating telemetry data...")
    print(f"  Observation: {OBSERVATION_START} → {OBSERVATION_END}")
    print(f"  Incident:    {INCIDENT_TIME}")

    # Load sensor inventory from filtered DimSensor.csv
    sensors = []
    with open(ENTITY_DIR / "DimSensor.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sensors.append(row)
    print(f"  Sensors: {len(sensors)}")

    # Load link inventory
    link_ids = list(LINK_PROFILES.keys())
    print(f"  Links: {len(link_ids)}")

    # ── SensorReadings ──────────────────────────────────────────────
    print("\nSensorReadings:")
    sr = generate_sensor_baseline(sensors, OBSERVATION_START, OBSERVATION_END, INTERVAL_MIN)
    sr = inject_fibre_cut(
        sr,
        INCIDENT_TIME,
        affected_sensors=["SENS-SYD-MEL-F1-OPT-002", "SENS-SYD-MEL-F1-OPT-003"],
        ber_sensors=["SENS-SYD-MEL-F1-BER-001", "SENS-SYD-MEL-F1-BER-002"],
    )
    sr = inject_cpu_spike(sr, "SENS-CORE-SYD-01-CPU-001", INCIDENT_TIME, peak_pct=72)
    sr = inject_cpu_spike(sr, "SENS-CORE-MEL-01-CPU-001", INCIDENT_TIME, peak_pct=68)
    write_csv(
        OUTPUT_DIR / "SensorReadings.csv",
        sr,
        ["ReadingId", "Timestamp", "SensorId", "SensorType", "Value", "Unit", "Status"],
    )

    # ── LinkTelemetry ───────────────────────────────────────────────
    print("LinkTelemetry:")
    lt = generate_link_baseline(link_ids, OBSERVATION_START, OBSERVATION_END, INTERVAL_MIN)
    lt = inject_link_down(lt, "LINK-SYD-MEL-FIBRE-01", INCIDENT_TIME)
    lt = inject_traffic_shift(
        lt,
        ["LINK-SYD-MEL-FIBRE-02", "LINK-SYD-BNE-FIBRE-01", "LINK-MEL-BNE-FIBRE-01"],
        INCIDENT_TIME + timedelta(minutes=4),
        increase_pct=25,
    )
    write_csv(
        OUTPUT_DIR / "LinkTelemetry.csv",
        lt,
        ["LinkId", "Timestamp", "UtilizationPct", "OpticalPowerDbm", "BitErrorRate", "LatencyMs"],
    )

    # ── AlertStream ────────────────────────────────────────────────
    print("AlertStream:")
    al = generate_alert_noise(OBSERVATION_START, OBSERVATION_END, rate_per_hour=50)
    al = inject_alert_storm(al, INCIDENT_TIME)
    al = inject_secondary_alerts(al, INCIDENT_TIME)
    write_csv(
        OUTPUT_DIR / "AlertStream.csv",
        al,
        ["AlertId", "Timestamp", "SourceNodeId", "SourceNodeType", "AlertType",
         "Severity", "Description", "OpticalPowerDbm", "BitErrorRate", "CPUUtilPct", "PacketLossPct"],
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
