#!/usr/bin/env python3
"""Build provenance-safe, genre-specific Author Writing Sheets from the Mind Vault."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

import vault_query


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "state" / "author-writing-sheets.json"
DEFAULT_EMAIL_PROFILE = Path(__file__).resolve().parents[1] / "state" / "email-writing-profile.json"
DEFAULT_SLACK_PROFILE = Path(__file__).resolve().parents[1] / "state" / "slack-dialogue-profile.json"
SHEET_GENRES = ("slam", "vers", "dalszoveg", "proza", "cikk", "tanulmany", "prezentacio", "reklam", "beszed", "email")
SHEET_SOURCE_HINTS = {
    "slam": ("slam", "spoken-word"),
    "vers": ("poem", "poetry", "creative-fragment", "interactive-poetry"),
    "dalszoveg": ("lyrics",),
    "proza": ("novella", "literary-prose", "interactive-prose", "literary-fragment"),
    "cikk": ("authored-web-article", "literary-essay", "essay/study"),
    "tanulmany": ("essay/study", "study"),
    "prezentacio": ("presentation",),
    "reklam": ("commercial", "script"),
    "beszed": ("speech",),
    "email": ("email", "e-mail"),
}
SHEET_ADJACENT_HINTS = {
    "email": ("professional/other", "commercial/professional", "bio"),
}
CARICATURE_GUARDS = {
    "slam": ["A beszélhetőség nem jelent kötelező kérdéshalmozást vagy állandó hangerőt."],
    "vers": ["A képiség nem jelent minden sorban metaforát vagy sortördelt prózát."],
    "dalszoveg": ["Az ismétlés csak akkor indokolt, ha zeneileg vagy jelentésben fokoz."],
    "proza": ["Az önirónia nem oldhatja fel automatikusan a jelenet tétjét."],
    "cikk": ["A hang nem helyettesítheti a bizonyítást vagy a forrást."],
    "tanulmany": ["A retorikai csattanó nem írhatja felül a fogalmi pontosságot."],
    "prezentacio": ["Az emlékezetes headline nem lehet minden dián szóvicc."],
    "reklam": ["A szójáték csak insightot tömöríthet; önmagában nem stratégia."],
    "beszed": ["Az élő ritmus nem jelent folyamatos emelkedettséget."],
    "email": ["Egy személyes csavar elég; a funkcionális email ne váljon mini slammé."],
}

SLACK_DIALOGUE_TRANSFER = {
    "email": "strong",
    "prezentacio": "strong",
    "reklam": "strong",
    "cikk": "strong",
    "tanulmany": "strong",
    "beszed": "strong",
    "proza": "conditional",
    "slam": "conditional",
    "vers": "dialogue-only",
    "dalszoveg": "dialogue-only",
}


def _document_priority(document: dict) -> tuple[float, int, str]:
    return (
        vault_query.DECISION_WEIGHT.get(str(document.get("decision", "")), 0.0)
        + vault_query.AUTHORITY_WEIGHT.get(str(document.get("authority", "")), 0.0),
        int(document.get("word_count") or 0),
        str(document.get("title", "")),
    )


def _unique_families(candidates: list[tuple[dict, dict]]) -> list[tuple[dict, dict]]:
    selected: list[tuple[dict, dict]] = []
    for document, profile in sorted(candidates, key=lambda item: _document_priority(item[0]), reverse=True):
        if any(vault_query.same_work_family(document, profile, old_doc, old_profile) for old_doc, old_profile in selected):
            continue
        selected.append((document, profile))
    return selected


def _bands(profiles: list[dict], field: str) -> dict:
    if not profiles:
        return {}
    keys = profiles[0][field].keys()
    return {
        key: {
            "min": round(min(float(profile[field][key]) for profile in profiles), 3),
            "median": round(statistics.median(float(profile[field][key]) for profile in profiles), 3),
            "max": round(max(float(profile[field][key]) for profile in profiles), 3),
        }
        for key in keys
    }


def _supported_claims(families: list[tuple[dict, dict]]) -> list[dict]:
    if len(families) < 3:
        return []
    tag_sources: dict[str, list[str]] = {}
    for document, profile in families:
        for tag in profile.get("technique_tags", []):
            tag_sources.setdefault(tag, []).append(str(document.get("id")))
    claims = []
    for tag, source_ids in sorted(tag_sources.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(source_ids) < 3:
            continue
        claims.append(
            {
                "signal": tag,
                "source_count": len(source_ids),
                "source_ratio": round(len(source_ids) / len(families), 3),
                "evidence_family_ids": source_ids[:5],
            }
        )
    return claims[:8]


def build_sheets(
    documents: list[dict],
    chunks: list[dict],
    target_genres: tuple[str, ...] = SHEET_GENRES,
    email_profile: dict | None = None,
    slack_profile: dict | None = None,
) -> dict:
    profiled = [
        (document, vault_query.source_profile(document, chunks))
        for document in documents
        if vault_query.style_eligible(document)
    ]
    sheets = {}
    for target in target_genres:
        direct_hints = SHEET_SOURCE_HINTS.get(target, vault_query.GENRE_HINTS.get(target, (target,)))
        direct = [
            (document, profile)
            for document, profile in profiled
            if vault_query.genre_matches(str(document.get("genre", "")), direct_hints)
        ]
        families = _unique_families(direct)
        source_basis = "direct"
        if len(families) < 3 and target in SHEET_ADJACENT_HINTS:
            adjacent = [
                (document, profile)
                for document, profile in profiled
                if vault_query.genre_matches(str(document.get("genre", "")), SHEET_ADJACENT_HINTS[target])
            ]
            families = _unique_families(direct + adjacent)
            source_basis = "adjacent"
        profiles = [profile for _, profile in families]
        evidence = [
            {
                "id": document.get("id"),
                "title": document.get("title"),
                "genre": document.get("genre"),
                "authority": document.get("authority"),
                "decision": document.get("decision"),
            }
            for document, _ in families[:5]
        ]
        mode_counts = Counter(profile.get("mode", "unknown") for profile in profiles)
        confidence = "insufficient" if len(families) < 3 else "adjacent" if source_basis == "adjacent" else "supported"
        sheets[target] = {
            "genre": target,
            "confidence": confidence,
            "source_basis": source_basis,
            "fallback_required": len(families) < 3,
            "evidence_family_count": len(families),
            "evidence_families": evidence,
            "supported_claims": _supported_claims(families),
            "mode_distribution": dict(sorted(mode_counts.items())),
            "range_axis_bands": _bands(profiles, "range_axes"),
            "style_metric_bands": _bands(profiles, "style_metrics"),
            "contrast_note": "A sávok Péter hiteles műfaji tartományát jelzik; az új briefnek nem kell a mediánra esnie.",
            "caricature_guards": CARICATURE_GUARDS.get(target, []),
        }
        if target == "email" and email_profile and int((email_profile.get("sample") or {}).get("usable") or 0) >= 20:
            sheets[target].update(
                {
                    "confidence": "supported",
                    "source_basis": "direct-email-corpus",
                    "fallback_required": False,
                    "evidence_family_count": int(email_profile["sample"]["usable"]),
                    "evidence_families": email_profile.get("representative_evidence") or [],
                    "email_style": email_profile.get("email_style") or {},
                    "prose_transfer": email_profile.get("prose_transfer") or {},
                }
            )
        if slack_profile and int((slack_profile.get("sample") or {}).get("usable") or 0) >= 100:
            sheets[target]["dialogue_support"] = {
                "confidence": "supported",
                "role": "secondary-dialogue-evidence",
                "transfer_strength": SLACK_DIALOGUE_TRANSFER.get(target, "conditional"),
                "sample_size": int(slack_profile["sample"]["usable"]),
                "strong_for": (slack_profile.get("dialogue_mechanics") or {}).get("strong_for") or [],
                "weak_for": (slack_profile.get("dialogue_mechanics") or {}).get("weak_for") or [],
                "precedence": (slack_profile.get("calibration_policy") or {}).get("precedence"),
                "guardrails": slack_profile.get("guardrails") or [],
            }
    return {
        "schema_version": 1,
        "source_document_count": len(documents),
        "style_eligible_document_count": len(profiled),
        "sheets": sheets,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--genre", action="append", default=[])
    parser.add_argument("--email-profile", type=Path, default=DEFAULT_EMAIL_PROFILE)
    parser.add_argument("--slack-profile", type=Path, default=DEFAULT_SLACK_PROFILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rag_root = vault_query.resolve_rag_root(args.rag_root)
    documents = list(vault_query.load_json(rag_root / "documents.json").get("documents") or [])
    chunks = list(vault_query.load_json(rag_root / "chunks.json").get("chunks") or [])
    email_profile = (
        json.loads(args.email_profile.read_text(encoding="utf-8-sig"))
        if args.email_profile.is_file()
        else None
    )
    slack_profile = (
        json.loads(args.slack_profile.read_text(encoding="utf-8-sig"))
        if args.slack_profile.is_file()
        else None
    )
    payload = build_sheets(
        documents,
        chunks,
        tuple(args.genre) if args.genre else SHEET_GENRES,
        email_profile=email_profile,
        slack_profile=slack_profile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sheets": len(payload["sheets"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
