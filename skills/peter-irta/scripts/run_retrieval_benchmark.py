#!/usr/bin/env python3
"""Run a blind, retrieval-only V1 versus V2 benchmark on the Mind Vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

import vault_query


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEFS = SKILL_ROOT / "references" / "benchmark-briefs.json"
DEFAULT_OUTPUT = SKILL_ROOT / "state" / "retrieval-benchmark-latest.json"


def balanced_blind_labels(briefs: list[dict]) -> dict[str, tuple[str, str]]:
    brief_ids = sorted(str(brief["id"]) for brief in briefs)
    cohort = "\n".join(brief_ids)
    start = int(hashlib.sha256(cohort.encode("utf-8")).hexdigest()[:8], 16) % 2
    options = (("legacy", "v2"), ("v2", "legacy"))
    return {brief_id: options[(index + start) % 2] for index, brief_id in enumerate(brief_ids)}


def build_family_groups(profiled: list[tuple[dict, dict]]) -> dict[str, str]:
    parents = {str(document.get("id")): str(document.get("id")) for document, _ in profiled}

    def find(item: str) -> str:
        while parents[item] != item:
            parents[item] = parents[parents[item]]
            item = parents[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    owner_by_key: dict[str, str] = {}
    for document, _ in profiled:
        source_id = str(document.get("id"))
        keys = {
            *vault_query.family_keys(document),
            *(f"signature:{value}" for value in vault_query.title_family_signatures(str(document.get("title", "")))),
        }
        for key in keys:
            if key in owner_by_key:
                union(source_id, owner_by_key[key])
            else:
                owner_by_key[key] = source_id
    return {source_id: find(source_id) for source_id in parents}


def benchmark_select(
    candidates: list[tuple[float, dict, dict]],
    limit: int,
    preferred: tuple[str, ...],
    target_same_genre: int,
    family_groups: dict[str, str],
) -> list[tuple[float, dict, dict, float]]:
    selected: list[tuple[float, dict, dict, float]] = []
    used_groups: set[str] = set()
    remaining = list(candidates)
    maximum = max((score for score, _, _ in candidates), default=1.0)
    while remaining and len(selected) < limit:
        same_count = sum(vault_query.genre_matches(str(item[1].get("genre", "")), preferred) for item in selected)
        require_same = bool(preferred) and same_count < target_same_genre
        pool = [item for item in remaining if not require_same or vault_query.genre_matches(str(item[1].get("genre", "")), preferred)] or remaining
        scored = []
        for relevance, document, profile in pool:
            group = family_groups[str(document.get("id"))]
            if group in used_groups:
                continue
            similarity = max(
                (vault_query.jaccard(profile["feature_tokens"], chosen[2]["feature_tokens"]) for chosen in selected),
                default=0.0,
            )
            covered = {tag for chosen in selected for tag in chosen[2]["technique_tags"]}
            new_tags = len(set(profile["technique_tags"]) - covered)
            score = (relevance / maximum) * 5.2 + (1.0 - similarity) * 3.2 + min(3, new_tags) * 0.42
            scored.append((score, relevance, document, profile))
        if not scored:
            break
        diversity, relevance, document, profile = max(
            scored,
            key=lambda item: (item[0], item[1], int(item[2].get("word_count") or 0), str(item[2].get("title", ""))),
        )
        selected.append((relevance, document, profile, round(diversity, 4)))
        used_groups.add(family_groups[str(document.get("id"))])
        remaining = [item for item in remaining if item[1] is not document]
    return selected


def benchmark_style_supplements(
    candidates: list[tuple[float, dict, dict]],
    already_selected: list[tuple[float, dict, dict, float]],
    limit: int,
    family_groups: dict[str, str],
) -> list[tuple[float, dict, dict, float]]:
    supplements: list[tuple[float, dict, dict, float]] = []
    remaining = list(candidates)
    maximum = max((score for score, _, _ in candidates), default=1.0)
    used_groups = {
        family_groups[str(item[1].get("id"))]
        for item in already_selected
        if str(item[1].get("id")) in family_groups
    }
    while remaining and len(supplements) < limit:
        comparison = [*already_selected, *supplements]
        covered_tags = {tag for item in comparison for tag in item[2].get("technique_tags", [])}
        scored = []
        for fit, document, profile in remaining:
            group = family_groups[str(document.get("id"))]
            if group in used_groups:
                continue
            similarity = max(
                (vault_query.jaccard(profile.get("feature_tokens", set()), item[2].get("feature_tokens", set())) for item in comparison),
                default=0.0,
            )
            new_tags = len(set(profile.get("technique_tags", [])) - covered_tags)
            selection_score = (fit / maximum) * 5.0 + (1.0 - similarity) * 3.0 + min(3, new_tags) * 0.6
            scored.append((selection_score, fit, document, profile))
        if not scored:
            break
        selection_score, fit, document, profile = max(scored, key=lambda item: (item[0], item[1], str(item[2].get("title", ""))))
        supplements.append((fit, document, profile, round(selection_score, 4)))
        used_groups.add(family_groups[str(document.get("id"))])
        remaining = [item for item in remaining if item[1] is not document]
    return supplements


def _blocked(source: dict) -> bool:
    return (
        str(source.get("decision", "")) in {"reference-only", "exclude"}
        or str(source.get("content_level", "")) in vault_query.BLOCKED_CONTENT_LEVELS
        or str(source.get("authority", "")) in vault_query.BLOCKED_AUTHORITIES
    )


def portfolio_diagnostics(portfolio: dict, genre: str) -> dict:
    sources = list(portfolio.get("sources") or [])
    preferred = vault_query.GENRE_HINTS.get(vault_query.normalize(genre), (vault_query.normalize(genre),))
    unique: list[dict] = []
    duplicates = 0
    for source in sources:
        if any(vault_query.same_title_family(str(source.get("title", "")), str(old.get("title", ""))) for old in unique):
            duplicates += 1
        else:
            unique.append(source)
    techniques = {tag for source in sources for tag in source.get("technique_tags", [])}
    modes = {str(source.get("mode", "")) for source in sources if source.get("mode")}
    return {
        "source_count": len(sources),
        "unique_family_count": len(unique),
        "duplicate_families": duplicates,
        "blocked_sources": sum(_blocked(source) for source in sources),
        "same_genre_sources": sum(
            vault_query.genre_matches(str(source.get("genre", "")), preferred) for source in sources
        ),
        "primary_authority_ratio": round(
            sum(str(source.get("authority", "")) in vault_query.PRIMARY_STYLE_AUTHORITIES for source in sources)
            / max(1, len(sources)),
            3,
        ),
        "technique_count": len(techniques),
        "mode_count": len(modes),
        "content_channel_count": sum(source.get("retrieval_channel") == "content" for source in sources),
        "style_channel_count": sum(source.get("retrieval_channel") == "style" for source in sources),
    }


def summarize_results(results: list[dict]) -> dict:
    metrics = (
        "blocked_sources",
        "unique_family_count",
        "duplicate_families",
        "same_genre_sources",
        "primary_authority_ratio",
        "technique_count",
        "mode_count",
    )
    systems = {}
    for system in ("legacy", "v2"):
        systems[system] = {
            metric: round(statistics.mean(float(row[system].get(metric, 0.0)) for row in results), 3)
            for metric in metrics
        } if results else {metric: 0.0 for metric in metrics}
    return {
        "brief_count": len(results),
        "conclusion_scope": "retrieval-diagnostics-only",
        "generation_evaluation_required": True,
        "systems": systems,
        "v2_minus_legacy": {
            metric: round(systems["v2"][metric] - systems["legacy"][metric], 3)
            for metric in metrics
        },
        "warning": "Retrieval diagnostics cannot establish which system writes more like Peter.",
    }


def _brief_context(brief: dict) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], dict[str, float], int]:
    genre = vault_query.normalize(str(brief["genre"]))
    preferred = vault_query.GENRE_HINTS.get(genre, (genre,))
    query_terms = vault_query.terms(str(brief.get("query", "")))
    title_hints = vault_query.GENRE_TITLE_HINTS.get(genre, ())
    target_axes = {axis: float(value) for axis, value in brief["target_axes"].items()}
    return genre, preferred, query_terms, title_hints, target_axes, vault_query.default_limit(genre)


def _source(document: dict, profile: dict, channel: str, content_score: float, style_score: float, fused_score: float, chunks: list[dict], query_terms: tuple[str, ...]) -> dict:
    return {
        "id": document.get("id"),
        "title": document.get("title"),
        "genre": document.get("genre"),
        "decision": document.get("decision"),
        "authority": document.get("authority"),
        "content_level": document.get("content_level"),
        "retrieval_channel": channel,
        "content_score": round(content_score, 4),
        "style_score": round(style_score, 4),
        "fused_score": round(fused_score, 8),
        "mode": profile.get("mode"),
        "technique_tags": profile.get("technique_tags") or [],
        "range_axes": profile.get("range_axes") or {},
        "evidence": vault_query.choose_chunks(document, chunks, query_terms, 2),
    }


def retrieve_pair(
    brief: dict,
    profiled: list[tuple[dict, dict]],
    chunks: list[dict],
    family_groups: dict[str, str],
) -> dict:
    genre, preferred, query_terms, title_hints, target_axes, limit = _brief_context(brief)
    eligible = list(profiled)
    content_scores = {
        str(document.get("id")): vault_query.content_relevance(document, preferred, query_terms, title_hints)
        for document, _ in eligible
    }
    style_scores = {
        str(document.get("id")): vault_query.style_relevance(profile, preferred, str(document.get("genre", "")), target_axes)
        for document, profile in eligible
    }
    content_ranked = sorted(
        [(content_scores[str(document.get("id"))], document, profile) for document, profile in eligible],
        key=lambda item: (-item[0], -int(item[1].get("word_count") or 0), str(item[1].get("title", ""))),
    )
    legacy_selected = benchmark_select(
        content_ranked,
        limit,
        preferred,
        min(math.ceil(limit * (0.6 if genre in vault_query.CREATIVE_TARGETS else 0.7)), sum(vault_query.genre_matches(str(item[1].get("genre", "")), preferred) for item in content_ranked)),
        family_groups,
    )
    legacy_sources = [
        _source(document, profile, "legacy", score, style_scores[str(document.get("id"))], 0.0, chunks, query_terms)
        for score, document, profile, _ in legacy_selected
    ]

    style_order = sorted(
        eligible,
        key=lambda item: (-style_scores[str(item[0].get("id"))], -content_scores[str(item[0].get("id"))], str(item[0].get("title", ""))),
    )
    fused = vault_query.reciprocal_rank_fusion(
        [
            [str(document.get("id")) for _, document, _ in content_ranked],
            [str(document.get("id")) for document, _ in style_order],
        ]
    )
    content_target = max(1, math.ceil(limit * 0.55))
    selected = benchmark_select(
        content_ranked,
        content_target,
        preferred,
        min(content_target, sum(vault_query.genre_matches(str(item[1].get("genre", "")), preferred) for item in content_ranked)),
        family_groups,
    )
    selected_docs = [(document, profile, "content") for _, document, profile, _ in selected]
    selected_ids = {str(document.get("id")) for document, _, _ in selected_docs}
    style_candidates = [
        (style_scores[str(document.get("id"))], document, profile)
        for document, profile in style_order
        if str(document.get("id")) not in selected_ids
    ]
    supplements = benchmark_style_supplements(
        style_candidates,
        selected,
        max(0, limit - content_target),
        family_groups,
    )
    selected_docs.extend((document, profile, "style") for _, document, profile, _ in supplements)
    v2_sources = [
        _source(
            document,
            profile,
            channel,
            content_scores[str(document.get("id"))],
            style_scores[str(document.get("id"))],
            fused.get(str(document.get("id")), 0.0),
            chunks,
            query_terms,
        )
        for document, profile, channel in selected_docs
    ]
    return {"legacy": {"sources": legacy_sources}, "v2": {"sources": v2_sources}}


def run_benchmark(briefs: list[dict], rag_root: Path) -> dict:
    documents = list(vault_query.load_json(rag_root / "documents.json").get("documents") or [])
    chunks = list(vault_query.load_json(rag_root / "chunks.json").get("chunks") or [])
    profiled = [(document, vault_query.source_profile(document, chunks)) for document in documents if vault_query.style_eligible(document)]
    family_groups = build_family_groups(profiled)
    label_map = balanced_blind_labels(briefs)
    rows = []
    generation_jobs = []
    for brief in briefs:
        pair = retrieve_pair(brief, profiled, chunks, family_groups)
        labels = label_map[str(brief["id"])]
        diagnostics = {system: portfolio_diagnostics(pair[system], str(brief["genre"])) for system in ("legacy", "v2")}
        rows.append({"brief_id": brief["id"], "genre": brief["genre"], **diagnostics})
        generation_jobs.append(
            {
                "brief_id": brief["id"],
                "genre": brief["genre"],
                "brief": brief["brief"],
                "audience": brief["audience"],
                "constraints": brief["constraints"],
                "blind_mapping": {"A": labels[0], "B": labels[1]},
                "A": pair[labels[0]],
                "B": pair[labels[1]],
            }
        )
    return {
        "schema_version": 1,
        "rag_root": str(rag_root),
        "brief_count": len(briefs),
        "summary": summarize_results(rows),
        "results": rows,
        "generation_jobs": generation_jobs,
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
    print(json.dumps({"output": str(args.output), "briefs": len(briefs), "summary": payload["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
