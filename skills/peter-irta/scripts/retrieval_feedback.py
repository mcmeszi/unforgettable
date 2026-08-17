#!/usr/bin/env python3
"""Record outcome-linked utility for a vault retrieval portfolio."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


LEDGER = Path(__file__).resolve().parents[1] / "state" / "retrieval-utility.jsonl"
ALLOWED_DIMENSIONS = {
    "brief_fidelity",
    "genre_naturalness",
    "author_style_match",
    "originality_anti_caricature",
}


def parse_dimensions(entries: list[str]) -> dict[str, float]:
    dimensions = {}
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(f"Invalid --dimension {entry!r}; use name=0..2")
        name, raw_value = entry.split("=", 1)
        name = name.strip()
        if name not in ALLOWED_DIMENSIONS:
            raise SystemExit(f"Unknown evaluation dimension: {name}")
        value = float(raw_value)
        if not 0.0 <= value <= 2.0:
            raise SystemExit(f"Dimension {name} must be between 0 and 2")
        dimensions[name] = value
    return dimensions


def build_entry(
    data: dict,
    utility: float,
    note: str = "",
    dimensions: dict[str, float] | None = None,
    recorded_at: str | None = None,
) -> dict:
    execution_ids = [
        str(item.get("id"))
        for item in data.get("contrastive_calibration", {}).get("execution_set", [])
        if item.get("id")
    ]
    source_by_id = {str(source.get("id")): source for source in data.get("sources") or [] if source.get("id")}
    source_uses = [
        {
            "id": source_id,
            "channel": source_by_id.get(source_id, {}).get("retrieval_channel", "unknown"),
            "role": source_by_id.get(source_id, {}).get("portfolio_role", "unknown"),
        }
        for source_id in execution_ids
    ]
    return {
        "schema_version": 2,
        "recorded_at": recorded_at or datetime.now(timezone.utc).isoformat(),
        "run_id": data.get("run_id"),
        "genre": data.get("genre", ""),
        "source_ids": execution_ids,
        "source_uses": source_uses,
        "utility": utility,
        "dimensions": dimensions or {},
        "note": note,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--utility", type=float, choices=(-1.0, 0.0, 1.0), required=True)
    parser.add_argument("--note", default="")
    parser.add_argument("--dimension", action="append", default=[], help="Evaluation score as name=0..2")
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()
    data = json.loads(args.portfolio.read_text(encoding="utf-8-sig"))
    entry = build_entry(data, args.utility, args.note, parse_dimensions(args.dimension))
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
