#!/usr/bin/env python3
"""Compare a draft with the brief-specific Mind Vault rhythm fingerprint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from vault_query import text_style_metrics


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    args = parser.parse_args()

    portfolio = load_json(args.portfolio)
    bands = portfolio.get("style_fingerprint", {}).get("metric_bands", {})
    if not bands:
        raise SystemExit("Portfolio has no style_fingerprint.metric_bands; rebuild it with the current vault_query.py")
    draft_metrics = text_style_metrics(args.draft.read_text(encoding="utf-8-sig"))

    deviations = []
    for metric, value in draft_metrics.items():
        band = bands.get(metric)
        if not band:
            continue
        lower = float(band["min"])
        upper = float(band["max"])
        span = max(0.001, upper - lower)
        tolerance = max(span * 0.2, abs(float(band["median"])) * 0.08, 0.02)
        if value < lower - tolerance:
            deviations.append({"metric": metric, "direction": "below", "draft": value, "reference": band})
        elif value > upper + tolerance:
            deviations.append({"metric": metric, "direction": "above", "draft": value, "reference": band})

    print(
        json.dumps(
            {
                "draft": str(args.draft),
                "reference_source_count": portfolio.get("style_fingerprint", {}).get("source_count"),
                "draft_metrics": draft_metrics,
                "deviations": deviations,
                "verdict": "review" if deviations else "within-reference-range",
                "instruction": "Treat deviations as revision questions, not automatic errors. Preserve intentional genre effects.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
