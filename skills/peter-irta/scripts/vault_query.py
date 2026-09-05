#!/usr/bin/env python3
"""Return provenance-safe, full-text Mind Vault evidence for a writing brief."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import os
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def default_rag_roots() -> tuple[Path, ...]:
    configured = os.environ.get("MIND_VAULT_RAG_ROOT", "").strip()
    repository_root = SKILL_ROOT.parents[1]
    candidates = [
        Path(configured) if configured else None,
        Path.cwd() / "data" / "mind-vault" / "rag",
        Path.cwd() / "release" / "vault-final" / "data" / "mind-vault" / "rag",
        repository_root / "data" / "mind-vault" / "rag",
        repository_root / "release" / "vault-final" / "data" / "mind-vault" / "rag",
    ]
    return tuple(dict.fromkeys(path.resolve() for path in candidates if path is not None))

DECISION_WEIGHT = {
    "include-core": 1.0,
    "include-secondary": 0.62,
    "include-pending": 0.12,
    "reference-only": 0.0,
    "exclude": 0.0,
}

AUTHORITY_WEIGHT = {
    "drive-owned": 1.0,
    "drive-original": 1.0,
    "author-drive": 1.0,
    "author-text": 1.0,
    "corrected-transcript": 0.82,
    "source-caption": 0.68,
    "youtube-caption": 0.62,
    "official-caption": 0.62,
    "source-description": 0.42,
    "web-authored": 0.72,
    "web-interview": 0.48,
}

GENRE_HINTS = {
    "vers": ("poem", "poetry", "creative-fragment", "interactive-poetry"),
    "poem": ("poem", "poetry", "creative-fragment", "interactive-poetry"),
    "slam": ("slam", "spoken-word", "performance-transcript"),
    "dalszoveg": ("lyrics",),
    "dal": ("lyrics",),
    "lyrics": ("lyrics",),
    "novella": ("novella", "literary-prose", "interactive-prose"),
    "proza": ("novella", "literary-prose", "interactive-prose"),
    "cikk": ("essay", "study", "authored-web-article", "professional"),
    "tanulmany": ("essay", "study"),
    "prezentacio": ("presentation", "study", "professional", "commercial"),
    "email": ("professional", "speech", "bio"),
    "reklam": ("commercial", "professional", "script"),
    "social": ("commercial", "professional", "script"),
    "beszed": ("speech", "performance", "spoken-interview"),
}

GENRE_TITLE_HINTS = {
    "email": ("email", "e-mail", "level", "uzenet"),
    "prezentacio": ("prezentacio", "presentation", "pitch", "deck"),
    "dalszoveg": ("dal", "lyrics", "rap"),
    "dal": ("dal", "lyrics", "rap"),
}

BLOCKED_AUTHORITIES = {"insufficient-asr", "whisper-small-int8"}
BLOCKED_SOURCE_TYPES = {"notebooklm-note"}
BLOCKED_CONTENT_LEVELS = {"metadata-only", "derived-paraphrase"}
PRIMARY_STYLE_AUTHORITIES = {"drive-owned", "drive-original", "author-drive", "author-text"}
CREATIVE_TARGETS = {"vers", "poem", "slam", "dalszoveg", "dal", "lyrics", "novella", "proza"}
PROFESSIONAL_TARGETS = {"cikk", "tanulmany", "prezentacio", "reklam", "social", "beszed"}
UTILITY_LEDGER = Path(__file__).resolve().parents[1] / "state" / "retrieval-utility.jsonl"
AUTHOR_SHEETS = Path(__file__).resolve().parents[1] / "state" / "author-writing-sheets.json"
GENERIC_FAMILY_STARTERS = {
    "a", "az", "egy", "ket", "harom", "elso", "masodik", "ha", "nem", "amikor", "miert",
    "hogyan", "untitled", "nevtelen", "cim", "ai", "magyar", "uj", "regi",
}
GENERIC_FAMILY_TOKENS = GENERIC_FAMILY_STARTERS | {
    "final", "draft", "nyers", "vegeredmeny", "szoveg", "szerkesztes", "prezentacio",
    "strategia", "workshop", "dokumentum", "document", "teljes", "kotetbe", "verzio",
    "vers", "poem", "slam", "novella", "proza", "cikk", "dal", "lyrics", "jegyzet", "jegyzetek",
    "otlet", "otletek", "alternativ", "alternative", "szerkesztoi", "szerkesztesre",
    "szovegszerkesztesre", "brainstorming", "leirat",
}
REFERENCE_MARKERS = (
    "jegyzetek:",
    "szerkezeti térkép",
    "parafrázis",
    "rudy francisco",
    "forma- és hangulatkorlát",
    "ai-segédszöveg",
)

MODE_BY_GENRE = {
    "poem": "page-lyric",
    "poetry": "page-lyric",
    "poetry-collection": "page-lyric",
    "creative-fragment": "page-lyric",
    "interactive-poetry": "conceptual-interface",
    "slam": "spoken-performance",
    "spoken-word": "spoken-performance",
    "performance-transcript": "spoken-performance",
    "lyrics": "refrain-song",
    "novella": "narrative-prose",
    "literary-prose": "narrative-prose",
    "interactive-prose": "conceptual-interface",
    "essay": "professional-argument",
    "study": "professional-argument",
    "presentation": "professional-argument",
    "professional": "professional-argument",
    "commercial": "professional-argument",
    "speech": "spoken-performance",
    "spoken-interview": "spoken-performance",
}

CONCEPT_TERMS = (
    "prompt", "algoritmus", "interfesz", "mesterseges", "intelligencia", "rendszer", "strategia",
    "ado", "hitel", "kozbeszerzes", "adminisztracio", "marka", "adat", "technologia", "isten",
)
IMAGE_TERMS = (
    "test", "bor", "ver", "sziv", "kez", "szem", "szaj", "levego", "feny", "arnyek", "szoba",
    "agy", "ajto", "ablak", "utca", "viz", "tuz", "fold", "eg", "fa", "madar", "gyogyszer",
    "pohar", "kuka", "kartya",
)
INTIMATE_TERMS = (
    "anya", "apa", "anyam", "apam", "szeretlek", "szerelem", "gyasz", "halal", "test", "szex",
    "felelem", "magany", "otthon", "csalad", "emlek", "hiany",
)
PUBLIC_TERMS = (
    "orszag", "tarsadalom", "politika", "kozonseg", "reklam", "marka", "munka", "penz", "ado",
    "klima", "varos", "internet", "generacio", "kampany",
)
RANGE_AXES = (
    "compressed_to_narrative",
    "image_to_conceptual",
    "page_to_performed",
    "intimate_to_public",
)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def terms(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(term for term in normalize(value).split() if len(term) >= 3))


def stable_fraction(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def canonical_title(title: str) -> str:
    value = normalize(title)
    value = re.sub(r"^(?:copy of|masolat)\s+", "", value)
    value = re.sub(r"\b(?:docx?|pdf|txt|pptx?)\b$", "", value)
    value = re.sub(r"\b(?:final|vegeredmeny|kötetbe|kotetbe|nyers|szerkesztoi)\b", "", value)
    value = re.sub(r"\bv(?:er(?:sion)?)?\s*\d+(?:\s*\d+)*$", "", value)
    return " ".join(value.split())


def title_family_keys(title: str) -> tuple[str, ...]:
    canonical = canonical_title(title)
    if not canonical:
        return ()
    keys = [canonical]
    family_tokens = [
        token
        for token in canonical.split()
        if token not in {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
    ]
    if len(family_tokens) >= 2:
        keys.append("prefix2:" + " ".join(family_tokens[:2]))
    if family_tokens and len(family_tokens[0]) >= 4 and family_tokens[0] not in GENERIC_FAMILY_STARTERS:
        keys.append("lead:" + family_tokens[0])
    # Long versioned/project titles usually retain the same distinctive opening.
    # This deliberately prefers broader style diversity over treating every deck
    # or performance cut as an independent voice sample.
    if len(family_tokens) >= 5:
        keys.append("prefix3:" + " ".join(family_tokens[:3]))
    return tuple(dict.fromkeys(keys))


def title_family_signatures(title: str) -> tuple[str, ...]:
    # Imported metadata can accidentally contain a whole paragraph as a title.
    # The opening label is enough for family identity and keeps fuzzy matching bounded.
    tokens = [token for token in canonical_title(title).split()[:24] if token not in GENERIC_FAMILY_TOKENS]
    # A seven-character content word is specific enough to connect editorial
    # variants such as "Babszem Janko" and "babszem jegyzetek", while genre
    # and workflow words above are deliberately ignored.
    signatures = {token for token in tokens if len(token) >= 7}
    signatures.update(
        "".join(tokens[index : index + width])
        for width in (2, 3)
        for index in range(max(0, len(tokens) - width + 1))
        if len("".join(tokens[index : index + width])) >= 10
    )
    return tuple(sorted(signatures))


def same_title_family(left: str, right: str) -> bool:
    if set(title_family_keys(left)) & set(title_family_keys(right)):
        return True
    left_signatures = title_family_signatures(left)
    right_signatures = title_family_signatures(right)
    for left_signature in left_signatures:
        for right_signature in right_signatures:
            if left_signature in right_signature or right_signature in left_signature:
                return True
            if (
                left_signature[:1] == right_signature[:1]
                and abs(len(left_signature) - len(right_signature)) <= 3
                and difflib.SequenceMatcher(None, left_signature, right_signature).ratio() >= 0.9
            ):
                return True
    return False


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_rag_root(explicit: Path | None) -> Path:
    candidates = (explicit,) if explicit else default_rag_roots()
    for candidate in candidates:
        if candidate and all((candidate / name).is_file() for name in ("documents.json", "chunks.json", "connections.json")):
            return candidate
    attempted = ", ".join(str(path) for path in candidates if path)
    raise SystemExit(f"Mind Vault RAG not found. Checked: {attempted}")


def genre_matches(genre: str, preferred: tuple[str, ...]) -> bool:
    normalized_genre = normalize(genre)
    return bool(preferred) and any(normalize(hint) in normalized_genre for hint in preferred)


def style_eligible(document: dict) -> bool:
    if DECISION_WEIGHT.get(str(document.get("decision", "")), 0.0) <= 0:
        return False
    if str(document.get("content_level", "")) in BLOCKED_CONTENT_LEVELS:
        return False
    if str(document.get("authority", "")) in BLOCKED_AUTHORITIES:
        return False
    if str(document.get("source_type", "")) in BLOCKED_SOURCE_TYPES:
        return False
    return bool(document.get("chunk_ids"))


def content_relevance(
    document: dict,
    preferred: tuple[str, ...],
    query_terms: tuple[str, ...],
    title_hints: tuple[str, ...],
) -> float:
    decision = str(document.get("decision", ""))
    authority = str(document.get("authority", ""))
    score = DECISION_WEIGHT.get(decision, 0.0) * 6.0
    score += AUTHORITY_WEIGHT.get(authority, 0.45) * 2.4
    score += 1.7 if document.get("content_level") == "full" else 0.4
    score += min(1.5, math.log10(max(10, int(document.get("word_count") or 0))) * 0.6)

    if genre_matches(str(document.get("genre", "")), preferred):
        score += 7.5

    title = normalize(str(document.get("title", "")))
    if any(normalize(hint) in title for hint in title_hints):
        score += 8.0
    topic_text = normalize(" ".join(document.get("topics") or []))
    top_term_text = normalize(" ".join(document.get("top_terms") or []))
    snippet = normalize(str(document.get("snippet", "")))
    for term in query_terms:
        score += 7.0 if term in title else 0.0
        score += 3.0 if term in topic_text else 0.0
        score += 2.0 if term in top_term_text else 0.0
        score += 1.2 if term in snippet else 0.0
    return round(score, 4)


def document_score(
    document: dict,
    preferred: tuple[str, ...],
    query_terms: tuple[str, ...],
    title_hints: tuple[str, ...],
) -> float:
    """Backward-compatible alias for the content retrieval channel."""
    return content_relevance(document, preferred, query_terms, title_hints)


def document_text(document: dict, chunks: list[dict]) -> str:
    return "\n".join(
        str(chunks[int(chunk_id)].get("text", ""))
        for chunk_id in document.get("chunk_ids") or []
        if 0 <= int(chunk_id) < len(chunks)
    )


def ratio_hits(text_terms: set[str], vocabulary: tuple[str, ...]) -> float:
    if not vocabulary:
        return 0.0
    return min(1.0, sum(1 for term in vocabulary if term in text_terms) / 5.0)


def text_style_metrics(raw_text: str) -> dict:
    words = normalize(raw_text).split()
    sentence_units = [
        unit.strip()
        for unit in re.split(r"(?<=[.!?])\s+|[\r\n]+", raw_text)
        if unit.strip()
    ]
    sentence_lengths = [len(normalize(unit).split()) for unit in sentence_units if normalize(unit)] or [0]
    word_count = max(1, len(words))
    sentence_count = max(1, len(sentence_lengths))
    first_person = {"en", "engem", "nekem", "velem", "ram", "belolem", "magam", "mi", "minket", "nekunk"}
    second_person = {"te", "teged", "neked", "veled", "rad", "beloled", "beloletek", "ti", "titeket", "nektek"}
    return {
        "avg_sentence_words": round(statistics.mean(sentence_lengths), 2),
        "sentence_burstiness": round(statistics.pstdev(sentence_lengths), 2),
        "short_sentence_ratio": round(sum(length <= 5 for length in sentence_lengths) / sentence_count, 3),
        "long_sentence_ratio": round(sum(length >= 18 for length in sentence_lengths) / sentence_count, 3),
        "question_per_100_sentences": round(raw_text.count("?") * 100 / sentence_count, 2),
        "exclamation_per_100_sentences": round(raw_text.count("!") * 100 / sentence_count, 2),
        "colon_per_100_sentences": round(raw_text.count(":") * 100 / sentence_count, 2),
        "line_breaks_per_100_words": round((raw_text.count("\n") + raw_text.count("\r")) * 100 / word_count, 2),
        "first_person_per_1000_words": round(sum(word in first_person for word in words) * 1000 / word_count, 2),
        "second_person_per_1000_words": round(sum(word in second_person for word in words) * 1000 / word_count, 2),
        "lexical_diversity": round(len(set(words)) / word_count, 3),
    }


def source_profile(document: dict, chunks: list[dict]) -> dict:
    raw_text = document_text(document, chunks)
    normalized_text = normalize(raw_text)
    text_terms = set(normalized_text.split())
    term_counts = Counter(normalized_text.split())
    raw_genre = str(document.get("genre", "")).casefold().strip()
    genre = normalize(raw_genre)
    word_count = max(0, int(document.get("word_count") or len(text_terms)))
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    question_density = raw_text.count("?") / max(1, word_count / 100)
    direct_hits = sum(normalized_text.count(token) for token in (" te ", " neked ", " hozzad ", " veled ", " figyelj "))
    sequence_hits = sum(
        normalized_text.count(token)
        for token in (" eloszor ", " aztan ", " vegul ", " egyre ", " masodszor ", " harmadszor ")
    )

    title_text = normalize(str(document.get("title", "")))
    mode = MODE_BY_GENRE.get(raw_genre) or MODE_BY_GENRE.get(genre)
    if not mode and any(token in genre for token in ("slam", "spoken", "performance", "speech")):
        mode = "spoken-performance"
    if not mode and any(token in genre for token in ("poem", "poetry", "vers", "lyric")):
        mode = "page-lyric"
    if not mode and any(token in genre for token in ("presentation", "study", "essay", "professional", "commercial")):
        mode = "professional-argument"
    if not mode and any(token in title_text for token in ("prezentacio", "presentation", "strategia", "workshop")):
        mode = "professional-argument"
    if not mode and "slam" in title_text:
        mode = "spoken-performance"
    if not mode:
        mode = "spoken-performance" if "transcript" in genre or "speech" in genre else "hybrid"

    technique_tags = {mode}
    if question_density >= 0.7:
        technique_tags.add("question-driven")
    if direct_hits >= 3:
        technique_tags.add("direct-address")
    if sequence_hits >= 3:
        technique_tags.add("list-escalation")
    if word_count <= 220:
        technique_tags.add("compressed")
        length_band = "short"
    elif word_count >= 1000:
        technique_tags.add("long-form")
        length_band = "long"
    else:
        length_band = "medium"
    if lines and len(lines) >= 8 and len(lines) / max(1, word_count) >= 0.08:
        technique_tags.add("line-broken")

    conceptual = ratio_hits(text_terms, CONCEPT_TERMS)
    image_driven = ratio_hits(text_terms, IMAGE_TERMS)
    intimate = ratio_hits(text_terms, INTIMATE_TERMS)
    public = ratio_hits(text_terms, PUBLIC_TERMS)
    if conceptual >= 0.4:
        technique_tags.add("conceptual-transfer")
    if image_driven >= 0.4:
        technique_tags.add("image-driven")
    if intimate >= 0.4:
        technique_tags.add("intimate")
    if public >= 0.4:
        technique_tags.add("public-social")

    narrative = 0.82 if mode == "narrative-prose" else 0.62 if word_count >= 1000 else 0.28
    narrative = min(1.0, narrative + min(0.18, sequence_hits * 0.025))
    performed = 0.9 if mode == "spoken-performance" else 0.72 if mode == "refrain-song" else 0.2
    conceptual_axis = min(1.0, 0.2 + conceptual * 0.8)
    if mode == "conceptual-interface":
        conceptual_axis = max(conceptual_axis, 0.9)
    public_axis = 0.5 if intimate + public < 0.2 else public / (intimate + public)

    feature_tokens = {
        f"genre:{genre}",
        f"mode:{mode}",
        f"length:{length_band}",
        *(f"technique:{tag}" for tag in technique_tags),
        *(f"topic:{normalize(str(topic))}" for topic in (document.get("topics") or [])[:8]),
        *(f"term:{normalize(str(term))}" for term in (document.get("top_terms") or [])[:10]),
    }
    return {
        "mode": mode,
        "length_band": length_band,
        "technique_tags": sorted(technique_tags),
        "feature_tokens": {token for token in feature_tokens if token and not token.endswith(":")},
        "range_axes": {
            "compressed_to_narrative": round(narrative, 2),
            "image_to_conceptual": round(conceptual_axis, 2),
            "page_to_performed": round(performed, 2),
            "intimate_to_public": round(public_axis, 2),
        },
        "style_metrics": text_style_metrics(raw_text),
        "content_family_terms": {
            token for token, count in term_counts.items()
            if len(token) >= 7 and count >= 3 and token not in GENERIC_FAMILY_TOKENS
        },
    }


def parse_target_axes(entries: list[str]) -> dict[str, float]:
    parsed: dict[str, float] = {}
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(f"Invalid --target-axis {entry!r}; use axis=0..1")
        axis, raw_value = entry.split("=", 1)
        axis = axis.strip()
        if axis not in RANGE_AXES:
            raise SystemExit(f"Unknown target axis {axis!r}; expected one of: {', '.join(RANGE_AXES)}")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise SystemExit(f"Invalid target value {raw_value!r} for {axis}") from exc
        if not 0.0 <= value <= 1.0:
            raise SystemExit(f"Target value for {axis} must be between 0 and 1")
        parsed[axis] = value
    return parsed


def axis_distance(source: dict, target_axes: dict[str, float]) -> float:
    if not target_axes:
        return 0.0
    return statistics.mean(abs(float(source["range_axes"][axis]) - target) for axis, target in target_axes.items())


def style_relevance(
    profile: dict,
    preferred: tuple[str, ...],
    genre: str,
    target_axes: dict[str, float],
) -> float:
    score = 4.0 if genre_matches(genre, preferred) else 0.0
    score += (1.0 - axis_distance(profile, target_axes)) * 6.0 if target_axes else 0.0
    score += min(2.0, len(profile.get("technique_tags", [])) * 0.25)
    return round(score, 4)


def style_score(profile: dict, preferred: tuple[str, ...], genre: str, target_axes: dict[str, float]) -> float:
    """Backward-compatible alias for the style retrieval channel."""
    return style_relevance(profile, preferred, genre, target_axes)


def reciprocal_rank_fusion(rankings: list[list[str]], constant: int = 60) -> dict[str, float]:
    fused: Counter[str] = Counter()
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            fused[str(item_id)] += 1.0 / (constant + rank)
    return {item_id: round(score, 8) for item_id, score in fused.items()}


def utility_weights(target_genre: str, ledger_path: Path | None = None) -> dict[str, float]:
    totals: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    path = ledger_path or UTILITY_LEDGER
    if not path.is_file():
        return {}
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if normalize(str(item.get("genre", ""))) != target_genre:
            continue
        utility = float(item.get("utility", 0.0))
        for source_id in item.get("source_ids") or []:
            totals[str(source_id)] += utility
            counts[str(source_id)] += 1
    result = {}
    for source_id in totals:
        observations = counts[source_id]
        if observations < 3:
            continue
        mean = totals[source_id] / observations
        result[source_id] = round(mean * observations / (observations + 3) * 0.75, 4)
    return result


def retrieval_confidence(sources: list[dict], preferred: tuple[str, ...], requested_limit: int) -> dict:
    requested = max(1, requested_limit)
    portfolio_ratio = min(1.0, len(sources) / requested)
    same_genre = sum(genre_matches(str(source.get("genre", "")), preferred) for source in sources)
    style_anchors = sum(source.get("retrieval_channel") == "style" for source in sources)
    primary_ratio = (
        sum(str(source.get("authority", "")) in PRIMARY_STYLE_AUTHORITIES for source in sources) / len(sources)
        if sources
        else 0.0
    )
    reasons = []
    if portfolio_ratio < 0.6:
        reasons.append("insufficient_portfolio")
    if same_genre < min(3, math.ceil(requested * 0.5)):
        reasons.append("thin_same_genre_evidence")
    if style_anchors < min(2, max(1, requested // 3)):
        reasons.append("thin_style_evidence")
    if primary_ratio < 0.5:
        reasons.append("weak_primary_authority")

    if not reasons and portfolio_ratio >= 0.8:
        level = "high"
    elif portfolio_ratio >= 0.6 and same_genre >= 2 and style_anchors >= 1:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "abstain_from_voice_claim": level == "low",
        "reasons": reasons,
        "signals": {
            "portfolio_ratio": round(portfolio_ratio, 3),
            "same_genre_sources": same_genre,
            "style_anchors": style_anchors,
            "primary_authority_ratio": round(primary_ratio, 3),
        },
    }


def load_writing_sheet(path: Path, target_genre: str) -> dict:
    if not path.is_file():
        return {
            "genre": target_genre,
            "confidence": "missing",
            "fallback_required": True,
            "evidence_family_count": 0,
        }
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError):
        return {
            "genre": target_genre,
            "confidence": "invalid",
            "fallback_required": True,
            "evidence_family_count": 0,
        }
    sheet = (payload.get("sheets") or {}).get(target_genre)
    if isinstance(sheet, dict):
        return sheet
    return {
        "genre": target_genre,
        "confidence": "missing",
        "fallback_required": True,
        "evidence_family_count": 0,
    }


def metric_bands(sources: list[dict]) -> dict:
    if not sources:
        return {}
    result = {}
    for metric in sources[0]["style_metrics"]:
        values = [float(source["style_metrics"][metric]) for source in sources]
        result[metric] = {
            "min": round(min(values), 3),
            "median": round(statistics.median(values), 3),
            "max": round(max(values), 3),
        }
    return result


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def default_limit(target_genre: str) -> int:
    if target_genre in CREATIVE_TARGETS:
        return 10
    if target_genre == "email":
        return 5
    if target_genre in PROFESSIONAL_TARGETS:
        return 7
    return 8


def diverse_select(
    candidates: list[tuple[float, dict, dict]],
    limit: int,
    preferred: tuple[str, ...],
    target_same_genre: int,
    variation_seed: str,
    rotation_strength: float,
) -> list[tuple[float, dict, dict, float]]:
    selected: list[tuple[float, dict, dict, float]] = []
    remaining = list(candidates)
    seen_keys: set[str] = set()
    max_relevance = max((score for score, _, _ in candidates), default=1.0)

    while remaining and len(selected) < limit:
        same_count = sum(genre_matches(str(item[1].get("genre", "")), preferred) for item in selected)
        require_same = bool(preferred) and same_count < target_same_genre
        pool = [item for item in remaining if not require_same or genre_matches(str(item[1].get("genre", "")), preferred)]
        if not pool:
            pool = remaining

        scored_pool = []
        for relevance, document, profile in pool:
            keys = family_keys(document)
            if any(key in seen_keys for key in keys) or any(
                same_work_family(document, profile, chosen[1], chosen[2]) for chosen in selected
            ):
                continue
            similarity = max(
                (jaccard(profile["feature_tokens"], chosen[2]["feature_tokens"]) for chosen in selected),
                default=0.0,
            )
            covered_tags = {tag for chosen in selected for tag in chosen[2]["technique_tags"]}
            new_tags = len(set(profile["technique_tags"]) - covered_tags)
            novelty = 1.0 - similarity
            seed_jitter = stable_fraction(f"{variation_seed}|{document.get('id')}|{document.get('title')}")
            authority_bonus = 0.25 if str(document.get("authority", "")) in PRIMARY_STYLE_AUTHORITIES else 0.0
            mmr = (relevance / max_relevance) * 5.2 + novelty * 3.2 + min(3, new_tags) * 0.42
            mmr += authority_bonus + seed_jitter * rotation_strength
            scored_pool.append((mmr, relevance, document, profile))
        if not scored_pool:
            break
        mmr, relevance, document, profile = max(
            scored_pool,
            key=lambda item: (item[0], item[1], int(item[2].get("word_count") or 0), str(item[2].get("title", ""))),
        )
        selected.append((relevance, document, profile, round(mmr, 4)))
        seen_keys.update(family_keys(document))
        remaining = [item for item in remaining if item[1] is not document]
    return selected


def select_style_supplements(
    candidates: list[tuple[float, dict, dict]],
    already_selected: list[tuple[float, dict, dict, float]],
    limit: int,
) -> list[tuple[float, dict, dict, float]]:
    supplements: list[tuple[float, dict, dict, float]] = []
    remaining = list(candidates)
    maximum = max((score for score, _, _ in candidates), default=1.0)
    while remaining and len(supplements) < limit:
        comparison = [*already_selected, *supplements]
        covered_tags = {tag for item in comparison for tag in item[2].get("technique_tags", [])}
        scored = []
        for fit, document, profile in remaining:
            if any(same_work_family(document, profile, item[1], item[2]) for item in comparison):
                continue
            similarity = max(
                (jaccard(profile.get("feature_tokens", set()), item[2].get("feature_tokens", set())) for item in comparison),
                default=0.0,
            )
            new_tags = len(set(profile.get("technique_tags", [])) - covered_tags)
            selection_score = (fit / maximum) * 5.0 + (1.0 - similarity) * 3.0 + min(3, new_tags) * 0.6
            scored.append((selection_score, fit, document, profile))
        if not scored:
            break
        selection_score, fit, document, profile = max(
            scored,
            key=lambda item: (item[0], item[1], int(item[2].get("word_count") or 0), str(item[2].get("title", ""))),
        )
        supplements.append((fit, document, profile, round(selection_score, 4)))
        remaining = [item for item in remaining if item[1] is not document]
    return supplements


def same_work_family(left: dict, left_profile: dict, right: dict, right_profile: dict) -> bool:
    if same_title_family(str(left.get("title", "")), str(right.get("title", ""))):
        return True
    left_title = set(title_family_signatures(str(left.get("title", ""))))
    right_title = set(title_family_signatures(str(right.get("title", ""))))
    return bool(
        left_title.intersection(right_profile.get("content_family_terms", set()))
        or right_title.intersection(left_profile.get("content_family_terms", set()))
    )


def family_keys(document: dict) -> tuple[str, ...]:
    provenance = document.get("provenance") or {}
    keys = list(title_family_keys(str(document.get("title", ""))))
    if provenance.get("sha256"):
        keys.append(f"sha256:{provenance['sha256']}")
    if provenance.get("text_path"):
        keys.append(f"path:{normalize(str(provenance['text_path']))}")
    return tuple(key for key in keys if key)


def clipped(text: str, limit: int = 900) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[: limit + 1]
    return head.rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def choose_chunks(document: dict, chunks: list[dict], query_terms: tuple[str, ...], count: int) -> list[dict]:
    available = [chunks[int(chunk_id)] for chunk_id in document.get("chunk_ids") or []]
    if not available or count <= 0:
        return []

    clean_available = [
        chunk
        for chunk in available
        if not any(normalize(marker) in normalize(str(chunk.get("text", ""))) for marker in REFERENCE_MARKERS)
    ]
    if clean_available:
        available = clean_available

    def chunk_score(chunk: dict) -> tuple[float, int]:
        haystack = normalize(
            f"{chunk.get('contextual_prefix', '')} {chunk.get('text', '')}"
        )
        lexical = sum(4.0 + min(3, haystack.count(term)) for term in query_terms if term in haystack)
        edge = 0.55 if int(chunk.get("position", 0)) == 0 else 0.0
        return lexical + edge, -int(chunk.get("position", 0))

    ranked = sorted(available, key=chunk_score, reverse=True)
    chosen = ranked[:count]
    if count >= 2 and len(available) > 1 and not query_terms:
        chosen = [available[0], available[-1]]
    return [
        {
            "position": int(chunk.get("position", 0)),
            "context": str(chunk.get("contextual_prefix", "")),
            "text": clipped(str(chunk.get("text", ""))),
            "contains_uncertain_asr": "[?]" in str(chunk.get("text", "")),
        }
        for chunk in sorted({int(item["id"]): item for item in chosen}.values(), key=lambda item: int(item.get("position", 0)))
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-root", type=Path)
    parser.add_argument("--genre", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=0, help="0 uses a genre-aware portfolio size")
    parser.add_argument("--chunks-per-source", type=int, default=2)
    parser.add_argument("--bridge-limit", type=int, default=3)
    parser.add_argument("--writing-sheets", type=Path, default=AUTHOR_SHEETS)
    parser.add_argument("--variation-seed", default="", help="Brief-specific seed for rotating near-equal source families")
    parser.add_argument(
        "--exclude-family",
        action="append",
        default=[],
        help="Canonical title/family used recently; repeat to avoid conversational overfitting",
    )
    parser.add_argument(
        "--target-axis",
        action="append",
        default=[],
        help="Brief coordinate as axis=0..1; repeat for multiple axes",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rag_root = resolve_rag_root(args.rag_root)
    documents_payload = load_json(rag_root / "documents.json")
    chunks_payload = load_json(rag_root / "chunks.json")
    connections_payload = load_json(rag_root / "connections.json")
    documents = list(documents_payload.get("documents") or [])
    chunks = list(chunks_payload.get("chunks") or [])
    by_id = {str(document.get("id")): document for document in documents}

    target_genre = normalize(args.genre)
    preferred = GENRE_HINTS.get(target_genre, tuple(filter(None, target_genre.split())))
    title_hints = GENRE_TITLE_HINTS.get(target_genre, ())
    query_terms = terms(args.query)
    target_axes = parse_target_axes(args.target_axis)
    learned_utility = utility_weights(target_genre)
    writing_sheet = load_writing_sheet(args.writing_sheets, target_genre)
    excluded_titles = {canonical_title(value) for value in args.exclude_family if canonical_title(value)}
    requested_exclusion_keys = {key for value in args.exclude_family for key in title_family_keys(value)}
    excluded_families = set(requested_exclusion_keys)
    profiled_documents = [
        (document, source_profile(document, chunks)) for document in documents if style_eligible(document)
    ]
    excluded_examples: list[tuple[dict, dict]] = []
    # Resolve a named family to every matching document's provenance keys first.
    # This also removes differently titled copies with the same hash/path.
    for document, profile in profiled_documents:
        document_title = str(document.get("title", ""))
        if requested_exclusion_keys.intersection(title_family_keys(document_title)) or any(
            same_title_family(excluded, document_title) for excluded in args.exclude_family
        ):
            excluded_families.update(family_keys(document))
            excluded_examples.append((document, profile))
    eligible_candidates = [
        (document, profile)
        for document, profile in profiled_documents
        if not excluded_families.intersection(family_keys(document))
        and not any(same_title_family(excluded, str(document.get("title", ""))) for excluded in args.exclude_family)
        and not any(same_work_family(document, profile, excluded, excluded_profile) for excluded, excluded_profile in excluded_examples)
    ]
    content_scores = {
        str(document.get("id")): content_relevance(document, preferred, query_terms, title_hints)
        for document, _ in eligible_candidates
    }
    style_scores = {
        str(document.get("id")): style_relevance(profile, preferred, str(document.get("genre", "")), target_axes)
        for document, profile in eligible_candidates
    }
    content_order = sorted(
        eligible_candidates,
        key=lambda item: (
            -(content_scores[str(item[0].get("id"))] + learned_utility.get(str(item[0].get("id")), 0.0) * 1.5),
            -int(item[0].get("word_count") or 0),
            str(item[0].get("title", "")).casefold(),
        ),
    )
    style_order = sorted(
        eligible_candidates,
        key=lambda item: (
            -(style_scores[str(item[0].get("id"))] + learned_utility.get(str(item[0].get("id")), 0.0)),
            -content_scores[str(item[0].get("id"))],
            str(item[0].get("title", "")).casefold(),
        ),
    )
    fused_scores = reciprocal_rank_fusion(
        [
            [str(document.get("id")) for document, _ in content_order],
            [str(document.get("id")) for document, _ in style_order],
        ]
    )
    ranked = [
        (
            content_scores[str(document.get("id"))] + learned_utility.get(str(document.get("id")), 0.0) * 1.5,
            document,
            profile,
        )
        for document, profile in content_order
    ]

    limit = max(1, min(12, args.limit or default_limit(target_genre)))
    same_genre_available = sum(genre_matches(str(item[1].get("genre", "")), preferred) for item in ranked)
    same_genre_ratio = 0.6 if target_genre in CREATIVE_TARGETS else 0.7
    target_same_genre = min(math.ceil(limit * same_genre_ratio), same_genre_available)
    content_target = max(1, math.ceil(limit * 0.55))
    selected = diverse_select(
        ranked,
        content_target,
        preferred,
        target_same_genre,
        args.variation_seed or f"{args.genre}|{args.query}",
        1.8 if args.variation_seed else 0.35,
    )
    selected_ids = {str(item[1].get("id")) for item in selected}
    content_anchor_ids = {str(item[1].get("id")) for item in selected}
    style_target = max(1, limit - content_target) if limit > 1 else 0
    style_candidates = [
        (style_scores[str(document.get("id"))], document, profile)
        for document, profile in style_order
        if str(document.get("id")) not in selected_ids
    ]
    supplements = select_style_supplements(style_candidates, selected, style_target)
    for style_fit, document, profile, selection_score in supplements:
        source_id = str(document.get("id"))
        selected.append((content_scores[source_id], document, profile, selection_score))
        selected_ids.add(source_id)

    if len(selected) < limit:
        for document, profile in content_order:
            if len(selected) >= limit:
                break
            source_id = str(document.get("id"))
            if source_id in selected_ids:
                continue
            if any(same_work_family(document, profile, chosen[1], chosen[2]) for chosen in selected):
                continue
            selected.append((content_scores[source_id], document, profile, fused_scores.get(source_id, 0.0)))
            selected_ids.add(source_id)
            content_anchor_ids.add(source_id)

    source_ids = {str(document.get("id")) for _, document, _, _ in selected}
    sources = []
    anchor_profile = selected[0][2] if selected else None
    for index, (score, document, profile, diversity_score) in enumerate(selected):
        if index == 0:
            role = "anchor"
        elif genre_matches(str(document.get("genre", "")), preferred):
            role = "formal-contrast" if anchor_profile and profile["mode"] != anchor_profile["mode"] else "range-sample"
        else:
            role = "cadence-bridge" if profile["mode"] in {"spoken-performance", "refrain-song"} else "thematic-contrast"
        sources.append(
            {
                "id": document.get("id"),
                "title": document.get("title"),
                "genre": document.get("genre"),
                "decision": document.get("decision"),
                "authority": document.get("authority"),
                "content_level": document.get("content_level"),
                "word_count": document.get("word_count"),
                "topics": document.get("topics") or [],
                "url": document.get("url"),
                "score": round(fused_scores.get(str(document.get("id")), 0.0), 8),
                "content_score": content_scores.get(str(document.get("id")), score),
                "style_score": style_scores.get(str(document.get("id")), 0.0),
                "fused_score": round(fused_scores.get(str(document.get("id")), 0.0), 8),
                "utility_weight": round(learned_utility.get(str(document.get("id")), 0.0), 3),
                "retrieval_channel": "content" if str(document.get("id")) in content_anchor_ids else "style",
                "diversity_score": diversity_score,
                "portfolio_role": role,
                "mode": profile["mode"],
                "technique_tags": profile["technique_tags"],
                "range_axes": profile["range_axes"],
                "style_metrics": profile["style_metrics"],
                "evidence": choose_chunks(document, chunks, query_terms, max(1, min(3, args.chunks_per_source))),
            }
        )

    portfolio_coverage = {
        "modes": sorted({source["mode"] for source in sources}),
        "technique_tags": sorted({tag for source in sources for tag in source["technique_tags"]}),
        "range_spans": {
            axis: {
                "min": min(source["range_axes"][axis] for source in sources),
                "max": max(source["range_axes"][axis] for source in sources),
            }
            for axis in (sources[0]["range_axes"] if sources else {})
        },
    }
    effective_target_axes = target_axes or (sources[0]["range_axes"] if sources else {})
    distance_ranked = sorted(
        sources,
        key=lambda source: (axis_distance(source, effective_target_axes), -float(source["score"])),
    )
    execution_count = min(5, max(3, math.ceil(len(sources) * 0.4))) if sources else 0
    execution_sources = distance_ranked[:execution_count]
    execution_ids = {str(source["id"]) for source in execution_sources}
    contrast_sources = [source for source in reversed(distance_ranked) if str(source["id"]) not in execution_ids][:2]
    contrastive_calibration = {
        "target_axes": effective_target_axes,
        "target_origin": "explicit" if target_axes else "anchor-derived",
        "execution_set": [
            {
                "id": source["id"],
                "title": source["title"],
                "distance": round(axis_distance(source, effective_target_axes), 3),
                "use": "Extract one transferable mechanism for this brief.",
            }
            for source in execution_sources
        ],
        "contrast_set": [
            {
                "id": source["id"],
                "title": source["title"],
                "distance": round(axis_distance(source, effective_target_axes), 3),
                "use": "This is also Peter, but not the target mode; use it to prevent flattening his range.",
            }
            for source in contrast_sources
        ],
    }
    style_fingerprint = {
        "scope": "execution_set",
        "source_count": len(execution_sources),
        "metric_bands": metric_bands(execution_sources),
        "warning": "Descriptive calibration bands, not authorship proof or mandatory quotas.",
    }
    confidence = retrieval_confidence(sources, preferred, limit)
    confidence["recommended_basis"] = (
        "genre-sheet-with-cautious-local-evidence"
        if confidence["level"] == "low" and writing_sheet.get("confidence") == "supported"
        else "retrieved-portfolio"
    )

    bridges = []
    seen_bridges: set[tuple[str, str]] = set()
    for connection in sorted(connections_payload.get("connections") or [], key=lambda item: float(item.get("score", 0)), reverse=True):
        left_id = str(connection.get("source", ""))
        right_id = str(connection.get("target", ""))
        if left_id in source_ids and right_id not in source_ids:
            source_id, target_id = left_id, right_id
        elif right_id in source_ids and left_id not in source_ids:
            source_id, target_id = right_id, left_id
        else:
            continue
        target = by_id.get(target_id)
        source = by_id.get(source_id)
        if not source or not target or not style_eligible(target) or not connection.get("cross_genre"):
            continue
        pair = tuple(sorted((source_id, target_id)))
        if pair in seen_bridges:
            continue
        seen_bridges.add(pair)
        bridges.append(
            {
                "from": {"id": source_id, "title": source.get("title"), "genre": source.get("genre")},
                "to": {"id": target_id, "title": target.get("title"), "genre": target.get("genre")},
                "shared_topics": connection.get("shared_topics") or [],
                "reason": connection.get("reason", ""),
                "score": connection.get("score"),
            }
        )
        if len(bridges) >= max(0, min(8, args.bridge_limit)):
            break

    run_id = hashlib.sha256(
        json.dumps({"genre": args.genre, "query": args.query, "sources": [source["id"] for source in sources]}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    print(
        json.dumps(
            {
                "rag_root": str(rag_root),
                "run_id": run_id,
                "genre": args.genre,
                "query": args.query,
                "selection_policy": {
                    "method": "dual-channel content relevance + style-fit portfolio with optional outcome utility",
                    "fusion": "reciprocal-rank-fusion",
                    "content_anchor_target": content_target,
                    "style_anchor_target": max(0, limit - content_target),
                    "utility_observations": sum(1 for value in learned_utility.values() if value),
                    "portfolio_size": limit,
                    "same_genre_target": target_same_genre if preferred else 0,
                    "variation_seed": args.variation_seed or f"{args.genre}|{args.query}",
                    "excluded_recent_families": sorted(excluded_titles),
                    "style_sources_exclude": ["reference-only", "metadata-only", "NotebookLM-derived", "raw/insufficient ASR"],
                    "copying": "Extract mechanisms and rhythm; do not reuse sentences unless the user explicitly asks for an own quote.",
                },
                "range_map_note": "Heuristic sampling coordinates, not literary facts or fixed traits.",
                "portfolio_coverage": portfolio_coverage,
                "contrastive_calibration": contrastive_calibration,
                "style_fingerprint": style_fingerprint,
                "retrieval_confidence": confidence,
                "author_writing_sheet": writing_sheet,
                "sources": sources,
                "cross_genre_bridges": bridges,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
