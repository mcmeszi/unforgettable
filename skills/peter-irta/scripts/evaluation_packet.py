#!/usr/bin/env python3
"""Create a multidimensional, order-swapped evaluation packet for two drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generation_contracts import genre_quality_contract


DIMENSIONS = {
    "brief_fidelity": "Tartalmi, terjedelmi és feladatbeli hűség; a stílus nem írhatja felül a briefet.",
    "genre_naturalness": "A célműfajban természetes, használható és felolvasva vagy publikálva működő szöveg.",
    "author_style_match": "Több műcsaládra támaszkodó szerzői mechanika- és ritmusegyezés, idézetmásolás nélkül.",
    "originality_anti_caricature": "Önálló megoldás, amely nem halmozza mechanikusan Péter visszatérő motívumait és manírjait.",
}
JUDGES = {
    "brief-editor": "Elsősorban a feladat teljesülését, pontosságát és kihagyásait vizsgáld.",
    "genre-practitioner": "Elsősorban a műfaji működést, ritmust és természetességet vizsgáld.",
    "authorship-skeptic": "Keresd a felszínes utánzást, karikatúrát, forrásszivárgást és az indokolatlan stílusállítást.",
}


def build_packet(brief: str, genre: str, draft_a: str, draft_b: str, portfolio: dict) -> dict:
    quality_contract = genre_quality_contract(genre)
    guard_ids = sorted(item["id"] for item in quality_contract["release_checks"])
    assignments = []
    for judge, focus in JUDGES.items():
        for order in (("A", "B"), ("B", "A")):
            assignments.append(
                {
                    "judge": judge,
                    "focus": focus,
                    "candidate_order": list(order),
                    "genre_guard_ids": guard_ids,
                    "scoring_contract": {
                        "scale": "0..2 per dimension",
                        "required_output": ["dimension_scores", "winner", "decisive_reason", "hard_guard_failures"],
                    },
                }
            )
    packet_id = hashlib.sha256(
        json.dumps(
            {"brief": brief, "genre": genre, "draft_a": draft_a, "draft_b": draft_b, "run_id": portfolio.get("run_id")},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": 1,
        "packet_id": packet_id,
        "genre": genre,
        "brief": brief,
        "portfolio_run_id": portfolio.get("run_id"),
        "portfolio_source_ids": [str(source.get("id")) for source in portfolio.get("sources") or [] if source.get("id")],
        "dimensions": DIMENSIONS,
        "genre_quality_contract": quality_contract,
        "candidates": {"A": draft_a, "B": draft_b},
        "judge_assignments": assignments,
        "aggregation": {
            "order_bias_guard": "A winner is stable only when the reversed-order assignment agrees.",
            "ensemble_rule": "Report per-dimension medians and judge disagreement; do not collapse hard-guard failures into an average.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, required=True)
    parser.add_argument("--draft-a", type=Path, required=True)
    parser.add_argument("--draft-b", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--genre", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    portfolio = json.loads(args.portfolio.read_text(encoding="utf-8-sig"))
    packet = build_packet(
        args.brief.read_text(encoding="utf-8-sig"),
        args.genre,
        args.draft_a.read_text(encoding="utf-8-sig"),
        args.draft_b.read_text(encoding="utf-8-sig"),
        portfolio,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "packet_id": packet["packet_id"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
