#!/usr/bin/env python3
"""Filter DimSensor.csv — remove vibration sensors.

Reads the source telecom-playground DimSensor.csv, drops rows where
SensorType == "Vibration", writes the result to the local data/entities/
directory. Idempotent — safe to run multiple times.

Input:  telecom-playground/data/entities/DimSensor.csv (18 rows)
Output: data/entities/DimSensor.csv (16 rows — no vibration sensors)
"""

import csv
from pathlib import Path

# Resolve paths relative to this script's parent (the scenario root)
SCENARIO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SCENARIO = SCENARIO_ROOT.parent / "telecom-playground"
SOURCE_CSV = SOURCE_SCENARIO / "data" / "entities" / "DimSensor.csv"
OUTPUT_CSV = SCENARIO_ROOT / "data" / "entities" / "DimSensor.csv"

# Sensor types to exclude from the enhanced scenario
EXCLUDED_TYPES = {"Vibration"}


def main() -> None:
    """Read source CSV, filter out vibration sensors, write output."""
    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = [r for r in reader if r["SensorType"] not in EXCLUDED_TYPES]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    excluded = 18 - len(rows)
    print(f"DimSensor.csv: {len(rows)} rows written ({excluded} vibration sensors removed)")
    print(f"Output: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
