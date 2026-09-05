#!/usr/bin/env python3
"""Build a deterministic, system-blind 30-pair human evaluation pack."""

from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


ALLOWED_FLAGS = frozenset({
    "brief_mismatch",
    "genre_mismatch",
    "false_peter_voice",
    "mannerism_caricature",
    "hard_guard_problem",
})
MAX_REASON_LENGTH = 2_000
MAX_FEEDBACK_LENGTH = 500
MAX_NOTE_LENGTH = 1_500


def canonical_sha256(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _benchmark_rows(result: dict) -> list[dict]:
    rows = list(result.get("briefs") or result.get("generation_jobs") or [])
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("benchmark briefs must be objects")
    return rows


def benchmark_briefs(result: dict) -> list[str]:
    rows = _benchmark_rows(result)
    brief_ids = [str(row.get("brief_id", "")) for row in rows]
    if len(brief_ids) != 30 or len(set(brief_ids)) != 30 or any(not brief_id for brief_id in brief_ids):
        raise ValueError("benchmark must contain exactly 30 unique briefs")
    genres = Counter(str(row.get("genre", "")) for row in rows)
    if not genres or any(not genre or count != 3 for genre, count in genres.items()):
        raise ValueError("benchmark must contain exactly three briefs per genre")
    return brief_ids


def _public_brief_rows(result: dict, jobs: list[dict]) -> list[dict]:
    """Join aggregate IDs/genres to public brief text from generation jobs."""
    brief_ids = benchmark_briefs(result)
    result_by_id = {str(row["brief_id"]): row for row in _benchmark_rows(result)}
    jobs_by_brief: dict[str, list[dict]] = {}
    for job in jobs:
        jobs_by_brief.setdefault(str(job.get("brief_id", "")), []).append(job)
    if set(jobs_by_brief) != set(brief_ids):
        raise ValueError("benchmark results and generation jobs must contain the same brief IDs")

    public_rows = []
    for brief_id in brief_ids:
        matching = jobs_by_brief[brief_id]
        candidates = {str(job.get("candidate", "")) for job in matching}
        genres = {str(job.get("genre", "")) for job in matching}
        briefs = {str(job.get("brief", "")).strip() for job in matching}
        result_genre = str(result_by_id[brief_id].get("genre", ""))
        if len(matching) != 2 or candidates != {"A", "B"}:
            raise ValueError(f"generation jobs must contain one A/B pair for {brief_id}")
        if genres != {result_genre} or not result_genre:
            raise ValueError(f"benchmark and generation job genres differ for {brief_id}")
        if len(briefs) != 1 or not next(iter(briefs)):
            raise ValueError(f"generation jobs must contain one non-empty brief for {brief_id}")
        public_rows.append({
            "brief_id": brief_id,
            "genre": result_genre,
            "brief": next(iter(briefs)),
        })
    return public_rows


def _domain_rng(seed: int, domain: str) -> random.Random:
    material = f"human-blind-test-v1:{seed}:{domain}".encode("utf-8")
    derived_seed = int.from_bytes(hashlib.sha256(material).digest(), "big")
    return random.Random(derived_seed)


def balanced_positions(brief_ids: list[str], seed: int) -> dict[str, bool]:
    if len(brief_ids) != 30 or len(set(brief_ids)) != 30:
        raise ValueError("balanced positions require 30 unique brief IDs")
    shuffled = list(brief_ids)
    _domain_rng(seed, "candidate-positions").shuffle(shuffled)
    return {brief_id: index < 15 for index, brief_id in enumerate(shuffled)}


def _draft_text(jobs: list[dict], drafts_dir: Path, brief_id: str, candidate: str) -> str:
    matching = [job for job in jobs if str(job.get("brief_id")) == brief_id and str(job.get("candidate")) == candidate]
    if len(matching) != 1:
        raise ValueError(f"expected one generation job for {brief_id}-{candidate}")
    job_id = str(matching[0].get("job_id") or f"{brief_id}-{candidate}")
    path = drafts_dir / f"{job_id}.md"
    if not path.is_file():
        raise ValueError(f"missing draft: {path}")
    return path.read_text(encoding="utf-8-sig").strip()


def build_pack(
    result: dict,
    jobs: list[dict],
    drafts_dir: Path,
    blind_key: dict,
    seed: int,
) -> tuple[dict, dict, dict]:
    public_briefs = _public_brief_rows(result, jobs)
    brief_ids = [row["brief_id"] for row in public_briefs]
    by_brief = {row["brief_id"]: row for row in public_briefs}
    engine_left = balanced_positions(brief_ids, seed)
    shuffled = list(brief_ids)
    _domain_rng(seed, "item-order").shuffle(shuffled)
    public_items = []
    private_items = {}
    for index, brief_id in enumerate(shuffled, start=1):
        mapping = blind_key.get(brief_id) or {}
        candidates = {str(system): candidate for candidate, system in mapping.items()}
        if set(candidates) != {"legacy", "engine_v3"}:
            raise ValueError(f"blind key must map A and B to both systems for {brief_id}")
        left_system = "engine_v3" if engine_left[brief_id] else "legacy"
        right_system = "legacy" if left_system == "engine_v3" else "engine_v3"
        left_candidate = candidates[left_system]
        right_candidate = candidates[right_system]
        left_text = _draft_text(jobs, drafts_dir, brief_id, left_candidate)
        right_text = _draft_text(jobs, drafts_dir, brief_id, right_candidate)
        item_id = f"item-{index:02d}"
        source = by_brief[brief_id]
        public_items.append(
            {
                "item_id": item_id,
                "brief_id": brief_id,
                "genre": source["genre"],
                "brief": source["brief"],
                "left_text": left_text,
                "right_text": right_text,
                "draft_hashes": {
                    "left": hashlib.sha256(left_text.encode("utf-8")).hexdigest(),
                    "right": hashlib.sha256(right_text.encode("utf-8")).hexdigest(),
                },
            }
        )
        private_items[item_id] = {
            "brief_id": brief_id,
            "left": left_system,
            "right": right_system,
            "left_candidate": left_candidate,
            "right_candidate": right_candidate,
        }
    public = {"schema_version": 1, "items": public_items}
    private = {"schema_version": 1, "items": private_items}
    manifest = {
        "schema_version": 1,
        "item_count": len(public_items),
        "seed": seed,
        "public_sha256": canonical_sha256(public),
        "private_sha256": canonical_sha256(private),
    }
    errors = validate_public_pack(public)
    if errors:
        raise ValueError("invalid public pack: " + "; ".join(errors))
    return public, private, manifest


def validate_public_pack(pack: dict) -> list[str]:
    errors = []
    items = pack.get("items")
    if not isinstance(items, list) or len(items) != 30:
        return ["public pack must contain exactly 30 items"]
    required = {"item_id", "brief_id", "genre", "brief", "left_text", "right_text", "draft_hashes"}
    item_ids = [str(item.get("item_id", "")) for item in items if isinstance(item, dict)]
    if len(item_ids) != 30 or len(set(item_ids)) != 30:
        errors.append("public item IDs must be unique")
    for item in items:
        if not isinstance(item, dict) or set(item) != required:
            errors.append("public items must contain only the required public fields")
            break
        if not all(isinstance(item[field], str) and item[field] for field in ("item_id", "brief_id", "genre", "brief", "left_text", "right_text")):
            errors.append("public item text fields must be non-empty strings")
            break
        hashes = item["draft_hashes"]
        if not isinstance(hashes, dict) or set(hashes) != {"left", "right"}:
            errors.append("public items must include left and right draft hashes")
            break
    return errors


def _validate_run_public_pack(pack: dict) -> list[str]:
    """Validate the public schema without assuming a malformed run has 30 items."""
    errors = []
    items = pack.get("items") if isinstance(pack, dict) else None
    if not isinstance(items, list) or not items:
        return ["public pack must contain items"]
    required = {"item_id", "brief_id", "genre", "brief", "left_text", "right_text", "draft_hashes"}
    item_ids = [str(item.get("item_id", "")) for item in items if isinstance(item, dict)]
    if len(item_ids) != len(items) or not all(item_ids) or len(set(item_ids)) != len(item_ids):
        errors.append("public item IDs must be unique")
    for item in items:
        if not isinstance(item, dict) or set(item) != required:
            errors.append("public items must contain only the required public fields")
            break
        if not all(isinstance(item[field], str) and item[field] for field in ("item_id", "brief_id", "genre", "brief", "left_text", "right_text")):
            errors.append("public item text fields must be non-empty strings")
            break
        hashes = item["draft_hashes"]
        if not isinstance(hashes, dict) or set(hashes) != {"left", "right"}:
            errors.append("public items must include left and right draft hashes")
            break
    return errors


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_run_id(manifest: dict, progress_path: Path, result_path: Path) -> str:
    """Create an opaque, stable ID for one pack and output-path pair."""
    material = {
        "schema": "human-blind-run-v1",
        "public_sha256": manifest["public_sha256"],
        "private_sha256": manifest["private_sha256"],
        "seed": manifest["seed"],
        "progress_path_sha256": hashlib.sha256(
            str(progress_path.resolve(strict=False)).encode("utf-8")
        ).hexdigest(),
        "result_path_sha256": hashlib.sha256(
            str(result_path.resolve(strict=False)).encode("utf-8")
        ).hexdigest(),
    }
    return f"hbt-{canonical_sha256(material)[:24]}"


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class BlindTestRun:
    """Persist and unblind one local human blind-test run without learning side effects."""

    def __init__(self, public: dict, private: dict, manifest: dict,
                 progress_path: Path, result_path: Path):
        self.public = public
        self.private = private
        self.manifest = manifest
        self.progress_path = Path(progress_path)
        self.result_path = Path(result_path)
        self._lock = RLock()
        self._validate_inputs()
        self.seed = self.manifest["seed"]
        self.run_id = _derive_run_id(self.manifest, self.progress_path, self.result_path)
        self._items = {item["item_id"]: item for item in self.public["items"]}

    def _validate_inputs(self) -> None:
        errors = _validate_run_public_pack(self.public)
        if errors:
            raise ValueError("invalid public pack: " + "; ".join(errors))
        if not isinstance(self.manifest, dict):
            raise ValueError("manifest must be an object")
        if self.manifest.get("item_count") != len(self.public["items"]):
            raise ValueError("manifest item count does not match public pack")
        seed = self.manifest.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("manifest seed must be an integer")
        if self.manifest.get("public_sha256") != canonical_sha256(self.public):
            raise ValueError("public manifest hash mismatch")
        if self.manifest.get("private_sha256") != canonical_sha256(self.private):
            raise ValueError("private manifest hash mismatch")
        private_items = self.private.get("items") if isinstance(self.private, dict) else None
        if not isinstance(private_items, dict) or set(private_items) != {item["item_id"] for item in self.public["items"]}:
            raise ValueError("private key items do not match public pack")
        for item_id, mapping in private_items.items():
            if not isinstance(mapping, dict) or {mapping.get("left"), mapping.get("right")} != {"legacy", "engine_v3"}:
                raise ValueError(f"private key has invalid system mapping for {item_id}")

    def _load_progress(self) -> dict:
        if not self.progress_path.exists():
            return {
                "schema_version": 1,
                "run_id": self.run_id,
                "seed": self.seed,
                "public_sha256": self.manifest["public_sha256"],
                "created_at": _utc_timestamp(),
                "answers": {},
            }
        try:
            progress = json.loads(self.progress_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid progress file: {error}") from error
        if (
            not isinstance(progress, dict)
            or progress.get("public_sha256") != self.manifest["public_sha256"]
            or progress.get("run_id") != self.run_id
            or progress.get("seed") != self.seed
        ):
            raise ValueError("progress does not belong to this public pack")
        answers = progress.get("answers")
        if not isinstance(answers, dict):
            raise ValueError("progress answers must be an object")
        return progress

    def _load_result(self) -> dict | None:
        if not self.result_path.exists():
            return None
        try:
            result = json.loads(self.result_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid finalized result: {error}") from error
        if (
            not isinstance(result, dict)
            or result.get("public_sha256") != self.manifest["public_sha256"]
            or result.get("run_id") != self.run_id
            or result.get("seed") != self.seed
        ):
            raise ValueError("finalized result does not belong to this public pack")
        return result

    @staticmethod
    def _bounded_text(value: str, field: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        normalized = value.strip()
        if len(normalized) > maximum:
            raise ValueError(f"{field} must be at most {maximum} characters")
        return normalized

    def snapshot(self) -> dict:
        with self._lock:
            progress = self._load_progress()
            finalized = self._load_result() is not None
            answers = progress["answers"]
            items = []
            for item in self.public["items"]:
                visible = dict(item)
                answer = answers.get(item["item_id"])
                if answer:
                    visible["answer"] = dict(answer)
                items.append(visible)
            return {
                "schema_version": 1,
                "item_count": len(items),
                "answered_count": len(answers),
                "finalized": finalized,
                "items": items,
            }

    def save_answer(self, item_id: str, choice: str, reason: str,
                    flags: list[str] | None = None,
                    left_highlight: str = "", right_highlight: str = "",
                    left_note: str = "", right_note: str = "",
                    general_note: str = "") -> dict:
        with self._lock:
            if self._load_result() is not None:
                raise RuntimeError("test has already been finalized")
            if item_id not in self._items:
                raise ValueError("unknown item")
            if choice not in {"left", "right", "tie"}:
                raise ValueError("choice must be left, right, or tie")
            reason = self._bounded_text(reason, "reason", MAX_REASON_LENGTH)
            if len(reason) < 10:
                raise ValueError("reason must be at least 10 characters")
            if flags is None:
                flags = []
            if not isinstance(flags, list) or any(not isinstance(flag, str) for flag in flags):
                raise ValueError("flags must be a list")
            normalized_flags = [flag.strip() for flag in flags]
            if len(set(normalized_flags)) != len(normalized_flags) or any(flag not in ALLOWED_FLAGS for flag in normalized_flags):
                raise ValueError("flags contain an unsupported value")
            answer = {
                "item_id": item_id,
                "choice": choice,
                "reason": reason,
                "flags": normalized_flags,
                "left_highlight": self._bounded_text(left_highlight, "left_highlight", MAX_FEEDBACK_LENGTH),
                "right_highlight": self._bounded_text(right_highlight, "right_highlight", MAX_FEEDBACK_LENGTH),
                "left_note": self._bounded_text(left_note, "left_note", MAX_NOTE_LENGTH),
                "right_note": self._bounded_text(right_note, "right_note", MAX_NOTE_LENGTH),
                "general_note": self._bounded_text(general_note, "general_note", MAX_NOTE_LENGTH),
                "updated_at": _utc_timestamp(),
            }
            progress = self._load_progress()
            progress["answers"][item_id] = answer
            progress["updated_at"] = answer["updated_at"]
            _atomic_write_json(self.progress_path, progress)
            return self.snapshot()

    def finalized_result(self) -> dict:
        """Return the already-written immutable result without triggering unblinding."""
        with self._lock:
            result = self._load_result()
            if result is None:
                raise RuntimeError("test is not finalized")
            return result

    def finalize(self) -> dict:
        with self._lock:
            existing = self._load_result()
            if existing is not None:
                return existing
            progress = self._load_progress()
            answers = progress["answers"]
            item_count = len(self._items)
            if item_count != 30 or len(answers) != 30 or set(answers) != set(self._items):
                raise RuntimeError("all 30 answers are required before finalization")
            overall = {"legacy": 0, "engine_v3": 0, "tie": 0}
            by_genre: dict[str, dict[str, int]] = {}
            result_items = []
            for public_item in self.public["items"]:
                item_id = public_item["item_id"]
                answer = answers[item_id]
                private_item = self.private["items"][item_id]
                chosen_system = private_item[answer["choice"]] if answer["choice"] != "tie" else None
                overall[chosen_system or "tie"] += 1
                genre = public_item["genre"]
                genre_totals = by_genre.setdefault(genre, {"legacy": 0, "engine_v3": 0, "tie": 0})
                genre_totals[chosen_system or "tie"] += 1
                candidate_feedback = {
                    private_item["left"]: {
                        "highlight": answer["left_highlight"],
                        "note": answer["left_note"],
                    },
                    private_item["right"]: {
                        "highlight": answer["right_highlight"],
                        "note": answer["right_note"],
                    },
                }
                result_items.append({
                    "item_id": item_id,
                    "brief_id": public_item["brief_id"],
                    "genre": genre,
                    "choice": answer["choice"],
                    "chosen_system": chosen_system,
                    "reason": answer["reason"],
                    "flags": answer["flags"],
                    "candidate_feedback": candidate_feedback,
                    "general_note": answer["general_note"],
                    "answered_at": answer["updated_at"],
                    "draft_hashes": dict(public_item["draft_hashes"]),
                })
            result = {
                "schema_version": 1,
                "run_id": self.run_id,
                "seed": self.seed,
                "public_sha256": self.manifest["public_sha256"],
                "private_sha256": self.manifest["private_sha256"],
                "finalized_at": _utc_timestamp(),
                "item_count": item_count,
                "overall": overall,
                "by_genre": by_genre,
                "items": result_items,
                "utility_written": False,
                "learned_preference_claimed": False,
                "feedback_review_required": True,
            }
            _atomic_write_json(self.result_path, result)
            return result
