#!/usr/bin/env python3
"""Compile a brief-specific Mind Vault evidence packet without an MCP layer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

from evidence_vault import load_policy, project_state, read_jsonl, select_evidence


SKILL_ROOT = Path(__file__).resolve().parents[1]
VAULT_QUERY = SKILL_ROOT / "scripts" / "vault_query.py"
AUTHOR_SHEETS = SKILL_ROOT / "state" / "author-writing-sheets.json"
EVIDENCE_LEDGER = SKILL_ROOT / "state" / "evidence-vault" / "evidence.jsonl"
DECISION_LEDGER = SKILL_ROOT / "state" / "evidence-vault" / "decisions.jsonl"
EVIDENCE_POLICY = SKILL_ROOT / "references" / "evidence-policy.json"
ENGINE_SCHEMA = "mind-vault-engine-packet/v2"

GENRE_ALIASES = {
    "beszed": ("beszéd", "speech", "előadás", "előadói"),
    "cikk": ("cikk", "article", "blogposzt", "esszé"),
    "dalszoveg": ("dalszöveg", "dal", "lyrics", "refrén"),
    "email": ("email", "e-mail", "levél", "válaszlevél"),
    "prezentacio": ("prezentáció", "prezi", "deck", "slide"),
    "proza": ("próza", "novella", "elbeszélés", "jelenet"),
    "reklam": ("reklám", "kampány", "szlogen", "headline", "copy"),
    "slam": ("slam", "spoken word", "színpadi vers"),
    "tanulmany": ("tanulmány", "kutatás", "elemzés", "whitepaper"),
    "vers": ("vers", "poem", "líra"),
}

DIALOGUE_MARKERS = (
    "dialógus", "párbeszéd", "válasz", "kérdés", "ellenvetés", "megszólítás",
    "feedback", "visszajelzés", "reakció", "beszélgetés", "email", "e-mail",
)
PURPOSE_MARKERS = {
    "meggyőzés": ("győzz", "meggyőz", "érvel", "pitch", "elad"),
    "tájékoztatás": ("tájékoztat", "összefoglal", "bemutat", "magyaráz"),
    "cselekvés": ("jelentkez", "kattint", "válaszol", "dönts", "következő lépés"),
    "érzelmi hatás": ("meghat", "érzelmi", "személyes", "intim"),
}
AUDIENCE_PATTERNS = (
    re.compile(r"(?:közönség|célcsoport|olvasó|hallgató)\s*[:=-]\s*([^.;\n]+)", re.I),
    re.compile(r"(?:számára|részére)\s+([^.;\n]+)", re.I),
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in value if not unicodedata.combining(char)).casefold()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def infer_genre(brief: str, explicit: str = "") -> tuple[str, str]:
    if explicit.strip():
        return normalize(explicit).replace(" ", ""), "explicit"
    haystack = normalize(brief)
    for genre, aliases in GENRE_ALIASES.items():
        if any(normalize(alias) in haystack for alias in aliases):
            return genre, "inferred"
    return "", "missing"


def infer_purpose(brief: str, explicit: str = "") -> tuple[str, str]:
    if explicit.strip():
        return explicit.strip(), "explicit"
    haystack = normalize(brief)
    for purpose, markers in PURPOSE_MARKERS.items():
        if any(normalize(marker) in haystack for marker in markers):
            return purpose, "inferred"
    return "", "missing"


def infer_audience(brief: str, explicit: str = "") -> tuple[str, str]:
    if explicit.strip():
        return explicit.strip(), "explicit"
    for pattern in AUDIENCE_PATTERNS:
        match = pattern.search(brief)
        if match:
            return match.group(1).strip(), "inferred"
    return "", "missing"


def extract_negative_preferences(brief: str) -> list[str]:
    results: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", brief):
        normalized = normalize(sentence)
        if any(marker in normalized for marker in ("ne legyen", "ne hasznal", "keruld", "nelkul", "nem akar")):
            cleaned = " ".join(sentence.split()).strip(" -")
            if cleaned and cleaned not in results:
                results.append(cleaned)
    return results[:8]


def plan_brief(
    brief: str,
    *,
    genre: str = "",
    purpose: str = "",
    audience: str = "",
    query: str = "",
    dialogue_mode: str = "auto",
    target_axes: dict[str, float] | None = None,
) -> dict:
    planned_genre, genre_origin = infer_genre(brief, genre)
    planned_purpose, purpose_origin = infer_purpose(brief, purpose)
    planned_audience, audience_origin = infer_audience(brief, audience)
    normalized_brief = normalize(brief)
    dialogue_signal = any(normalize(marker) in normalized_brief for marker in DIALOGUE_MARKERS)
    if dialogue_mode == "required":
        dialogue_need, dialogue_origin = True, "explicit"
    elif dialogue_mode == "off":
        dialogue_need, dialogue_origin = False, "explicit"
    else:
        dialogue_need, dialogue_origin = dialogue_signal, "inferred"
    return {
        "brief": brief.strip(),
        "genre": {"value": planned_genre, "origin": genre_origin},
        "purpose": {"value": planned_purpose, "origin": purpose_origin},
        "audience": {"value": planned_audience, "origin": audience_origin},
        "query": {"value": query.strip() or brief.strip(), "origin": "explicit" if query.strip() else "brief-derived"},
        "dialogue_need": {"value": dialogue_need, "origin": dialogue_origin},
        "target_axes": target_axes or {},
        "negative_preferences": extract_negative_preferences(brief),
        "missing_fields": [
            field
            for field, value in (
                ("genre", planned_genre),
                ("purpose", planned_purpose),
                ("audience", planned_audience),
            )
            if not value
        ],
    }


def dialogue_channel(writing_sheet: dict, plan: dict) -> dict:
    support = writing_sheet.get("dialogue_support") or {}
    strength = str(support.get("transfer_strength", "none"))
    explicit_need = bool(plan["dialogue_need"]["value"])
    active = strength == "strong" or (strength in {"conditional", "dialogue-only"} and explicit_need)
    reason = {
        "strong": "genre-level secondary calibration",
        "conditional": "brief contains a dialogue or response situation" if explicit_need else "brief has no dialogue signal",
        "dialogue-only": "explicit dialogue fragment only" if explicit_need else "disabled outside an explicit dialogue fragment",
    }.get(strength, "no supported dialogue transfer")
    return {
        "active": active,
        "role": "secondary-calibration-only",
        "transfer_strength": strength,
        "reason": reason,
        "mechanics": list(support.get("strong_for") or []) if active else [],
        "weak_for": list(support.get("weak_for") or []),
        "precedence": support.get("precedence", "direct genre evidence first"),
        "privacy": "Aggregated Slack signals only; no raw message text is retrieved or copied.",
    }


def rerank_execution_sources(portfolio: dict) -> dict:
    source_by_id = {str(source.get("id")): source for source in portfolio.get("sources") or []}
    execution = (portfolio.get("contrastive_calibration") or {}).get("execution_set") or []
    ranked: list[dict] = []
    observed = 0
    for original_rank, item in enumerate(execution, start=1):
        source = source_by_id.get(str(item.get("id")), {})
        technique_tags = list(source.get("technique_tags") or ["brief-specific mechanism"])
        mechanism = technique_tags[0]
        transfer_instruction = str(
            source.get("transfer_instruction")
            or item.get("transfer_instruction")
            or item.get("use")
            or f"Transfer the {mechanism} mechanism without copying source wording."
        )
        utility = max(-0.75, min(0.75, float(source.get("utility_weight") or 0.0)))
        observed += int(abs(utility) > 0.0)
        distance = max(0.0, float(item.get("distance") or 0.0))
        fit = 1.0 / (1.0 + distance)
        preference_score = fit + utility * 0.20
        ranked.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "channel": source.get("retrieval_channel", "content"),
                "portfolio_role": source.get("portfolio_role"),
                "mechanism": mechanism,
                "technique_tags": technique_tags,
                "transfer_instruction": transfer_instruction,
                "fit_score": round(fit, 4),
                "utility_weight": round(utility, 4),
                "preference_score": round(preference_score, 4),
                "original_rank": original_rank,
                "evidence": list(source.get("evidence") or []),
            }
        )
    ranked.sort(key=lambda item: (-item["preference_score"], item["original_rank"]))
    return {
        "state": "observed" if observed else "cold-start",
        "policy": "brief fit first; genre-specific outcome utility is shrinkage-capped and may only break close calls",
        "utility_weighted_sources": observed,
        "ranked": ranked,
    }


def negative_channel(portfolio: dict, writing_sheet: dict, plan: dict, dialogue: dict) -> dict:
    contrast = (portfolio.get("contrastive_calibration") or {}).get("contrast_set") or []
    guards = list(writing_sheet.get("caricature_guards") or [])
    guards.extend(plan.get("negative_preferences") or [])
    if dialogue.get("active"):
        guards.extend((writing_sheet.get("dialogue_support") or {}).get("guardrails") or [])
    return {
        "contrast_sources": contrast,
        "guards": list(dict.fromkeys(str(item) for item in guards if str(item).strip())),
        "interpretation": "Contrast sources map Peter's valid range; they are not bad texts and must not be copied as anti-examples.",
    }


def fallback_evidence_policy(state: str) -> dict:
    """Return a deterministic selector policy without reading runtime state."""
    return {
        "schema": "mind-vault-evidence-policy/v1",
        "policy_version": "unavailable",
        "state": state,
        "authority_weights": {},
        "confidence_weights": {},
        "selection_limits": {"voice": 5, "mechanisms": 0, "soft_guards": 0},
        "genre_exact_bonus": 0.0,
        "genre_global_bonus": 0.0,
        "scope_brief_match_bonus": 0.0,
        "allowed_scopes": [],
    }


def derived_mechanism_transfer(item: dict) -> dict:
    """Adapt one sanitized selector result without carrying RAG source text."""
    return {
        "id": item["evidence_id"],
        "title": "Curated mechanism",
        "channel": "curated-evidence",
        "portfolio_role": "derived-mechanism",
        "mechanism": item["directive"],
        "technique_tags": list(item.get("scope") or []),
        "transfer_instruction": item["directive"],
        "evidence": [],
        "derived": True,
    }


def compile_engine_packet(
    portfolio: dict,
    plan: dict,
    *,
    evidence_records: list[dict] | None = None,
    evidence_decisions: list[dict] | None = None,
    evidence_policy: dict | None = None,
) -> dict:
    writing_sheet = portfolio.get("author_writing_sheet") or {}
    dialogue = dialogue_channel(writing_sheet, plan)
    reranker = rerank_execution_sources(portfolio)
    negatives = negative_channel(portfolio, writing_sheet, plan, dialogue)
    state_absent = evidence_records is None or evidence_decisions is None or evidence_policy is None
    active_policy = evidence_policy or fallback_evidence_policy("state_absent")
    projected = {} if state_absent else project_state(evidence_records, evidence_decisions)
    selection = select_evidence(portfolio, plan, projected, active_policy)
    evidence_state = "state_absent" if state_absent else active_policy["state"]
    execution_evidence = list(reranker["ranked"])
    execution_evidence.extend(derived_mechanism_transfer(item) for item in selection["mechanisms"])
    negatives["guards"] = list(
        dict.fromkeys(
            [
                *negatives["guards"],
                *(item["directive"] for item in selection["guards"] if item["directive"].strip()),
            ]
        )
    )
    sources = portfolio.get("sources") or []
    content = [source for source in sources if source.get("retrieval_channel") == "content"]
    style = [source for source in sources if source.get("retrieval_channel") == "style"]
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "run_id": portfolio.get("run_id"),
                "genre": plan["genre"]["value"],
                "sources": [item.get("id") for item in reranker["ranked"]],
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema": ENGINE_SCHEMA,
        "packet_id": fingerprint,
        "retrieval_run_id": portfolio.get("run_id"),
        "brief_plan": plan,
        "retrieval": {
            "confidence": portfolio.get("retrieval_confidence") or {},
            "selection_policy": portfolio.get("selection_policy") or {},
            "coverage": portfolio.get("portfolio_coverage") or {},
        },
        "channels": {
            "content": content,
            "style_mechanics": style,
            "dialogue": dialogue,
            "negative_examples": negatives,
        },
        "preference_reranker": reranker,
        "evidence_policy": {
            "schema": active_policy["schema"],
            "policy_version": active_policy["policy_version"],
            "state": evidence_state,
            "ledger_sha256": selection["ledger_sha256"],
        },
        "selected_evidence": {
            "voice": selection["voice"],
            "mechanisms": selection["mechanisms"],
            "guards": selection["guards"],
        },
        "selection_trace": selection["selection_trace"],
        "conflicts": selection["conflicts"],
        "evidence_compiler": {
            "execution_evidence": execution_evidence,
            "generation_contract": {
                "authority_order": dialogue.get("precedence"),
                "do": [
                    "Transfer mechanisms, rhythm and decision patterns from the execution evidence.",
                    "Keep the brief's purpose stronger than any recognizable style gesture.",
                    "Use negative evidence as a boundary, not as content.",
                ],
                "do_not": [
                    "Do not reuse source sentences unless the user explicitly requests a quotation.",
                    "Do not treat aggregate Slack signals as factual or literary source material.",
                    "Do not flatten Peter's full range into one universal recipe.",
                ],
                "claim_gate_required": plan["genre"]["value"] in {"cikk", "tanulmany", "prezentacio", "reklam", "beszed", "email"},
            },
        },
        "source_trace": {
            "rag_root": portfolio.get("rag_root"),
            "source_count": len(sources),
            "cross_genre_bridges": portfolio.get("cross_genre_bridges") or [],
            "raw_slack_included": False,
        },
    }


def run_vault_query(plan: dict, args: argparse.Namespace) -> dict:
    genre = plan["genre"]["value"]
    if not genre:
        raise SystemExit("A műfaj nem állapítható meg. Add meg a --genre kapcsolót.")
    command = [
        sys.executable,
        str(args.vault_query),
        "--genre",
        genre,
        "--query",
        plan["query"]["value"],
        "--variation-seed",
        args.variation_seed or hashlib.sha256(plan["brief"].encode("utf-8")).hexdigest()[:12],
    ]
    if args.rag_root:
        command.extend(["--rag-root", str(args.rag_root)])
    if args.limit:
        command.extend(["--limit", str(args.limit)])
    for axis, value in plan.get("target_axes", {}).items():
        command.extend(["--target-axis", f"{axis}={value}"])
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env,
    )
    return json.loads(completed.stdout)


def parse_axis(entries: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(f"Hibás --target-axis: {entry!r}; a forma axis=0..1")
        key, raw = entry.split("=", 1)
        value = float(raw)
        if not 0.0 <= value <= 1.0:
            raise SystemExit(f"A tengelyértéknek 0 és 1 közé kell esnie: {entry!r}")
        parsed[key.strip()] = value
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--genre", default="")
    parser.add_argument("--purpose", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--dialogue", choices=("auto", "required", "off"), default="auto")
    parser.add_argument("--target-axis", action="append", default=[])
    parser.add_argument("--variation-seed", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rag-root", type=Path)
    parser.add_argument("--vault-query", type=Path, default=VAULT_QUERY)
    parser.add_argument("--evidence-ledger", type=Path, default=EVIDENCE_LEDGER)
    parser.add_argument("--decision-ledger", type=Path, default=DECISION_LEDGER)
    parser.add_argument("--evidence-policy", type=Path, default=EVIDENCE_POLICY)
    parser.add_argument("--no-derived-evidence", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.no_derived_evidence:
        evidence_records: list[dict] | None = []
        evidence_decisions: list[dict] | None = []
        evidence_policy = fallback_evidence_policy("disabled_explicitly")
    else:
        try:
            evidence_policy = load_policy(args.evidence_policy)
            evidence_records = read_jsonl(args.evidence_ledger)
            evidence_decisions = read_jsonl(args.decision_ledger)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        if not args.evidence_ledger.is_file() or not args.decision_ledger.is_file():
            evidence_records = None
            evidence_decisions = None
    plan = plan_brief(
        args.brief,
        genre=args.genre,
        purpose=args.purpose,
        audience=args.audience,
        query=args.query,
        dialogue_mode=args.dialogue,
        target_axes=parse_axis(args.target_axis),
    )
    portfolio = run_vault_query(plan, args)
    try:
        packet = compile_engine_packet(
            portfolio,
            plan,
            evidence_records=evidence_records,
            evidence_decisions=evidence_decisions,
            evidence_policy=evidence_policy,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    rendered = json.dumps(packet, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
