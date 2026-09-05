#!/usr/bin/env python3
"""Validate first-person claim provenance and phrase distance from Vault evidence."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


ALLOWED_LABELS = {"brief-supplied", "vault-backed", "fictional-by-genre", "unsupported"}
SENSITIVE_MARKERS = (
    "anyám", "apám", "anya", "apa", "testvérem", "gyerekem", "feleségem", "férjem",
    "diagnózis", "műtét", "kórház", "meghalt", "születtem", "dolgoztam", "laktam",
)
FIRST_PERSON_MARKERS = (
    "én ", "engem ", "nekem ", "velem ", "rajtam ", "voltam ", "láttam ", "éreztem ",
    "tettem ", "csináltam ", "mentem ", "jöttem ", "dolgoztam ", "laktam ", "emlékszem ",
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+|[\r\n]+", text) if item.strip()]


def ngrams(text: str, size: int) -> set[tuple[str, ...]]:
    words = normalize(text).split()
    return {tuple(words[index : index + size]) for index in range(max(0, len(words) - size + 1))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--portfolio", type=Path, required=True)
    parser.add_argument("--claim-map", type=Path, required=True)
    parser.add_argument("--mode", choices=("nonfiction", "fiction"), required=True)
    args = parser.parse_args()

    draft = args.draft.read_text(encoding="utf-8-sig")
    portfolio = json.loads(args.portfolio.read_text(encoding="utf-8-sig"))
    claim_map = json.loads(args.claim_map.read_text(encoding="utf-8-sig"))
    claims = claim_map.get("claims") or []
    invalid_labels = [claim for claim in claims if claim.get("label") not in ALLOWED_LABELS]
    unsupported = [claim for claim in claims if claim.get("label") == "unsupported"]
    fiction_mismatch = [
        claim for claim in claims
        if claim.get("label") == "fictional-by-genre" and args.mode != "fiction"
    ]
    missing_source = [
        claim for claim in claims
        if claim.get("label") == "vault-backed" and not claim.get("source_ids")
    ]

    mapped_text = normalize(" ".join(str(claim.get("text", "")) for claim in claims))
    candidates = []
    for sentence in sentences(draft):
        normalized_sentence = normalize(sentence)
        padded_sentence = f" {normalized_sentence} "
        is_first_person = any(f" {normalize(marker)} " in padded_sentence for marker in FIRST_PERSON_MARKERS)
        is_sensitive = any(f" {normalize(marker)} " in padded_sentence for marker in SENSITIVE_MARKERS)
        has_specific_number = bool(re.search(r"\b(?:19|20)\d{2}\b|\b\d{1,3}\s*(?:eves|evig|honap|nap)\b", normalized_sentence))
        if is_first_person and (is_sensitive or has_specific_number or len(normalized_sentence.split()) >= 8):
            covered = normalized_sentence in mapped_text or any(
                normalize(str(claim.get("text", ""))) in normalized_sentence for claim in claims
            )
            if not covered:
                candidates.append(sentence)

    evidence_text = "\n".join(
        str(evidence.get("text", ""))
        for source in portfolio.get("sources") or []
        for evidence in source.get("evidence") or []
        if not evidence.get("contains_uncertain_asr")
    )
    evidence_12 = ngrams(evidence_text, 12)
    overlap_12 = sorted(" ".join(tokens) for tokens in ngrams(draft, 12) & evidence_12)
    evidence_8 = ngrams(evidence_text, 8)
    overlap_8 = sorted(" ".join(tokens) for tokens in ngrams(draft, 8) & evidence_8 if tokens not in evidence_12)

    hard_failures = []
    if invalid_labels:
        hard_failures.append("invalid-claim-label")
    if unsupported and args.mode == "nonfiction":
        hard_failures.append("unsupported-nonfiction-claim")
    if fiction_mismatch:
        hard_failures.append("fiction-label-in-nonfiction")
    if missing_source:
        hard_failures.append("vault-backed-claim-without-source")
    if candidates and args.mode == "nonfiction":
        hard_failures.append("unmapped-first-person-claim")
    if overlap_12:
        hard_failures.append("source-overlap-12gram")

    print(json.dumps({
        "mode": args.mode,
        "claim_count": len(claims),
        "unmapped_claim_candidates": candidates,
        "unsupported_claims": unsupported,
        "invalid_labels": invalid_labels,
        "missing_source_ids": missing_source,
        "source_overlap_12gram": overlap_12,
        "source_overlap_8gram_review": overlap_8[:20],
        "hard_failures": hard_failures,
        "verdict": "fail" if hard_failures else "review" if overlap_8 or candidates else "pass",
    }, ensure_ascii=False, indent=2))
    return 1 if hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
