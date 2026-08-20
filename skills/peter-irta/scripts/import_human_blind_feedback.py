#!/usr/bin/env python3
"""Import immutable human blind-test feedback as pending evidence observations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from evidence_vault import (
    EVIDENCE_SCHEMA,
    LedgerTransactionLock,
    canonical_sha256,
    derive_evidence_id,
    read_jsonl,
    validate_record,
)


SYSTEMS = {"engine_v3", "legacy"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHOICES = {"left", "right", "tie"}
SIDE_ADJECTIVE_RE = re.compile(
    r"(?P<article>\b(?:a|az)\s+)?"
    r"(?P<side>bal|jobb)\s*oldal"
    r"(?P<form>i(?:ban|ben|nál|nél|hoz|hez|höz|nak|nek|ról|ről|ra|re|ként|on|en|ön|t|n)?|o)\b",
    re.IGNORECASE,
)
STANDALONE_SIDE_RE = re.compile(
    r"(?P<article>\b(?:a|az)\s+)(?P<side>bal|jobb)\b(?=\s*[,.;:!?])",
    re.IGNORECASE,
)
SYSTEM_LABELS = {"engine_v3": "Engine v3-változat", "legacy": "legacy-változat"}
HUNGARIAN_SIDE_KEYS = {"bal": "left", "jobb": "right"}
FORM_SUFFIXES = {
    "i": "",
    "iban": "ban",
    "iben": "ban",
    "inál": "nál",
    "inél": "nál",
    "ihoz": "hoz",
    "ihez": "hoz",
    "ihöz": "hoz",
    "inak": "nak",
    "inek": "nak",
    "iról": "ról",
    "iről": "ról",
    "ira": "ra",
    "ire": "ra",
    "iként": "ként",
    "ion": "on",
    "ien": "on",
    "iön": "on",
    "it": "ot",
    "in": "on",
    "o": "",
}


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _parse_finalized_at(value: object) -> datetime:
    timestamp = _require_text(value, "finalized_at")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("finalized_at must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("finalized_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def _require_sha256(value: object, field: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a 64-character lowercase SHA-256 hash")


def validate_human_result(result: dict) -> None:
    """Reject anything other than a finalized, non-learning human-test result."""
    if not isinstance(result, dict):
        raise ValueError("human result must be an object")
    if result.get("schema_version") != 1:
        raise ValueError("human result schema_version must be 1")
    _require_text(result.get("run_id"), "run_id")
    _require_sha256(result.get("private_sha256"), "private_sha256")
    _parse_finalized_at(result.get("finalized_at"))
    if "finalized" in result and result["finalized"] is not True:
        raise ValueError("finalized must be true when present")
    for field, expected in (
        ("utility_written", False),
        ("learned_preference_claimed", False),
        ("feedback_review_required", True),
    ):
        if result.get(field) is not expected:
            raise ValueError(f"{field} must remain {str(expected).lower()}")

    items = result.get("items")
    item_count = result.get("item_count")
    if not isinstance(item_count, int) or isinstance(item_count, bool) or not isinstance(items, list):
        raise ValueError("item_count and items must be valid")
    if item_count != len(items):
        raise ValueError("item_count does not match items")

    item_ids = set()
    brief_ids = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] must be an object")
        item_id = _require_text(item.get("item_id"), f"items[{index}].item_id")
        brief_id = _require_text(item.get("brief_id"), f"items[{index}].brief_id")
        _require_text(item.get("genre"), f"items[{index}].genre")
        _require_text(item.get("reason"), f"items[{index}].reason")
        if item_id in item_ids:
            raise ValueError("item_id values must be unique")
        if brief_id in brief_ids:
            raise ValueError("brief_id values must be unique")
        item_ids.add(item_id)
        brief_ids.add(brief_id)

        choice = item.get("choice")
        if choice not in CHOICES:
            raise ValueError("choice must be left, right, or tie")
        chosen_system = item.get("chosen_system")
        if chosen_system is not None and chosen_system not in SYSTEMS:
            raise ValueError("chosen_system must be engine_v3, legacy, or null")
        if choice == "tie" and chosen_system is not None:
            raise ValueError("tie choice must not have a chosen_system")
        if choice != "tie" and chosen_system is None:
            raise ValueError("non-tie choice must have a chosen_system")

        flags = item.get("flags")
        if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
            raise ValueError("flags must be a list of strings")
        if len(set(flags)) != len(flags):
            raise ValueError("flags must not contain duplicates")
        if not isinstance(item.get("general_note", ""), str):
            raise ValueError("general_note must be text")
        feedback = item.get("candidate_feedback")
        if not isinstance(feedback, dict) or set(feedback) != SYSTEMS:
            raise ValueError("candidate_feedback must be keyed by known systems")
        for system, note in feedback.items():
            if not isinstance(note, dict) or not set(note) <= {"highlight", "note"}:
                raise ValueError(f"candidate_feedback.{system} may contain only highlight and note")
            if any(not isinstance(value, str) for value in note.values()):
                raise ValueError(f"candidate_feedback.{system} highlight and note must be strings")

        draft_hashes = item.get("draft_hashes")
        if not isinstance(draft_hashes, dict) or set(draft_hashes) != {"left", "right"}:
            raise ValueError("draft_hashes must contain left and right hashes")
        for side, digest in draft_hashes.items():
            _require_sha256(digest, f"draft_hashes.{side}")


def _validate_private_key(result: dict, private_key: dict) -> None:
    if not isinstance(private_key, dict) or private_key.get("schema_version") != 1:
        raise ValueError("private key schema_version must be 1")
    mappings = private_key.get("items")
    if not isinstance(mappings, dict):
        raise ValueError("private key items must be an object")
    if canonical_sha256(private_key) != result["private_sha256"]:
        raise ValueError("private_sha256 does not match the canonical private key")
    result_item_ids = {item["item_id"] for item in result["items"]}
    if set(mappings) != result_item_ids:
        raise ValueError("private key items do not match human result items")
    for item in result["items"]:
        mapping = mappings[item["item_id"]]
        if not isinstance(mapping, dict) or mapping.get("brief_id") != item["brief_id"]:
            raise ValueError("private key brief_id does not match human result")
        if {mapping.get("left"), mapping.get("right")} != SYSTEMS:
            raise ValueError("private key has invalid system mapping")
        choice = item["choice"]
        expected_system = None if choice == "tie" else mapping[choice]
        if item["chosen_system"] != expected_system:
            raise ValueError("choice and chosen_system disagree with the private key mapping")


def _system_reference(system: str, form: str, *, capitalized: bool) -> str:
    label = SYSTEM_LABELS[system] + FORM_SUFFIXES[form.casefold()]
    if capitalized and label[:1].islower():
        return label[:1].upper() + label[1:]
    return label


def _sanitize_feedback_text(value: str, side_map: dict) -> str:
    """Replace blind-test candidate positions while preserving ordinary spatial wording."""
    def replace_adjective(match: re.Match) -> str:
        system = side_map[HUNGARIAN_SIDE_KEYS[match.group("side").casefold()]]
        article = match.group("article")
        label = _system_reference(system, match.group("form"), capitalized=article is None and match.group(0)[0].isupper())
        if article is None:
            return label
        replacement_article = "az" if system == "engine_v3" else "a"
        if article[0].isupper():
            replacement_article = replacement_article[:1].upper() + replacement_article[1:]
        return f"{replacement_article} {label}"

    def replace_standalone(match: re.Match) -> str:
        system = side_map[HUNGARIAN_SIDE_KEYS[match.group("side").casefold()]]
        article = "az" if system == "engine_v3" else "a"
        if match.group("article")[0].isupper():
            article = article[:1].upper() + article[1:]
        return f"{article} {SYSTEM_LABELS[system]}"

    return STANDALONE_SIDE_RE.sub(replace_standalone, SIDE_ADJECTIVE_RE.sub(replace_adjective, value))


def _make_observation(identity: dict, content: dict, item: dict, result_sha: str, created_at: str) -> dict:
    record = {
        "schema": EVIDENCE_SCHEMA,
        "evidence_id": derive_evidence_id(identity),
        "evidence_type": "evaluation_observation",
        "genre": [item["genre"]],
        "scope": [],
        "status": "pending_review",
        "authority": "evaluation_only",
        "content": content,
        "provenance": {
            "source_kind": "human_blind_test",
            "source_run_id": identity["source_run_id"],
            "source_item_id": identity["source_item_id"],
            "brief_id": identity["brief_id"],
            "source_sha256": result_sha,
            "parent_evidence_ids": [],
        },
        "confidence": {
            "level": "high",
            "basis": "Explicit human blind-test feedback; pending human review.",
        },
        "created_at": created_at,
        "supersedes": [],
    }
    validate_record(record)
    return record


def build_observation_records(result: dict, private_key: dict) -> list[dict]:
    """Convert a finalized result into pending records without retaining side mappings."""
    validate_human_result(result)
    _validate_private_key(result, private_key)
    result_sha = canonical_sha256(result)
    created_at = _parse_finalized_at(result["finalized_at"]).isoformat()
    records = []
    for item in result["items"]:
        side_map = private_key["items"][item["item_id"]]
        draft_hashes = {
            side_map[side]: digest
            for side, digest in item["draft_hashes"].items()
        }
        candidate_feedback = {
            system: {
                field: _sanitize_feedback_text(text, side_map)
                for field, text in feedback.items()
            }
            for system, feedback in (item.get("candidate_feedback") or {}).items()
        }
        content = {
            "chosen_system": item["chosen_system"],
            "reason": _sanitize_feedback_text(item["reason"], side_map),
            "flags": list(item.get("flags") or []),
            "general_note": _sanitize_feedback_text(item.get("general_note", ""), side_map),
            "candidate_feedback": candidate_feedback,
            "draft_sha256_by_system": draft_hashes,
        }
        identity = {
            "schema": EVIDENCE_SCHEMA,
            "source_run_id": result["run_id"],
            "source_item_id": item["item_id"],
            "brief_id": item["brief_id"],
            "content_sha256": canonical_sha256(content),
        }
        records.append(_make_observation(identity, content, item, result_sha, created_at))
    return records


def _append_new_records(records: list[dict], ledger: Path) -> dict:
    """Append under the shared ledger lock and return one consistent write report."""
    ledger = Path(ledger).expanduser().resolve(strict=False)
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    for record in records:
        validate_record(record)

    with LedgerTransactionLock(ledger):
        existing_records = read_jsonl(ledger)
        existing_by_id = {}
        for record in existing_records:
            validate_record(record)
            record_hash = canonical_sha256(record)
            existing_hash = existing_by_id.get(record["evidence_id"])
            if existing_hash is not None and existing_hash != record_hash:
                raise ValueError(f"duplicate evidence_id with different canonical content: {record['evidence_id']}")
            existing_by_id[record["evidence_id"]] = record_hash

        new_records = []
        for record in records:
            record_hash = canonical_sha256(record)
            existing_hash = existing_by_id.get(record["evidence_id"])
            if existing_hash is None:
                existing_by_id[record["evidence_id"]] = record_hash
                new_records.append(record)
            elif existing_hash != record_hash:
                raise ValueError(f"duplicate evidence_id with different canonical content: {record['evidence_id']}")

        if new_records:
            ledger.parent.mkdir(parents=True, exist_ok=True)
            existing_bytes = ledger.read_bytes() if ledger.is_file() else b""
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{ledger.name}.", suffix=".tmp", dir=ledger.parent
            )
            try:
                with os.fdopen(descriptor, "wb") as temporary:
                    temporary.write(existing_bytes)
                    if existing_bytes and not existing_bytes.endswith(b"\n"):
                        temporary.write(b"\n")
                    for record in new_records:
                        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        temporary.write(payload.encode("utf-8") + b"\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, ledger)
            except Exception:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise

        ledger_bytes = ledger.read_bytes() if ledger.is_file() else b""
        return {
            "added_records": len(new_records),
            "existing_records": len(existing_records),
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        }


def append_new_records(records: list[dict], ledger: Path) -> int:
    """Atomically add unseen immutable records, leaving existing entries untouched."""
    return int(_append_new_records(records, ledger)["added_records"])


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise ValueError(f"unable to read {label}: {error}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"malformed {label}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = _load_json(args.result, "human result")
        private_key = _load_json(args.private_key, "private key")
        records = build_observation_records(result, private_key)
        append_report = _append_new_records(records, args.ledger)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({
        "source_run_id": result["run_id"],
        "input_items": len(records),
        "added_records": append_report["added_records"],
        "existing_records": append_report["existing_records"],
        "ledger_sha256": append_report["ledger_sha256"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
