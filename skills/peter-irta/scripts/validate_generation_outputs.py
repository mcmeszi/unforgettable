#!/usr/bin/env python3
"""Validate blind draft completeness and write an immutable hash manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


FORBIDDEN = re.compile(r"\b(?:benchmark|source_label|engine[_ -]?v3|legacy retrieval)\b", re.IGNORECASE)
WORD_RANGE = re.compile(r"(\d{2,5})\s*[–-]\s*(\d{2,5})\s+szavas", re.IGNORECASE)
WORD_TARGET = re.compile(r"(?<![–-])(\d{2,5})\s+szavas", re.IGNORECASE)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÁÉÍÓÖŐÚÜŰáéíóöőúüű'-]+\b", text, re.UNICODE))


def validate(jobs: list[dict], drafts_dir: Path) -> dict:
    issues = []
    records = []
    hashes = {}
    for job in jobs:
        job_id = str(job["job_id"])
        path = drafts_dir / f"{job_id}.md"
        if not path.exists():
            issues.append({"job_id": job_id, "type": "missing"})
            continue
        text = path.read_text(encoding="utf-8-sig").strip()
        words = word_count(text)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        hashes[job_id] = digest
        if len(text) < 40:
            issues.append({"job_id": job_id, "type": "too-short", "characters": len(text)})
        if FORBIDDEN.search(text):
            issues.append({"job_id": job_id, "type": "prompt-leakage"})
        range_match = WORD_RANGE.search(str(job.get("brief", "")))
        target_match = WORD_TARGET.search(str(job.get("brief", ""))) if not range_match else None
        if range_match:
            lower, upper = map(int, range_match.groups())
            if not lower <= words <= upper:
                issues.append({"job_id": job_id, "type": "word-range", "words": words, "expected": [lower, upper]})
        elif target_match:
            target = int(target_match.group(1))
            tolerance = max(20, round(target * 0.1))
            if not target - tolerance <= words <= target + tolerance:
                issues.append({"job_id": job_id, "type": "word-target", "words": words, "expected": target, "tolerance": tolerance})
        records.append({"job_id": job_id, "genre": job.get("genre"), "words": words, "sha256": digest})
    brief_ids = sorted({str(job["brief_id"]) for job in jobs})
    for brief_id in brief_ids:
        left, right = hashes.get(f"{brief_id}-A"), hashes.get(f"{brief_id}-B")
        if left and right and left == right:
            issues.append({"brief_id": brief_id, "type": "identical-pair"})
    return {
        "schema_version": 1,
        "job_count": len(jobs),
        "draft_count": len(records),
        "valid": not issues,
        "issues": issues,
        "drafts": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--drafts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    jobs = [json.loads(line) for line in args.jobs.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    result = validate(jobs, args.drafts_dir)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("job_count", "draft_count", "valid", "issues")}, ensure_ascii=False))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
