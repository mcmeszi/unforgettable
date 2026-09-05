#!/usr/bin/env python3
"""Validate the internal thinking-DNA map for argumentative Peter writing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIELDS = (
    "personal_stake",
    "claim",
    "not_claiming",
    "strongest_counterargument",
    "where_counterargument_is_right",
    "perspective_turn",
)
ALLOWED_ORIGINS = {"brief-derived", "vault-backed", "not-applicable"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.map.read_text(encoding="utf-8-sig"))
    missing = [field for field in FIELDS if field not in data]
    invalid = []
    unsupported = []
    for field in FIELDS:
        item = data.get(field) or {}
        if item.get("origin") not in ALLOWED_ORIGINS:
            invalid.append(field)
        if item.get("origin") == "vault-backed" and not item.get("source_ids"):
            unsupported.append(field)
        if item.get("origin") != "not-applicable" and not str(item.get("text", "")).strip():
            unsupported.append(field)
    verdict = "fail" if missing or invalid or unsupported else "pass"
    print(json.dumps({"missing": missing, "invalid_origin": invalid, "missing_evidence": unsupported, "verdict": verdict}, ensure_ascii=False, indent=2))
    return 1 if verdict == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
