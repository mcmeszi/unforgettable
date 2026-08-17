#!/usr/bin/env python3
"""Prepare blind generation jobs and a separate key from a retrieval benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from generation_contracts import genre_quality_contract


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHEETS = SKILL_ROOT / "state" / "author-writing-sheets.json"


def _strip_private_ids(value):
    if isinstance(value, list):
        return [_strip_private_ids(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _strip_private_ids(item)
            for key, item in value.items()
            if key not in {"source_id", "source_ids", "evidence_family_ids"}
        }
    return value


def _compact_sheet(sheet: dict) -> dict:
    compact = {
        key: sheet[key]
        for key in (
            "genre",
            "confidence",
            "source_basis",
            "supported_claims",
            "range_axis_bands",
            "caricature_guards",
            "email_style",
            "prose_transfer",
        )
        if key in sheet
    }
    return _strip_private_ids(compact)


def _select_sources(portfolio: dict) -> list[dict]:
    sources = list(portfolio.get("sources") or [])
    content = [source for source in sources if source.get("retrieval_channel") == "content"]
    style = [source for source in sources if source.get("retrieval_channel") == "style"]
    selected = [*content[:2], *style[:2]] if content and style else sources[:4]
    return selected[:4]


def _blind_evidence(portfolio: dict) -> list[dict]:
    result = []
    for index, source in enumerate(_select_sources(portfolio), start=1):
        result.append(
            {
                "source_label": f"S{index}",
                "mode": source.get("mode"),
                "technique_tags": source.get("technique_tags") or [],
                "range_axes": source.get("range_axes") or {},
                "evidence": [
                    {"context": item.get("context", ""), "text": item.get("text", "")}
                    for item in (source.get("evidence") or [])[:2]
                ],
            }
        )
    return result


def build_generation_pack(retrieval: dict, writing_sheets: dict) -> tuple[list[dict], dict]:
    public_jobs = []
    blind_key = {}
    sheets = writing_sheets.get("sheets") or {}
    for row in retrieval.get("generation_jobs") or []:
        brief_id = str(row["brief_id"])
        blind_key[brief_id] = dict(row["blind_mapping"])
        sheet = _compact_sheet(sheets.get(str(row["genre"]), {}))
        for candidate in ("A", "B"):
            public_jobs.append(
                {
                    "job_id": f"{brief_id}-{candidate}",
                    "brief_id": brief_id,
                    "candidate": candidate,
                    "genre": row["genre"],
                    "brief": row["brief"],
                    "audience": row["audience"],
                    "constraints": row["constraints"],
                    "author_writing_sheet": sheet,
                    "evidence_sources": _blind_evidence(row[candidate]),
                    "genre_quality_contract": genre_quality_contract(str(row["genre"])),
                    "generation_contract": [
                        "A brief célja erősebb a stílusmutatványnál.",
                        "Forrásonként legfeljebb egy átvihető mechanikát használj.",
                        "Ne másolj felismerhető mondatot vagy ritka önéletrajzi adatot.",
                        "Ne nevezd meg a forrásokat, a rendszert vagy a benchmarkot.",
                        "Csak a kész szöveget add vissza háttérelemzés nélkül.",
                    ],
                }
            )
    return public_jobs, blind_key


def build_private_generation_manifest(retrieval: dict) -> dict:
    jobs = {}
    for row in retrieval.get("generation_jobs") or []:
        brief_id = str(row["brief_id"])
        mapping = row.get("blind_mapping") or {}
        for candidate in ("A", "B"):
            portfolio = row.get(candidate) or {}
            portfolio_source_ids = [
                str(source.get("id"))
                for source in portfolio.get("sources") or []
                if source.get("id")
            ]
            selected_sources = _select_sources(portfolio)
            source_ids = [str(source.get("id")) for source in selected_sources if source.get("id")]
            source_linkage = [
                {"source_label": f"S{index}", "id": str(source.get("id"))}
                for index, source in enumerate(selected_sources, start=1)
                if source.get("id")
            ]
            provided_run_id = portfolio.get("run_id")
            if provided_run_id:
                retrieval_run_id = str(provided_run_id)
                run_id_origin = "source-provided"
            else:
                fingerprint_payload = {
                    "brief_id": brief_id,
                    "candidate": candidate,
                    "genre": row.get("genre"),
                    "source_ids": portfolio_source_ids,
                }
                digest = hashlib.sha256(
                    json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest()[:20]
                retrieval_run_id = f"benchmark-portfolio-{digest}"
                run_id_origin = "derived-portfolio-fingerprint"
            jobs[f"{brief_id}-{candidate}"] = {
                "brief_id": brief_id,
                "candidate": candidate,
                "genre": row.get("genre"),
                "system": mapping.get(candidate),
                "retrieval_run_id": retrieval_run_id,
                "run_id_origin": run_id_origin,
                "source_ids": source_ids,
                "source_linkage": source_linkage,
                "portfolio_source_ids": portfolio_source_ids,
            }
    return {"schema_version": 1, "jobs": jobs}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--writing-sheets", type=Path, default=DEFAULT_SHEETS)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retrieval = json.loads(args.retrieval.read_text(encoding="utf-8-sig"))
    sheets = json.loads(args.writing_sheets.read_text(encoding="utf-8-sig"))
    public_jobs, blind_key = build_generation_pack(retrieval, sheets)
    private_manifest = build_private_generation_manifest(retrieval)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    jobs_path = args.output_dir / "generation-jobs.jsonl"
    key_path = args.output_dir / "blind-key.json"
    manifest_path = args.output_dir / "evaluation-manifest.json"
    private_manifest_path = args.output_dir / "private-generation-manifest.json"
    jobs_path.write_text("\n".join(json.dumps(job, ensure_ascii=False) for job in public_jobs) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(blind_key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    private_manifest_path.write_text(json.dumps(private_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "job_count": len(public_jobs),
        "brief_count": len(blind_key),
        "draft_contract": "Save one UTF-8 draft per job as drafts/<job_id>.md.",
        "evaluation_dimensions": [
            "brief_fidelity",
            "genre_naturalness",
            "author_style_match",
            "originality_anti_caricature",
        ],
        "judge_order": ["A/B", "B/A"],
        "unblind_only_after": "All draft and judge outputs are immutable.",
        "private_linkage_manifest": private_manifest_path.name,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"jobs": len(public_jobs), "briefs": len(blind_key), "output_dir": str(args.output_dir), "private_manifest": str(private_manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
