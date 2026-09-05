#!/usr/bin/env python3
"""Core schema and append-only state projection for Mind Vault evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


EVIDENCE_SCHEMA = "mind-vault-evidence/v1"
DECISION_SCHEMA = "mind-vault-evidence-decision/v1"
POLICY_SCHEMA = "mind-vault-evidence-policy/v1"
EVIDENCE_TYPES = {
    "voice_source",
    "mechanism",
    "guard",
    "evaluation_observation",
    "utility_observation",
}
STATUSES = {"pending_review", "active", "rejected", "retired"}
ALLOWED_TRANSITIONS = {
    "pending_review": {"active", "rejected"},
    "active": {"active", "retired"},
    "rejected": set(),
    "retired": set(),
}
AUTHORITIES = {"voice", "genre_mechanism", "generation_guard", "evaluation_only", "utility_only"}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
EVIDENCE_ID_RE = re.compile(r"^ev-[0-9a-f]{24}$")
VOICE_SOURCE_KIND = "provenance_validated_own_source"
VOICE_SOURCE_ORIGINS = {
    "drive-original",
    "drive-owned",
    "author-drive",
    "author-text",
    "proven-drive-match",
    "corrected-transcript",
    "source-caption",
    "source-description",
}


class LedgerTransactionLock:
    """Lock one or more ledgers by canonical path in deadlock-safe order."""

    def __init__(self, *ledger_paths: Path) -> None:
        if not ledger_paths:
            raise ValueError("at least one ledger path is required")
        unique: dict[str, Path] = {}
        for raw_path in ledger_paths:
            path = Path(raw_path).expanduser().resolve(strict=False)
            key = os.path.normcase(str(path))
            unique[key] = path
        self.ledger_paths = [unique[key] for key in sorted(unique)]
        self._files: list[object] = []

    @staticmethod
    def _lock_path(ledger_path: Path) -> Path:
        identity = canonical_sha256({"ledger": os.path.normcase(str(ledger_path))})[:20]
        return ledger_path.parent / f".evidence-ledger-{identity}.lock"

    @staticmethod
    def _acquire(file: object) -> None:
        if os.name == "nt":
            import msvcrt

            file.seek(0, os.SEEK_END)
            if file.tell() == 0:
                file.write(b"\0")
                file.flush()
            while True:
                try:
                    file.seek(0)
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(file.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _release(file: object) -> None:
        if os.name == "nt":
            import msvcrt

            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(file.fileno(), fcntl.LOCK_UN)

    def __enter__(self) -> "LedgerTransactionLock":
        try:
            for ledger_path in self.ledger_paths:
                lock_path = self._lock_path(ledger_path)
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                file = lock_path.open("a+b")
                try:
                    self._acquire(file)
                except Exception:
                    file.close()
                    raise
                self._files.append(file)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        release_error = None
        for file in reversed(self._files):
            try:
                self._release(file)
            except Exception as error:  # pragma: no cover - only OS-level lock corruption
                release_error = release_error or error
            finally:
                file.close()
        self._files.clear()
        if release_error is not None and exc_type is None:
            raise release_error


def canonical_sha256(value: object) -> str:
    """Return the hash of the canonical compact JSON representation of value."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def derive_evidence_id(record_identity: dict) -> str:
    """Build a stable, content-addressed evidence identifier."""
    return f"ev-{canonical_sha256(record_identity)[:24]}"


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not contain duplicate values")
    return value


def _parse_utc_timestamp(value: object, field: str) -> datetime:
    timestamp = _require_string(value, field)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must be an ISO-8601 UTC timestamp")
    return parsed


