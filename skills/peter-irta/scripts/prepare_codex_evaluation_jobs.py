#!/usr/bin/env python3
"""Prepare independent order-swapped judge jobs from frozen blind drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evaluation_packet import DIMENSIONS, JUDGES
from generation_contracts import genre_quality_contract


def build_jobs(generation_jobs: list[dict], drafts_dir: Path) -> tuple[list[dict], dict]:
    by_brief = {}
    for job in generation_jobs:
        by_brief.setdefault(str(job["brief_id"]), job)
    public_jobs = []
    private_key = {}
    for brief_id, source in sorted(by_brief.items()):
        drafts = {
            label: (drafts_dir / f"{brief_id}-{label}.md").read_text(encoding="utf-8-sig").strip()
            for label in ("A", "B")
        }
        contract = genre_quality_contract(str(source["genre"]))
        for judge, focus in JUDGES.items():
            for order in (("A", "B"), ("B", "A")):
                order_name = "AB" if order == ("A", "B") else "BA"
                job_id = f"{brief_id}--{judge}--{order_name}"
                public_jobs.append(
                    {
                        "job_id": job_id,
                        "brief_id": brief_id,
                        "genre": source["genre"],
                        "brief": source["brief"],
                        "audience": source.get("audience", ""),
                        "constraints": source.get("constraints") or [],
                        "judge": judge,
                        "focus": focus,
                        "dimensions": DIMENSIONS,
                        "genre_quality_contract": contract,
                        "candidate_1": drafts[order[0]],
                        "candidate_2": drafts[order[1]],
                        "required_output": {
                            "scores": "0..2 per dimension for candidate_1 and candidate_2",
                            "winner": "candidate_1, candidate_2 or tie",
                            "decisive_reason": "one concise reason",
                            "hard_guard_failures": "separate arrays per candidate",
                        },
                    }
                )
                private_key[job_id] = {"candidate_1": order[0], "candidate_2": order[1]}
    return public_jobs, {"schema_version": 1, "jobs": private_key}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation-jobs", type=Path, required=True)
    parser.add_argument("--drafts-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    generation_jobs = [json.loads(line) for line in args.generation_jobs.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    jobs, private_key = build_jobs(generation_jobs, args.drafts_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    public_path = args.output_dir / "evaluation-jobs.jsonl"
    key_path = args.output_dir / "private-order-key.json"
    public_path.write_text("\n".join(json.dumps(job, ensure_ascii=False) for job in jobs) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(private_key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(public_path.read_bytes()).hexdigest()
    print(json.dumps({"jobs": len(jobs), "briefs": len({job['brief_id'] for job in jobs}), "sha256": digest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
