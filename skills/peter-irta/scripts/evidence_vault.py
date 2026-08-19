#!/usr/bin/env python3
"""Core schema and append-only state projection for Mind Vault evidence."""

from __future__ import annotations

import hashlib
import json
import re
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

    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance must be an object")
    for field in ("source_kind", "source_run_id", "source_item_id", "brief_id", "source_sha256"):
        _require_string(provenance.get(field), f"provenance.{field}")
    source_sha256 = provenance["source_sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("provenance.source_sha256 must be 64 lowercase hex characters")
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
    if record["status"] == "active" and record["evidence_type"] == "guard" and not parent_ids:
        raise ValueError("active guard requires parent evidence")


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