def validate_record(record: dict) -> None:
    """Validate the v1 evidence envelope without changing the supplied record."""
    if not isinstance(record, dict):
        raise ValueError("evidence record must be an object")
    if record.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError(f"schema must be {EVIDENCE_SCHEMA}")
    evidence_id = record.get("evidence_id")
    if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.fullmatch(evidence_id):
        raise ValueError("evidence_id must match ev-<24 lowercase hex>")
    if record.get("evidence_type") not in EVIDENCE_TYPES:
        raise ValueError("evidence_type is invalid")
    if record.get("status") not in STATUSES:
        raise ValueError("status is invalid")
    if record.get("authority") not in AUTHORITIES:
        raise ValueError("authority is invalid")
    _require_string_list(record.get("genre"), "genre")
    scope = _require_string_list(record.get("scope"), "scope")
    if not isinstance(record.get("content"), dict):
        raise ValueError("content must be an object")
    if record["evidence_type"] in {"guard", "mechanism"} and "polarity" in record["content"]:
        if record["content"]["polarity"] not in {"require", "forbid", "prefer"}:
            raise ValueError("content.polarity must be require, forbid, or prefer")

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")
    for field in ("source_kind", "source_run_id", "source_item_id", "brief_id", "source_sha256"):
        _require_string(provenance.get(field), f"provenance.{field}")
    source_sha256 = provenance["source_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("provenance.source_sha256 must be 64 lowercase hex characters")
    if record["evidence_type"] == "voice_source":
        if (
            provenance["source_kind"] != VOICE_SOURCE_KIND
            or provenance.get("origin") not in VOICE_SOURCE_ORIGINS
        ):
            raise ValueError("voice_source provenance must be a provenance-backed own source")
    parent_ids = provenance.get("parent_evidence_ids", [])
    _require_string_list(parent_ids, "provenance.parent_evidence_ids")
    if any(not EVIDENCE_ID_RE.fullmatch(item) for item in parent_ids):
        raise ValueError("provenance.parent_evidence_ids contains an invalid evidence ID")

    confidence = record.get("confidence")
    if not isinstance(confidence, dict) or confidence.get("level") not in CONFIDENCE_LEVELS:
        raise ValueError("confidence.level is invalid")
    _require_string(confidence.get("basis"), "confidence.basis")
    _parse_utc_timestamp(record.get("created_at"), "created_at")
    _require_string_list(record.get("supersedes"), "supersedes")
    if any(not EVIDENCE_ID_RE.fullmatch(item) for item in record["supersedes"]):
        raise ValueError("supersedes contains an invalid evidence ID")

    if record["status"] == "active" and record["evidence_type"] in {"guard", "mechanism"} and not scope:
        raise ValueError("active guard or mechanism requires scope")
    if record["status"] == "active" and record["evidence_type"] in {"guard", "mechanism"} and not parent_ids:
        raise ValueError("active derived evidence requires parent evidence")


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL ledger, reporting malformed rows precisely."""
    if not path.is_file():
        return []
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Malformed JSONL at {path} line {line_number}: {error.msg}") from error
        if not isinstance(item, dict):
            raise ValueError(f"Malformed JSONL at {path} line {line_number}: expected object")
        records.append(item)
    return records


def _validate_decision(decision: dict) -> datetime:
    if not isinstance(decision, dict):
        raise ValueError("decision must be an object")
    if decision.get("schema") != DECISION_SCHEMA:
        raise ValueError(f"decision schema must be {DECISION_SCHEMA}")
    evidence_id = decision.get("evidence_id")
    if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.fullmatch(evidence_id):
        raise ValueError("decision evidence_id is invalid")
    if decision.get("status") not in STATUSES:
        raise ValueError("decision status is invalid")
    _require_string(decision.get("reason"), "decision reason")
    if decision.get("curator") != "peter":
        raise ValueError("decision curator must be peter")
    return _parse_utc_timestamp(decision.get("decided_at"), "decision decided_at")


def _copy_json(value: dict) -> dict:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def project_state(records: list[dict], decisions: list[dict]) -> dict[str, dict]:
    """Project immutable evidence records through their ordered decision ledger."""
    state = {}
    content_by_id = {}
    for record in records:
        validate_record(record)
        evidence_id = record["evidence_id"]
        content_hash = canonical_sha256(record)
        existing_hash = content_by_id.get(evidence_id)
        if existing_hash is not None:
            if existing_hash != content_hash:
                raise ValueError(f"duplicate evidence_id with different canonical content: {evidence_id}")
            continue
        content_by_id[evidence_id] = content_hash
        state[evidence_id] = _copy_json(record)

    previous_decision_at = {}
    for decision in decisions:
        decided_at = _validate_decision(decision)
        evidence_id = decision["evidence_id"]
        if evidence_id not in state:
            raise ValueError(f"decision references missing evidence: {evidence_id}")
        previous = previous_decision_at.get(evidence_id)
        if previous is not None and decided_at <= previous:
            raise ValueError(f"non-monotonic decision timestamp for evidence: {evidence_id}")
        current_status = state[evidence_id]["status"]
        next_status = decision["status"]
        if next_status not in ALLOWED_TRANSITIONS[current_status]:
            raise ValueError(f"invalid transition for {evidence_id}: {current_status} -> {next_status}")
        projected = _copy_json(state[evidence_id])
        projected["status"] = next_status
        validate_record(projected)
        state[evidence_id] = projected
        previous_decision_at[evidence_id] = decided_at
    for evidence_id, record in state.items():
        if record["status"] == "active" and record["evidence_type"] in {"guard", "mechanism"}:
            for parent_id in record["provenance"]["parent_evidence_ids"]:
                parent = state.get(parent_id)
                if parent is None:
                    raise ValueError(f"active derived evidence has missing parent: {parent_id}")
                if (
                    parent["evidence_type"] != "evaluation_observation"
                    or parent["status"] not in {"pending_review", "active"}
                ):
                    raise ValueError(
                        f"active derived evidence parent must be a pending or active evaluation_observation: {parent_id}"
                    )
        for superseded_id in record["supersedes"]:
            superseded = state.get(superseded_id)
            if superseded is None:
                raise ValueError(f"supersedes references missing evidence: {superseded_id}")
            if superseded["status"] != "active":
                raise ValueError(f"supersedes must reference active evidence: {superseded_id}")
    return state


def load_policy(path: Path) -> dict:
    """Load the versioned static policy required by evidence selection."""
    try:
        policy = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ValueError(f"Unable to read evidence policy at {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed evidence policy at {path}: {error.msg}") from error
    if not isinstance(policy, dict) or policy.get("schema") != POLICY_SCHEMA:
        raise ValueError(f"policy schema must be {POLICY_SCHEMA}")
    required = {
        "policy_version",
        "state",
        "authority_weights",
        "confidence_weights",
        "selection_limits",
        "genre_exact_bonus",
        "genre_global_bonus",
        "scope_brief_match_bonus",
        "allowed_scopes",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise ValueError(f"policy is missing required fields: {', '.join(missing)}")
    _require_string(policy["policy_version"], "policy_version")
    _require_string(policy["state"], "state")
    _require_string_list(policy["allowed_scopes"], "allowed_scopes")
    return policy


def _normalized_text(value: object) -> str:
    """Normalize human-facing values for deterministic selector matching."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return text.casefold().replace("_", " ")


def _tokens(value: object) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalized_text(value))


