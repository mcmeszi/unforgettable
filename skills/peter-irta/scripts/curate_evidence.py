#!/usr/bin/env python3
"""Curate immutable evaluation observations into derived evidence rules."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from evidence_vault import (
    CONFIDENCE_LEVELS,
    DECISION_SCHEMA,
    EVIDENCE_ID_RE,
    EVIDENCE_SCHEMA,
    canonical_sha256,
    derive_evidence_id,
    load_policy,
    project_state,
    read_jsonl,
    validate_record,
)


POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "evidence-policy.json"
DERIVED_KINDS = {"guard", "mechanism"}
GUARD_LEVELS = {"hard", "soft"}
DECISION_STATUSES = {"active", "rejected", "retired"}


def _resolve_distinct_ledger_paths(evidence_path: Path, decision_path: Path) -> tuple[Path, Path]:
    """Resolve both ledgers and reject aliases for the same underlying file."""
    evidence_path = Path(evidence_path).expanduser().resolve(strict=False)
    decision_path = Path(decision_path).expanduser().resolve(strict=False)
    same_file = (
        evidence_path == decision_path
        or (
            evidence_path.is_file()
            and decision_path.is_file()
            and os.path.samefile(evidence_path, decision_path)
        )
    )
    if same_file:
        raise ValueError("evidence and decision ledgers must be different files")
    return evidence_path, decision_path


class _LedgerTransactionLock:
    """Cross-platform interprocess lock for one ordered ledger-pair transaction."""

    def __init__(self, evidence_path: Path, decision_path: Path) -> None:
        identity = canonical_sha256({
            "evidence_ledger": str(evidence_path),
            "decision_ledger": str(decision_path),
        })
        self.path = evidence_path.parent / f".curate-evidence-{identity}.lock"
        self.file = None

    def __enter__(self) -> "_LedgerTransactionLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0, os.SEEK_END)
                if self.file.tell() == 0:
                    self.file.write(b"\0")
                    self.file.flush()
                while True:
                    try:
                        self.file.seek(0)
                        msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX)
        except Exception:
            self.file.close()
            self.file = None
            raise
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        assert self.file is not None
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_text_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be a list of non-empty strings")
    normalized = [item.strip() for item in value]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must not contain duplicate values")
    return normalized


def _derived_identity(record: dict) -> dict:
    """Return the timestamp-free content identity used for stable derived IDs."""
    return {
        "schema": record["schema"],
        "evidence_type": record["evidence_type"],
        "genre": record["genre"],
        "scope": record["scope"],
        "authority": record["authority"],
        "content": record["content"],
        "provenance": record["provenance"],
        "confidence": record["confidence"],
        "supersedes": record["supersedes"],
    }


def _same_derived_identity(left: dict, right: dict) -> bool:
    return canonical_sha256(_derived_identity(left)) == canonical_sha256(_derived_identity(right))


def build_decision(evidence_id: str, status: str, reason: str, decided_at: str | None = None) -> dict:
    """Build a curator decision; transitions are checked against projected state."""
    if not isinstance(evidence_id, str) or not EVIDENCE_ID_RE.fullmatch(evidence_id):
        raise ValueError("evidence_id is invalid")
    if status not in DECISION_STATUSES:
        raise ValueError("decision status is invalid")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("curation reason is required")
    if decided_at is not None:
        _require_text(decided_at, "decided_at")
    return {
        "schema": DECISION_SCHEMA,
        "evidence_id": evidence_id,
        "status": status,
        "reason": reason.strip(),
        "curator": "peter",
        "decided_at": decided_at or datetime.now(timezone.utc).isoformat(),
    }


def build_derived_record(
    kind: str,
    genres: list[str],
    scopes: list[str],
    directive: str,
    guard_level: str | None,
    confidence: str,
    basis: str,
    parents: list[dict],
) -> dict:
    """Build a pending guard or mechanism from explicit observation records only."""
    if kind not in DERIVED_KINDS:
        raise ValueError("derived evidence type must be guard or mechanism")
    genres = _require_text_list(genres, "genre")
    scopes = _require_text_list(scopes, "scope")
    allowed_scopes = set(load_policy(POLICY_PATH)["allowed_scopes"])
    unknown_scopes = sorted(set(scopes) - allowed_scopes)
    if unknown_scopes:
        raise ValueError(f"unknown scope: {', '.join(unknown_scopes)}")
    directive = _require_text(directive, "directive")
    basis = _require_text(basis, "confidence basis")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError("confidence level is invalid")
    if kind == "guard":
        if guard_level not in GUARD_LEVELS:
            raise ValueError("guard level must be hard or soft")
    elif guard_level is not None:
        raise ValueError("guard level is only valid for guards")
    if not isinstance(parents, list) or not parents:
        raise ValueError("derived evidence requires at least one parent observation")

    parent_ids = []
    parent_fingerprints = []
    for parent in parents:
        validate_record(parent)
        if parent["evidence_type"] != "evaluation_observation":
            raise ValueError("derived evidence parents must be evaluation_observation records")
        parent_id = parent["evidence_id"]
        if parent_id in parent_ids:
            raise ValueError("duplicate parent evidence ID")
        parent_ids.append(parent_id)
        parent_fingerprints.append({"evidence_id": parent_id, "sha256": canonical_sha256(parent)})
    parent_fingerprints.sort(key=lambda item: item["evidence_id"])

    content = {"directive": directive}
    if kind == "guard":
        content["guard_level"] = guard_level
    provenance = {
        "source_kind": "curated_evaluation_observations",
        "source_run_id": "curation-" + canonical_sha256(parent_fingerprints)[:24],
        "source_item_id": "derived-rule",
        "brief_id": "curated-derived",
        "source_sha256": canonical_sha256(parent_fingerprints),
        "parent_evidence_ids": parent_ids,
    }
    record = {
        "schema": EVIDENCE_SCHEMA,
        "evidence_id": "",
        "evidence_type": kind,
        "genre": genres,
        "scope": scopes,
        "status": "pending_review",
        "authority": "generation_guard" if kind == "guard" else "genre_mechanism",
        "content": content,
        "provenance": provenance,
        "confidence": {"level": confidence, "basis": basis},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "supersedes": [],
    }
    record["evidence_id"] = derive_evidence_id(_derived_identity(record))
    validate_record(record)
    return record


def resolve_parent_ids(records: list[dict], runs: list[str], briefs: list[str]) -> list[str]:
    """Resolve each ordered (--parent-run, --parent-brief) pair exactly once."""
    if len(runs) != len(briefs):
        raise ValueError("parent-run and parent-brief selectors must have equal lengths")
    if not runs:
        raise ValueError("at least one parent-run and parent-brief selector is required")
    parent_ids = []
    for run_id, brief_id in zip(runs, briefs):
        matches = [
            record
            for record in records
            if record.get("evidence_type") == "evaluation_observation"
            and record.get("provenance", {}).get("source_run_id") == run_id
            and record.get("provenance", {}).get("brief_id") == brief_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"parent selector ({run_id}, {brief_id}) must resolve exactly one evaluation_observation"
            )
        parent_ids.append(matches[0]["evidence_id"])
    if len(set(parent_ids)) != len(parent_ids):
        raise ValueError("duplicate parent evidence ID")
    return parent_ids


def _jsonl_bytes(existing: bytes, rows: list[dict]) -> bytes:
    if not rows:
        return existing
    prefix = existing if not existing or existing.endswith(b"\n") else existing + b"\n"
    appended = b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in rows
    )
    return prefix + appended


def _write_bytes(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return temporary_name


def _replace_pair_atomically(
    evidence_path: Path,
    decision_path: Path,
    evidence_bytes: bytes,
    decision_bytes: bytes,
) -> None:
    """Commit prepared ledgers together, rolling back a failed second replacement."""
    evidence_existed = evidence_path.is_file()
    old_evidence = evidence_path.read_bytes() if evidence_existed else b""
    evidence_temp = None
    decision_temp = None
    evidence_replaced = False
    try:
        evidence_temp = _write_bytes(evidence_path, evidence_bytes)
        decision_temp = _write_bytes(decision_path, decision_bytes)
        os.replace(evidence_temp, evidence_path)
        evidence_replaced = True
        os.replace(decision_temp, decision_path)
    except Exception:
        if evidence_replaced:
            if evidence_existed:
                rollback_temp = _write_bytes(evidence_path, old_evidence)
                os.replace(rollback_temp, evidence_path)
            else:
                evidence_path.unlink(missing_ok=True)
        raise
    finally:
        for temporary_name in (evidence_temp, decision_temp):
            if temporary_name is None:
                continue
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _project(records: list[dict], decisions: list[dict]) -> dict[str, dict]:
    return project_state(records, decisions)


def _parent_records(records: list[dict], parent_ids: list[str]) -> list[dict]:
    by_id = {record["evidence_id"]: record for record in records}
    missing = [evidence_id for evidence_id in parent_ids if evidence_id not in by_id]
    if missing:
        raise ValueError(f"missing parent evidence: {', '.join(missing)}")
    return [by_id[evidence_id] for evidence_id in parent_ids]


def create_derived(
    evidence_path: Path,
    decision_path: Path,
    kind: str,
    genres: list[str],
    scopes: list[str],
    directive: str,
    guard_level: str | None,
    confidence: str,
    basis: str,
    parent_ids: list[str],
    activate: bool,
) -> dict:
    """Create derived evidence and optionally activate it after final-state validation."""
    evidence_path, decision_path = _resolve_distinct_ledger_paths(evidence_path, decision_path)
    with _LedgerTransactionLock(evidence_path, decision_path):
        return _create_derived_locked(
            evidence_path=evidence_path,
            decision_path=decision_path,
            kind=kind,
            genres=genres,
            scopes=scopes,
            directive=directive,
            guard_level=guard_level,
            confidence=confidence,
            basis=basis,
            parent_ids=parent_ids,
            activate=activate,
        )


def _create_derived_locked(
    evidence_path: Path,
    decision_path: Path,
    kind: str,
    genres: list[str],
    scopes: list[str],
    directive: str,
    guard_level: str | None,
    confidence: str,
    basis: str,
    parent_ids: list[str],
    activate: bool,
) -> dict:
    """Run one create-derived transaction while its ledger pair is locked."""
    records = read_jsonl(evidence_path)
    decisions = read_jsonl(decision_path)
    current_state = _project(records, decisions)
    parents = _parent_records(records, parent_ids)
    record = build_derived_record(
        kind, genres, scopes, directive, guard_level, confidence, basis, parents
    )
    existing = next((item for item in records if item["evidence_id"] == record["evidence_id"]), None)
    new_records = []
    if existing is not None:
        if not _same_derived_identity(existing, record):
            raise ValueError(f"duplicate evidence_id with different derived content: {record['evidence_id']}")
        record = existing
    else:
        new_records.append(record)

    new_decisions = []
    state_status = current_state.get(record["evidence_id"], {}).get("status")
    if activate and state_status != "active":
        new_decisions.append(build_decision(record["evidence_id"], "active", basis))
    if not new_records and not new_decisions:
        return record

    final_records = records + new_records
    final_decisions = decisions + new_decisions
    _project(final_records, final_decisions)
    evidence_bytes = _jsonl_bytes(evidence_path.read_bytes() if evidence_path.is_file() else b"", new_records)
    decision_bytes = _jsonl_bytes(decision_path.read_bytes() if decision_path.is_file() else b"", new_decisions)
    _replace_pair_atomically(evidence_path, decision_path, evidence_bytes, decision_bytes)
    return record


def create_derived_from_selectors(
    evidence_path: Path,
    decision_path: Path,
    parent_runs: list[str],
    parent_briefs: list[str],
    **kwargs: object,
) -> dict:
    """Resolve parent selectors and create a derived record in one locked transaction."""
    evidence_path, decision_path = _resolve_distinct_ledger_paths(evidence_path, decision_path)
    with _LedgerTransactionLock(evidence_path, decision_path):
        records = read_jsonl(evidence_path)
        parent_ids = resolve_parent_ids(records, parent_runs, parent_briefs)
        return _create_derived_locked(
            evidence_path=evidence_path,
            decision_path=decision_path,
            parent_ids=parent_ids,
            **kwargs,
        )


def append_decision(evidence_path: Path, decision_path: Path, decision: dict) -> None:
    """Append one validated curation decision only after its final state is valid."""
    evidence_path, decision_path = _resolve_distinct_ledger_paths(evidence_path, decision_path)
    with _LedgerTransactionLock(evidence_path, decision_path):
        records = read_jsonl(evidence_path)
        decisions = read_jsonl(decision_path)
        _project(records, decisions + [decision])
        new_decision_bytes = _jsonl_bytes(
            decision_path.read_bytes() if decision_path.is_file() else b"", [decision]
        )
        temporary_name = _write_bytes(decision_path, new_decision_bytes)
        try:
            os.replace(temporary_name, decision_path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def _pending_rows(records: list[dict], decisions: list[dict]) -> list[dict]:
    state = _project(records, decisions)
    rows = []
    for evidence_id, record in sorted(state.items()):
        if record["evidence_type"] != "evaluation_observation" or record["status"] != "pending_review":
            continue
        content = record["content"]
        rows.append({
            "evidence_id": evidence_id,
            "run_id": record["provenance"]["source_run_id"],
            "brief_id": record["provenance"]["brief_id"],
            "genre": record["genre"],
            "reason": content.get("reason", ""),
            "flags": content.get("flags", []),
            "notes": {
                "general_note": content.get("general_note", ""),
                "candidate_feedback": content.get("candidate_feedback", {}),
            },
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List pending human observations.")
    list_parser.add_argument("--evidence-ledger", required=True, type=Path)
    list_parser.add_argument("--decision-ledger", required=True, type=Path)

    decide_parser = subparsers.add_parser("decide", help="Record a curation decision.")
    decide_parser.add_argument("--evidence-ledger", required=True, type=Path)
    decide_parser.add_argument("--decision-ledger", required=True, type=Path)
    decide_parser.add_argument("--evidence-id", required=True)
    decide_parser.add_argument("--status", required=True, choices=["active", "rejected", "retired"])
    decide_parser.add_argument("--reason", required=True)

    create_parser = subparsers.add_parser("create-derived", help="Create a pending derived rule.")
    create_parser.add_argument("--evidence-ledger", required=True, type=Path)
    create_parser.add_argument("--decision-ledger", required=True, type=Path)
    create_parser.add_argument("--type", required=True, choices=sorted(DERIVED_KINDS))
    create_parser.add_argument("--genre", action="append", required=True)
    create_parser.add_argument("--scope", action="append", required=True)
    create_parser.add_argument("--directive", required=True)
    create_parser.add_argument("--guard-level", choices=sorted(GUARD_LEVELS))
    create_parser.add_argument("--confidence", required=True, choices=sorted(CONFIDENCE_LEVELS))
    create_parser.add_argument("--basis", required=True)
    create_parser.add_argument("--parent-run", action="append", default=[])
    create_parser.add_argument("--parent-brief", action="append", default=[])
    create_parser.add_argument("--activate", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            evidence_path, decision_path = _resolve_distinct_ledger_paths(
                args.evidence_ledger, args.decision_ledger
            )
            print(json.dumps(
                _pending_rows(read_jsonl(evidence_path), read_jsonl(decision_path)),
                ensure_ascii=False,
                sort_keys=True,
            ))
            return 0
        if args.command == "decide":
            decision = build_decision(args.evidence_id, args.status, args.reason)
            append_decision(args.evidence_ledger, args.decision_ledger, decision)
            print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
            return 0

        record = create_derived_from_selectors(
            evidence_path=args.evidence_ledger,
            decision_path=args.decision_ledger,
            parent_runs=args.parent_run,
            parent_briefs=args.parent_brief,
            kind=args.type,
            genres=args.genre,
            scopes=args.scope,
            directive=args.directive,
            guard_level=args.guard_level,
            confidence=args.confidence,
            basis=args.basis,
            activate=args.activate,
        )
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 0
    except ValueError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
