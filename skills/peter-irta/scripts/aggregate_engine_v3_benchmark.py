#!/usr/bin/env python3
"""Validate, freeze, unblind and aggregate the Engine v3 benchmark judgments."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path


DIMENSIONS = (
    "brief_fidelity",
    "genre_naturalness",
    "author_style_match",
    "originality_anti_caricature",
)
SYSTEMS = ("legacy", "engine_v3")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def judgment_valid(data: dict) -> bool:
    if data.get("winner") not in {"candidate_1", "candidate_2", "tie"}:
        return False
    for candidate in ("candidate_1", "candidate_2"):
        scores = (data.get("scores") or {}).get(candidate) or {}
        if set(scores) != set(DIMENSIONS):
            return False
        if any(not isinstance(scores[name], (int, float)) or not 0 <= scores[name] <= 2 for name in DIMENSIONS):
            return False
        if not isinstance((data.get("hard_guard_failures") or {}).get(candidate), list):
            return False
    return True


def validate_and_manifest(jobs: list[dict], judgments_dir: Path) -> dict:
    expected = {str(job["job_id"]) for job in jobs}
    actual_files = {path.stem: path for path in judgments_dir.glob("*.json")}
    actual = set(actual_files)
    invalid = []
    records = []
    for job_id in sorted(expected & actual):
        path = actual_files[job_id]
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError):
            invalid.append(job_id)
            continue
        if data.get("job_id") != job_id or not judgment_valid(data):
            invalid.append(job_id)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"job_id": job_id, "sha256": digest, "bytes": path.stat().st_size})
    bundle_payload = "\n".join(f"{item['job_id']}:{item['sha256']}" for item in records)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    return {
        "schema_version": 1,
        "expected_count": len(expected),
        "valid_count": len(records),
        "valid": not missing and not unexpected and not invalid and len(records) == len(expected),
        "missing_job_ids": missing,
        "unexpected_job_ids": unexpected,
        "invalid_job_ids": invalid,
        "bundle_sha256": hashlib.sha256(bundle_payload.encode("utf-8")).hexdigest(),
        "judgments": records,
    }


def aggregate(jobs: list[dict], judgments: dict[str, dict], order_key: dict, blind_key: dict) -> dict:
    job_by_id = {str(job["job_id"]): job for job in jobs}
    votes = defaultdict(int)
    hard_failures = defaultdict(int)
    dimension_values = {system: {dimension: [] for dimension in DIMENSIONS} for system in SYSTEMS}
    brief_votes = defaultdict(lambda: defaultdict(int))
    genre_by_brief = {}
    translated_winners = {}
    per_judgment = []
    for job_id in sorted(job_by_id):
        job = job_by_id[job_id]
        judgment = judgments[job_id]
        brief_id = str(job["brief_id"])
        _, judge, _ = job_id.split("--")
        genre_by_brief[brief_id] = str(job["genre"])
        position_to_candidate = order_key["jobs"][job_id]
        candidate_to_system = blind_key[brief_id]
        position_to_system = {
            position: candidate_to_system[candidate]
            for position, candidate in position_to_candidate.items()
        }
        for position, system in position_to_system.items():
            for dimension in DIMENSIONS:
                dimension_values[system][dimension].append(float(judgment["scores"][position][dimension]))
            hard_failures[system] += len(judgment["hard_guard_failures"][position])
        winner_position = judgment["winner"]
        winner_system = "tie" if winner_position == "tie" else position_to_system[winner_position]
        translated_winners[job_id] = winner_system
        votes[winner_system] += 1
        brief_votes[brief_id][winner_system] += 1
        per_judgment.append({"job_id": job_id, "brief_id": brief_id, "judge": judge, "winner": winner_system})

    brief_results = []
    brief_win_counts = defaultdict(int)
    genre_results = defaultdict(lambda: {"legacy": 0, "engine_v3": 0, "tie": 0})
    for brief_id in sorted(brief_votes):
        counts = brief_votes[brief_id]
        if counts["engine_v3"] > counts["legacy"]:
            winner = "engine_v3"
        elif counts["legacy"] > counts["engine_v3"]:
            winner = "legacy"
        else:
            winner = "tie"
        brief_win_counts[winner] += 1
        genre_results[genre_by_brief[brief_id]][winner] += 1
        brief_results.append({"brief_id": brief_id, "genre": genre_by_brief[brief_id], "winner": winner, "votes": dict(counts)})

    stable_pairs = 0
    unstable_pairs = []
    paired = defaultdict(dict)
    for job_id, winner in translated_winners.items():
        brief_id, judge, order = job_id.split("--")
        paired[(brief_id, judge)][order] = winner
    for (brief_id, judge), pair in sorted(paired.items()):
        if pair.get("AB") == pair.get("BA"):
            stable_pairs += 1
        else:
            unstable_pairs.append({"brief_id": brief_id, "judge": judge, "AB": pair.get("AB"), "BA": pair.get("BA")})

    return {
        "schema_version": 1,
        "benchmark": "v1-retrieval-vs-engine-v3",
        "overall": {
            "brief_wins": {name: brief_win_counts[name] for name in (*SYSTEMS, "tie")},
            "judge_votes": {name: votes[name] for name in (*SYSTEMS, "tie")},
            "dimension_medians": {
                system: {dimension: round(statistics.median(values), 3) for dimension, values in dimension_values[system].items()}
                for system in SYSTEMS
            },
            "dimension_means": {
                system: {dimension: round(statistics.mean(values), 3) for dimension, values in dimension_values[system].items()}
                for system in SYSTEMS
            },
            "hard_guard_failures": {system: hard_failures[system] for system in SYSTEMS},
        },
        "by_genre": {genre: result for genre, result in sorted(genre_results.items())},
        "order_bias": {
            "pair_count": len(paired),
            "stable_pairs": stable_pairs,
            "unstable_pairs": len(unstable_pairs),
            "stability_rate": round(stable_pairs / len(paired), 3) if paired else 0.0,
            "details": unstable_pairs,
        },
        "briefs": brief_results,
        "judgments": per_judgment,
        "limitations": [
            "The same model family generated and judged the drafts.",
            "The benchmark measures this fixed 30-brief corpus, not universal writing quality.",
            "No human verdict or retrieval utility was recorded.",
            "The Engine v3 reranker remained cold-start throughout the benchmark.",
        ],
    }


def render_report(result: dict, manifest: dict) -> str:
    overall = result["overall"]
    lines = [
        "# V1 retrieval vs Engine v3 — vak benchmark",
        "",
        f"Ítéletek: {manifest['valid_count']}/{manifest['expected_count']} · bundle SHA-256: `{manifest['bundle_sha256']}`",
        "",
        "## Eredmény",
        "",
        f"- Brief-győzelmek: Engine v3 {overall['brief_wins']['engine_v3']}, V1 {overall['brief_wins']['legacy']}, döntetlen {overall['brief_wins']['tie']}.",
        f"- Bírói szavazatok: Engine v3 {overall['judge_votes']['engine_v3']}, V1 {overall['judge_votes']['legacy']}, döntetlen {overall['judge_votes']['tie']}.",
        f"- Hard guard hibák: Engine v3 {overall['hard_guard_failures']['engine_v3']}, V1 {overall['hard_guard_failures']['legacy']}.",
        f"- Sorrendstabilitás: {result['order_bias']['stable_pairs']}/{result['order_bias']['pair_count']} ({result['order_bias']['stability_rate']:.1%}).",
        "",
        "## Műfajonkénti brief-győzelmek",
        "",
        "| Műfaj | Engine v3 | V1 | Döntetlen |",
        "|---|---:|---:|---:|",
    ]
    for genre, values in result["by_genre"].items():
        lines.append(f"| {genre} | {values['engine_v3']} | {values['legacy']} | {values['tie']} |")
    lines.extend(["", "## Dimenzióátlagok", "", "| Dimenzió | Engine v3 | V1 | Delta |", "|---|---:|---:|---:|"])
    for dimension in DIMENSIONS:
        engine = overall["dimension_means"]["engine_v3"][dimension]
        legacy = overall["dimension_means"]["legacy"][dimension]
        lines.append(f"| {dimension} | {engine:.3f} | {legacy:.3f} | {engine - legacy:+.3f} |")
    lines.extend(["", "## Korlátok", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--judgments-dir", type=Path, required=True)
    parser.add_argument("--order-key", type=Path, required=True)
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    jobs = [json.loads(line) for line in args.jobs.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    manifest = validate_and_manifest(jobs, args.judgments_dir)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not manifest["valid"]:
        print(json.dumps(manifest, ensure_ascii=False))
        return 1
    judgments = {item["job_id"]: load_json(args.judgments_dir / f"{item['job_id']}.json") for item in jobs}
    result = aggregate(jobs, judgments, load_json(args.order_key), load_json(args.blind_key))
    result["judgment_bundle_sha256"] = manifest["bundle_sha256"]
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report.write_text(render_report(result, manifest), encoding="utf-8")
    print(json.dumps({"valid_judgments": manifest["valid_count"], "bundle_sha256": manifest["bundle_sha256"], "brief_wins": result["overall"]["brief_wins"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
