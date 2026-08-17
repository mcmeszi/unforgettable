#!/usr/bin/env python3
"""Prepare a blind V1 retrieval versus Engine v3 generation benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import mind_vault_engine
import run_retrieval_benchmark
import vault_query


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEFS = SKILL_ROOT / "references" / "benchmark-briefs.json"
DEFAULT_OUTPUT = SKILL_ROOT / "state" / "engine-v3-benchmark-latest.json"


def balanced_blind_labels(briefs: list[dict]) -> dict[str, tuple[str, str]]:
    ids = sorted(str(brief["id"]) for brief in briefs)
    start = int(hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:8], 16) % 2
    orders = (("legacy", "engine_v3"), ("engine_v3", "legacy"))
    return {brief_id: orders[(index + start) % 2] for index, brief_id in enumerate(ids)}


def engine_portfolio(packet: dict) -> dict:
    ranked = list(packet.get("evidence_compiler", {}).get("execution_evidence") or [])
    channel_sources = []
    for channel in ("content", "style_mechanics"):
        channel_sources.extend((packet.get("channels") or {}).get(channel) or [])
    source_by_id = {str(source.get("id")): source for source in channel_sources if source.get("id")}
    sources = []
    for item in ranked:
        source_id = str(item.get("id"))
        source = dict(source_by_id.get(source_id) or item)
        source["retrieval_channel"] = source.get("retrieval_channel") or item.get("channel")
        source["engine_preference_score"] = item.get("preference_score")
        sources.append(source)
    return {
        "run_id": packet.get("retrieval_run_id"),
        "genre": (packet.get("brief_plan", {}).get("genre") or {}).get("value", ""),
        "sources": sources,
        "contrastive_calibration": {
            "execution_set": [{"id": source.get("id"), "title": source.get("title", "")} for source in sources],
            "contrast_set": (packet.get("channels", {}).get("negative_examples") or {}).get("contrast_sources") or [],
        },
        "engine_metadata": {
            "schema": packet.get("schema"),
            "packet_id": packet.get("packet_id"),
            "retrieval_confidence": (packet.get("retrieval") or {}).get("confidence"),
            "reranker_state": (packet.get("preference_reranker") or {}).get("state", "cold-start"),
            "learned_preference_claimed": False,
        },
    }


def build_engine_packet(brief: dict, rag_root: Path) -> dict:
    plan = mind_vault_engine.plan_brief(
        str(brief["brief"]),
        genre=str(brief["genre"]),
        audience=str(brief.get("audience", "")),
    )
    args = SimpleNamespace(
        vault_query=SKILL_ROOT / "scripts" / "vault_query.py",
        rag_root=rag_root,
        variation_seed=f"engine-v3-benchmark:{brief['id']}",
        limit=0,
    )
    portfolio = mind_vault_engine.run_vault_query(plan, args)
    return mind_vault_engine.compile_engine_packet(portfolio, plan)


def run_benchmark(briefs: list[dict], rag_root: Path) -> dict:
    documents = list(vault_query.load_json(rag_root / "documents.json").get("documents") or [])
    chunks = list(vault_query.load_json(rag_root / "chunks.json").get("chunks") or [])
    profiled = [(document, vault_query.source_profile(document, chunks)) for document in documents if vault_query.style_eligible(document)]
    family_groups = run_retrieval_benchmark.build_family_groups(profiled)
    labels = balanced_blind_labels(briefs)
    jobs = []
    diagnostics = []
    for brief in briefs:
        legacy = run_retrieval_benchmark.retrieve_pair(brief, profiled, chunks, family_groups)["legacy"]
        engine = engine_portfolio(build_engine_packet(brief, rag_root))
        systems = {"legacy": legacy, "engine_v3": engine}
        left, right = labels[str(brief["id"])]
        jobs.append(
            {
                "brief_id": brief["id"],
                "genre": brief["genre"],
                "brief": brief["brief"],
                "audience": brief.get("audience", ""),
                "constraints": brief.get("constraints") or [],
                "blind_mapping": {"A": left, "B": right},
                "A": systems[left],
                "B": systems[right],
            }
        )
        diagnostics.append(
            {
                "brief_id": brief["id"],
                "genre": brief["genre"],
                "legacy_source_count": len(legacy.get("sources") or []),
                "engine_source_count": len(engine.get("sources") or []),
                "engine_reranker_state": engine["engine_metadata"]["reranker_state"],
            }
        )
    return {
        "schema_version": 1,
        "benchmark": "v1-retrieval-vs-engine-v3",
        "rag_root": str(rag_root),
        "brief_count": len(briefs),
        "generation_jobs": jobs,
        "diagnostics": diagnostics,
        "guardrails": {
            "same_rag_snapshot": True,
            "fixed_seed_per_brief": True,
            "utility_ledger_written": False,
            "learned_preference_claimed": False,
            "unblind_only_after_immutable_outputs": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--briefs", type=Path, default=DEFAULT_BRIEFS)
    parser.add_argument("--rag-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    briefs = list(json.loads(args.briefs.read_text(encoding="utf-8-sig")).get("briefs") or [])
    rag_root = vault_query.resolve_rag_root(args.rag_root)
    payload = run_benchmark(briefs, rag_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "briefs": len(briefs), "benchmark": payload["benchmark"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