def _plan_value(plan: dict, key: str) -> str:
    value = plan.get(key, "")
    return str(value.get("value", "")) if isinstance(value, dict) else str(value or "")


def _target_genre(plan: dict) -> str:
    return _normalized_text(_plan_value(plan, "genre")).strip()


def _record_genres(record: dict) -> set[str]:
    return {_normalized_text(item).strip() for item in record.get("genre") or [] if str(item).strip()}


def _genre_match(record: dict, plan: dict) -> str:
    target = _target_genre(plan)
    genres = _record_genres(record)
    if target and target in genres:
        return "exact"
    if "global" in genres:
        return "global"
    return ""


def adapt_voice_sources(portfolio: dict) -> list[dict]:
    """Adapt only the existing execution set into bounded voice evidence."""
    source_by_id = {str(item.get("id")): item for item in portfolio.get("sources") or []}
    execution = (portfolio.get("contrastive_calibration") or {}).get("execution_set") or []
    return [
        {
            "evidence_id": f"voice-{item['id']}",
            "evidence_type": "voice_source",
            "authority": "voice",
            "source": source_by_id.get(str(item["id"]), {}),
            "original_rank": rank,
        }
        for rank, item in enumerate(execution, start=1)
        if item.get("id")
    ]


def score_derived(record: dict, plan: dict, policy: dict) -> tuple[float, list[str]]:
    """Score one active derived record from policy weights and brief relevance."""
    if record.get("status") != "active" or record.get("evidence_type") not in {"guard", "mechanism"}:
        return 0.0, ["inactive or unsupported evidence"]

    genre_match = _genre_match(record, plan)
    if not genre_match:
        return 0.0, ["genre mismatch"]

    scope_tokens = _tokens(" ".join(str(item) for item in record.get("scope") or []))
    brief_text = " ".join(
        [
            str(plan.get("brief") or ""),
            _plan_value(plan, "purpose"),
            _plan_value(plan, "audience"),
            _plan_value(plan, "query"),
            " ".join(str(item) for item in plan.get("negative_preferences") or []),
            _target_genre(plan),
        ]
    )
    brief_tokens = set(_tokens(brief_text))
    brief_fit = sum(token in brief_tokens for token in scope_tokens) / len(scope_tokens) if scope_tokens else 0.0
    authority_weight = float((policy.get("authority_weights") or {}).get(record.get("authority"), 0.0))
    confidence_level = (record.get("confidence") or {}).get("level")
    confidence_weight = float((policy.get("confidence_weights") or {}).get(confidence_level, 0.0))
    genre_bonus = float(policy.get("genre_exact_bonus", 0.0) if genre_match == "exact" else policy.get("genre_global_bonus", 0.0))
    scope_bonus = float(policy.get("scope_brief_match_bonus", 0.0)) if brief_fit else 0.0
    score = brief_fit + genre_bonus + authority_weight + confidence_weight + scope_bonus
    reasons = [
        f"brief_fit:{brief_fit:.4f}",
        f"genre:{genre_match}",
        f"authority:{authority_weight:.4f}",
        f"confidence:{confidence_weight:.4f}",
    ]
    if scope_bonus:
        reasons.append(f"scope_match:{scope_bonus:.4f}")
    return score, reasons


