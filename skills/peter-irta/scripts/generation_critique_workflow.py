#!/usr/bin/env python3
"""Build reproducible generation and genre-critique jobs from an Engine v3 packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generation_contracts import genre_quality_contract, normalize_genre


EVALUATION_DIMENSIONS = {
    "brief_fidelity": "A brief tartalmi, terjedelmi és feladatbeli teljesülése.",
    "genre_naturalness": "A célműfajban természetes és használható szöveg.",
    "author_style_match": "Szerzői mechanika- és ritmusegyezés mondatmásolás nélkül.",
    "originality_anti_caricature": "Önálló megoldás Péter-manírok katalógusa nélkül.",
}

SUPPORTED_ENGINE_SCHEMAS = {
    "mind-vault-engine-packet/v1",
    "mind-vault-engine-packet/v2",
}


def _stable_digest(payload: dict) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:20]


def _execution_sources(packet: dict) -> list[dict]:
    return list(packet.get("evidence_compiler", {}).get("execution_evidence") or [])[:4]


def _engine_schema(packet: dict, *, require_explicit: bool = False) -> str:
    schema = packet.get("schema")
    if schema is None or schema == "":
        if require_explicit:
            raise ValueError("Engine packet must declare an explicit supported schema")
        return "mind-vault-engine-packet/v1"
    if not isinstance(schema, str) or schema not in SUPPORTED_ENGINE_SCHEMAS:
        raise ValueError(f"Unsupported Engine packet schema: {schema}")
    return schema


def _curated_evidence(packet: dict) -> tuple[list[dict], list[dict]]:
    selected = packet.get("selected_evidence") or {}
    fields = ("evidence_id", "genre", "scope", "directive", "level", "confidence")
    mechanisms = [
        {key: item.get(key) for key in fields if item.get(key) is not None}
        for item in selected.get("mechanisms") or []
    ]
    guards = [
        {key: item.get(key) for key in fields if item.get(key) is not None}
        for item in selected.get("guards") or []
    ]
    return mechanisms, guards


def _public_evidence(packet: dict) -> list[dict]:
    evidence = []
    for index, source in enumerate(_execution_sources(packet), start=1):
        raw_tags = source.get("technique_tags") or []
        technique_tags = [raw_tags] if isinstance(raw_tags, str) else list(raw_tags)
        mechanism = str(source.get("mechanism") or "").strip()
        if not technique_tags and mechanism:
            technique_tags = [mechanism]
        primary_mechanism = mechanism or (str(technique_tags[0]) if technique_tags else "")
        transfer_instruction = str(source.get("transfer_instruction") or "").strip()
        if not transfer_instruction and primary_mechanism:
            transfer_instruction = (
                f"Transfer the {primary_mechanism} mechanism without copying source wording."
            )
        evidence.append(
            {
                "source_label": f"S{index}",
                "channel": source.get("channel") or source.get("retrieval_channel"),
                "technique_tags": technique_tags,
                "transfer_instruction": transfer_instruction,
                "evidence": source.get("evidence") or [],
            }
        )
    return evidence


def build_workflow(packet: dict, variation_seed: str = "") -> tuple[dict, dict]:
    engine_schema = _engine_schema(packet)
    plan = packet.get("brief_plan") or {}
    genre = normalize_genre(str((plan.get("genre") or {}).get("value") or ""))
    if not genre:
        raise ValueError("Engine packet has no brief_plan.genre.value")
    contract = genre_quality_contract(genre)
    critique_contract = genre_quality_contract(genre)
    curated_mechanisms, curated_guards = _curated_evidence(packet)
    critique_contract["release_checks"].extend(
        {
            "id": f"curated:{guard['evidence_id']}",
            "question": guard.get("directive", ""),
            "hard": True,
        }
        for guard in curated_guards
        if guard.get("level") == "hard"
    )
    public_evidence = _public_evidence(packet)
    seed = variation_seed or str(packet.get("retrieval", {}).get("variation_seed") or "default")
    identity = {
        "schema": 1,
        "brief": plan.get("brief", ""),
        "genre": genre,
        "seed": seed,
        "evidence": public_evidence,
        "curated_mechanisms": curated_mechanisms,
        "curated_guards": curated_guards,
        "contract": contract,
    }
    workflow_id = f"generation-critique-{_stable_digest(identity)}"
    reranker = packet.get("preference_reranker") or {}
    public = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "variation_seed": seed,
        "generation_job": {
            "job_id": f"{workflow_id}-generate",
            "brief": plan.get("brief", ""),
            "genre": genre,
            "purpose": (plan.get("purpose") or {}).get("value", ""),
            "audience": (plan.get("audience") or {}).get("value", ""),
            "negative_preferences": plan.get("negative_preferences") or [],
            "evidence_sources": public_evidence,
            "curated_mechanisms": curated_mechanisms,
            "curated_guards": curated_guards,
            "dialogue_calibration": (packet.get("channels") or {}).get("dialogue") or {},
            "generation_contract": packet.get("evidence_compiler", {}).get("generation_contract") or {},
            "genre_quality_contract": contract,
            "required_output": "A kész draft szövege, háttérelemzés és forráshivatkozás nélkül.",
        },
        "critique_job": {
            "job_id": f"{workflow_id}-critique",
            "input_contract": "A generation_job draftja változtatás nélkül.",
            "genre": genre,
            "curated_mechanisms": curated_mechanisms,
            "curated_guards": curated_guards,
            "dimensions": EVALUATION_DIMENSIONS,
            "genre_quality_contract": critique_contract,
            "required_output": [
                "dimension_scores",
                "hard_guard_failures",
                "decisive_revision_notes",
                "release_verdict",
            ],
            "release_rule": "Kemény műfaji hiba esetén revise; a hibát nem szabad átlagponttal elfedni.",
        },
        "feedback_contract": {
            "record_only_after_human_verdict": True,
            "accepted_verdicts": ["accepted", "rejected", "mixed"],
            "store_raw_brief_or_draft": False,
        },
    }
    private = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "engine_packet_schema": engine_schema,
        "evidence_policy_version": (packet.get("evidence_policy") or {}).get("policy_version"),
        "evidence_ledger_sha256": (packet.get("evidence_policy") or {}).get("ledger_sha256"),
        "engine_run_id": (
            packet.get("retrieval_run_id")
            or packet.get("retrieval", {}).get("run_id")
            or packet.get("source_trace", {}).get("run_id")
        ),
        "reranker_state": reranker.get("state", "cold-start"),
        "learned_preference_claimed": False,
        "source_linkage": [
            {"source_label": f"S{index}", "id": str(source.get("id"))}
            for index, source in enumerate(_execution_sources(packet), start=1)
            if source.get("id")
        ],
    }
    return public, private


def attach_draft(workflow: dict, draft: str) -> dict:
    result = json.loads(json.dumps(workflow, ensure_ascii=False))
    result["critique_job"]["draft"] = draft
    result["critique_job"]["draft_sha256"] = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-packet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--variation-seed", default="")
    parser.add_argument("--draft", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    packet = json.loads(args.engine_packet.read_text(encoding="utf-8-sig"))
    try:
        _engine_schema(packet, require_explicit=True)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    workflow, private = build_workflow(packet, args.variation_seed)
    if args.draft:
        workflow = attach_draft(workflow, args.draft.read_text(encoding="utf-8-sig"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    public_path = args.output_dir / "generation-critique-job.json"
    private_path = args.output_dir / "private-generation-manifest.json"
    public_path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_path.write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"workflow_id": workflow["workflow_id"], "job": str(public_path), "private_manifest": str(private_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
