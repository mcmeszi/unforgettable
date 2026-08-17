#!/usr/bin/env python3
"""Build a deterministic, system-blind 30-pair human evaluation pack."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path


def canonical_sha256(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def benchmark_briefs(result: dict) -> list[str]:
    rows = list(result.get("generation_jobs") or [])
    brief_ids = [str(row.get("brief_id", "")) for row in rows]
    if len(brief_ids) != 30 or len(set(brief_ids)) != 30 or any(not brief_id for brief_id in brief_ids):
        raise ValueError("benchmark must contain exactly 30 unique briefs")
    genres = Counter(str(row.get("genre", "")) for row in rows)
    if not genres or any(not genre or count != 3 for genre, count in genres.items()):
        raise ValueError("benchmark must contain exactly three briefs per genre")
    return brief_ids


def balanced_positions(brief_ids: list[str], seed: int) -> dict[str, bool]:
    if len(brief_ids) != 30 or len(set(brief_ids)) != 30:
        raise ValueError("balanced positions require 30 unique brief IDs")
    shuffled = list(brief_ids)
    random.Random(seed).shuffle(shuffled)
    return {brief_id: index < 15 for index, brief_id in enumerate(shuffled)}


def _draft_text(jobs: list[dict], drafts_dir: Path, brief_id: str, candidate: str) -> str:
    matching = [job for job in jobs if str(job.get("brief_id")) == brief_id and str(job.get("candidate")) == candidate]
    if len(matching) != 1:
        raise ValueError(f"expected one generation job for {brief_id}-{candidate}")
    job_id = str(matching[0].get("job_id") or f"{brief_id}-{candidate}")
    path = drafts_dir / f"{job_id}.md"
    if not path.is_file():
        raise ValueError(f"missing draft: {path}")
    return path.read_text(encoding="utf-8-sig").strip()


def build_pack(
    result: dict,
    jobs: list[dict],
    drafts_dir: Path,
    blind_key: dict,
    seed: int,
) -> tuple[dict, dict, dict]:
    brief_ids = benchmark_briefs(result)
    by_brief = {str(row["brief_id"]): row for row in result["generation_jobs"]}
    engine_left = balanced_positions(brief_ids, seed)
    shuffled = list(brief_ids)
    random.Random(seed).shuffle(shuffled)
    public_items = []
    private_items = {}
    for index, brief_id in enumerate(shuffled, start=1):
        mapping = blind_key.get(brief_id) or {}
        candidates = {str(system): candidate for candidate, system in mapping.items()}
        if set(candidates) != {"legacy", "engine_v3"}:
            raise ValueError(f"blind key must map A and B to both systems for {brief_id}")
        left_system = "engine_v3" if engine_left[brief_id] else "legacy"
        right_system = "legacy" if left_system == "engine_v3" else "engine_v3"
        left_candidate = candidates[left_system]
        right_candidate = candidates[right_system]
        left_text = _draft_text(jobs, drafts_dir, brief_id, left_candidate)
        right_text = _draft_text(jobs, drafts_dir, brief_id, right_candidate)
        item_id = f"item-{index:02d}"
        source = by_brief[brief_id]
        public_items.append(
            {
                "item_id": item_id,
                "brief_id": brief_id,
                "genre": source["genre"],
                "brief": source["brief"],
                "left_text": left_text,
                "right_text": right_text,
                "draft_hashes": {
                    "left": hashlib.sha256(left_text.encode("utf-8")).hexdigest(),
                    "right": hashlib.sha256(right_text.encode("utf-8")).hexdigest(),
                },
            }
        )
        private_items[item_id] = {
            "brief_id": brief_id,
            "left": left_system,
            "right": right_system,
            "left_candidate": left_candidate,
            "right_candidate": right_candidate,
        }
    public = {"schema_version": 1, "items": public_items}
    private = {"schema_version": 1, "items": private_items}
    manifest = {
        "schema_version": 1,
        "item_count": len(public_items),
        "seed": seed,
        "public_sha256": canonical_sha256(public),
        "private_sha256": canonical_sha256(private),
    }
    errors = validate_public_pack(public)
    if errors:
        raise ValueError("invalid public pack: " + "; ".join(errors))
    return public, private, manifest


def validate_public_pack(pack: dict) -> list[str]:
    errors = []
    items = pack.get("items")
    if not isinstance(items, list) or len(items) != 30:
        return ["public pack must contain exactly 30 items"]
    required = {"item_id", "brief_id", "genre", "brief", "left_text", "right_text", "draft_hashes"}
    item_ids = [str(item.get("item_id", "")) for item in items if isinstance(item, dict)]
    if len(item_ids) != 30 or len(set(item_ids)) != 30:
        errors.append("public item IDs must be unique")
    for item in items:
        if not isinstance(item, dict) or set(item) != required:
            errors.append("public items must contain only the required public fields")
            break
        if not all(isinstance(item[field], str) and item[field] for field in ("item_id", "brief_id", "genre", "brief", "left_text", "right_text")):
            errors.append("public item text fields must be non-empty strings")
            break
        hashes = item["draft_hashes"]
        if not isinstance(hashes, dict) or set(hashes) != {"left", "right"}:
            errors.append("public items must include left and right draft hashes")
            break
    return errors