def _normalized_scope(scope: object) -> str:
    return "_".join(_tokens(scope))


def _guard_level(record: dict) -> str:
    content = record.get("content") or {}
    return str(content.get("guard_level") or content.get("level") or "soft")


def _polarity(record: dict) -> str:
    value = str((record.get("content") or {}).get("polarity") or "prefer")
    return value if value in {"require", "forbid", "prefer"} else "prefer"


def _selected_derived(record: dict, score: float, reasons: list[str]) -> dict:
    content = record.get("content") or {}
    return {
        "evidence_id": record.get("evidence_id"),
        "evidence_type": record.get("evidence_type"),
        "genre": list(record.get("genre") or []),
        "scope": list(record.get("scope") or []),
        "directive": str(content.get("directive") or ""),
        "level": _guard_level(record),
        "confidence": str((record.get("confidence") or {}).get("level") or ""),
        "score": round(score, 8),
        "reasons": list(reasons),
    }


def _ranked(records: list[dict], plan: dict, policy: dict) -> list[tuple[dict, float, list[str]]]:
    scored = []
    for record in records:
        score, reasons = score_derived(record, plan, policy)
        if _genre_match(record, plan):
            scored.append((record, score, reasons))
    return sorted(
        scored,
        key=lambda item: (
            {"exact": 0, "global": 1}[_genre_match(item[0], plan)],
            -item[1],
            str(item[0].get("evidence_id") or ""),
        ),
    )


def _guard_conflicts(guards: list[dict], plan: dict) -> tuple[set[str], list[dict]]:
    """Find unresolved require/forbid pairs for the current output genre."""
    grouped: dict[tuple[str, str], list[dict]] = {}
    target = _target_genre(plan)
    for record in guards:
        for scope in record.get("scope") or []:
            normalized_scope = _normalized_scope(scope)
            if normalized_scope:
                grouped.setdefault((target, normalized_scope), []).append(record)

    excluded: set[str] = set()
    conflicts = []
    for (genre_scope, scope), records in sorted(grouped.items()):
        require = [record for record in records if _polarity(record) == "require"]
        forbid = [record for record in records if _polarity(record) == "forbid"]
        if not require or not forbid:
            continue
        conflicting = set()
        for left in require:
            for right in forbid:
                left_id = str(left.get("evidence_id"))
                right_id = str(right.get("evidence_id"))
                if right_id in set(left.get("supersedes") or []) or left_id in set(right.get("supersedes") or []):
                    continue
                conflicting.update((left_id, right_id))
        if conflicting:
            evidence_ids = sorted(conflicting)
            excluded.update(evidence_ids)
            conflicts.append({"genre_scope": genre_scope, "scope": scope, "evidence_ids": evidence_ids})
    return excluded, conflicts


def select_evidence(portfolio: dict, plan: dict, projected: dict[str, dict], policy: dict) -> dict:
    """Purely select active curated evidence with a stable, privacy-safe result."""
    active = [
        record
        for record in projected.values()
        if record.get("status") == "active" and record.get("evidence_type") in {"guard", "mechanism"}
    ]
    genre_matching = [record for record in active if _genre_match(record, plan)]
    superseded_ids = {
        superseded_id
        for record in genre_matching
        for superseded_id in record.get("supersedes") or []
    }
    eligible = [record for record in genre_matching if record.get("evidence_id") not in superseded_ids]
    guards = [record for record in eligible if record.get("evidence_type") == "guard"]
    mechanisms = [record for record in eligible if record.get("evidence_type") == "mechanism"]
    conflicting_ids, conflicts = _guard_conflicts(guards, plan)
    guards = [record for record in guards if record.get("evidence_id") not in conflicting_ids]

    ranked_guards = _ranked(guards, plan, policy)
    hard_guards = [item for item in ranked_guards if _guard_level(item[0]) == "hard"]
    soft_guards = [item for item in ranked_guards if _guard_level(item[0]) != "hard"]
    limits = policy.get("selection_limits") or {}
    selected_guards = hard_guards + soft_guards[:int(limits.get("soft_guards", 3))]
    selected_mechanisms = _ranked(mechanisms, plan, policy)[:int(limits.get("mechanisms", 3))]
    voice_candidates = adapt_voice_sources(portfolio)
    voice = voice_candidates[:int(limits.get("voice", 5))]

    selected_derived = [
        ("guard", _selected_derived(record, score, reasons)) for record, score, reasons in selected_guards
    ] + [
        ("mechanism", _selected_derived(record, score, reasons)) for record, score, reasons in selected_mechanisms
    ]
    selection_trace = [
        {
            "channel": channel,
            "evidence_id": item["evidence_id"],
            "genre_tier": next(
                _genre_match(record, plan)
                for record, _, _ in (selected_guards if channel == "guard" else selected_mechanisms)
                if record.get("evidence_id") == item["evidence_id"]
            ),
            "score": item["score"],
            "reasons": item["reasons"],
            "selected": True,
            "exclusion_reason": None,
        }
        for channel, item in selected_derived
    ]
    selection_trace.extend(
        {
            "channel": "voice",
            "evidence_id": item["evidence_id"],
            "original_rank": item["original_rank"],
            "selected": True,
            "exclusion_reason": None,
        }
        for item in voice
    )

    selected_guard_ids = {record["evidence_id"] for record, _, _ in selected_guards}
    selected_mechanism_ids = {record["evidence_id"] for record, _, _ in selected_mechanisms}
    for record in sorted(projected.values(), key=lambda item: str(item.get("evidence_id") or "")):
        evidence_id = str(record.get("evidence_id") or "")
        evidence_type = str(record.get("evidence_type") or "")
        if evidence_id in selected_guard_ids or evidence_id in selected_mechanism_ids:
            continue
        row = {
            "channel": evidence_type if evidence_type in {"guard", "mechanism"} else evidence_type or "derived",
            "evidence_id": evidence_id,
            "selected": False,
        }
        if evidence_type not in {"guard", "mechanism"}:
            row["exclusion_reason"] = "unsupported_type"
        elif record.get("status") != "active":
            row["exclusion_reason"] = "inactive"
        else:
            genre_tier = _genre_match(record, plan)
            score, reasons = score_derived(record, plan, policy)
            row.update({
                "genre_tier": genre_tier or None,
                "score": round(score, 8),
                "reasons": reasons,
            })
            if not genre_tier:
                row["exclusion_reason"] = "genre_mismatch"
            elif evidence_id in superseded_ids:
                row["exclusion_reason"] = "superseded"
            elif evidence_id in conflicting_ids:
                row["exclusion_reason"] = "conflict"
            elif evidence_type == "guard":
                row["exclusion_reason"] = "soft_guard_limit"
            elif evidence_type == "mechanism":
                row["exclusion_reason"] = "mechanism_limit"
            else:  # pragma: no cover - evidence type is exhausted above
                row["exclusion_reason"] = "not_selected"
        selection_trace.append(row)

    selection_trace.extend(
        {
            "channel": "voice",
            "evidence_id": item["evidence_id"],
            "original_rank": item["original_rank"],
            "selected": False,
            "exclusion_reason": "voice_limit",
        }
        for item in voice_candidates[len(voice):]
    )
    return {
        "voice": voice,
        "mechanisms": [item for channel, item in selected_derived if channel == "mechanism"],
        "guards": [item for channel, item in selected_derived if channel == "guard"],
        "conflicts": conflicts,
        "selection_trace": selection_trace,
        "ledger_sha256": canonical_sha256(projected),
        "policy_version": policy.get("policy_version"),
    }
