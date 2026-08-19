import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "evidence_vault.py"
SPEC = importlib.util.spec_from_file_location("evidence_vault", MODULE_PATH)
evidence_vault = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evidence_vault)

IMPORTER_PATH = SCRIPTS / "import_human_blind_feedback.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_human_blind_feedback", IMPORTER_PATH)
importer = importlib.util.module_from_spec(IMPORTER_SPEC)
assert IMPORTER_SPEC.loader is not None
IMPORTER_SPEC.loader.exec_module(importer)


POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "evidence-policy.json"


def make_record(**overrides):
    base = {
        "schema": "mind-vault-evidence/v1",
        "evidence_id": "ev-" + "1" * 24,
        "evidence_type": "guard",
        "genre": ["slam"],
        "scope": ["spoken_delivery"],
        "status": "pending_review",
        "authority": "generation_guard",
        "content": {"directive": "A slam legyen kimondható."},
        "provenance": {
            "source_kind": "human_blind_test",
            "source_run_id": "hbt-abc",
            "source_item_id": "item-01",
            "brief_id": "slam-01",
            "source_sha256": "a" * 64,
            "parent_evidence_ids": ["ev-" + "2" * 24],
        },
        "confidence": {"level": "high", "basis": "explicit human feedback"},
        "created_at": "2026-08-19T12:00:00+00:00",
        "supersedes": [],
    }
    base.update(overrides)
    return base


def make_decision(evidence_id, status, **overrides):
    base = {
        "schema": "mind-vault-evidence-decision/v1",
        "evidence_id": evidence_id,
        "status": status,
        "reason": "Curation decision.",
        "curator": "peter",
        "decided_at": "2026-08-19T13:00:00+00:00",
    }
    base.update(overrides)
    return base


def make_human_result(item_count=2, **overrides):
    items = []
    for number in range(1, item_count + 1):
        items.append({
            "item_id": f"item-{number:02d}",
            "brief_id": f"slam-{number:02d}",
            "genre": "slam",
            "choice": "left",
            "chosen_system": "engine_v3",
            "reason": f"Reason {number} is explicit.",
            "flags": ["brief_mismatch"],
            "candidate_feedback": {
                "engine_v3": {"highlight": "Strong line", "note": "Natural."},
                "legacy": {"highlight": "", "note": "Stilted."},
            },
            "general_note": "Compare the two approaches.",
            "answered_at": "2026-08-19T10:00:00+00:00",
            "draft_hashes": {"left": "a" * 64, "right": "b" * 64},
            "left_text": "SECRET FULL DRAFT",
        })
    base = {
        "schema_version": 1,
        "run_id": "hbt-" + "a" * 24,
        "seed": 20260818,
        "public_sha256": "c" * 64,
        "private_sha256": "d" * 64,
        "finalized_at": "2026-08-19T11:00:00+00:00",
        "item_count": item_count,
        "overall": {"legacy": 0, "engine_v3": item_count, "tie": 0},
        "by_genre": {"slam": {"legacy": 0, "engine_v3": item_count, "tie": 0}},
        "items": items,
        "utility_written": False,
        "learned_preference_claimed": False,
        "feedback_review_required": True,
    }
    base.update(overrides)
    return base


def make_private_key(item_count=2):
    return {
        "schema_version": 1,
        "items": {
            f"item-{number:02d}": {
                "brief_id": f"slam-{number:02d}",
                "left": "engine_v3",
                "right": "legacy",
                "left_candidate": "A",
                "right_candidate": "B",
            }
            for number in range(1, item_count + 1)
        },
    }


class EvidenceIdentityTests(unittest.TestCase):
    def test_evidence_id_is_stable_across_key_order(self):
        left = {"source_run_id": "hbt-abc", "brief_id": "slam-01", "content_sha256": "a" * 64}
        right = {"content_sha256": "a" * 64, "brief_id": "slam-01", "source_run_id": "hbt-abc"}

        self.assertEqual(evidence_vault.derive_evidence_id(left), evidence_vault.derive_evidence_id(right))

    def test_canonical_hash_uses_compact_key_sorted_unicode_json(self):
        self.assertEqual(
            evidence_vault.canonical_sha256({"z": "ár", "a": [1, True]}),
            "a3177e3c49914ac1f3a282a81457a9ef35c902f5e477a633579ecb268097c0da",
        )


class RecordValidationTests(unittest.TestCase):
    def test_voice_source_accepts_provenance_backed_own_source(self):
        record = make_record(
            evidence_type="voice_source",
            authority="voice",
            provenance={
                "source_kind": "provenance_validated_own_source",
                "origin": "drive-original",
                "source_run_id": "rag-abc",
                "source_item_id": "doc-01",
                "brief_id": "source-doc-01",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
        )

        evidence_vault.validate_record(record)

    def test_voice_source_rejects_generated_v1_draft_source_kind(self):
        record = make_record(
            evidence_type="voice_source",
            authority="voice",
            provenance={
                "source_kind": "generated_v1_draft",
                "origin": "drive-original",
                "source_run_id": "v1-run",
                "source_item_id": "draft-01",
                "brief_id": "slam-01",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
        )

        with self.assertRaisesRegex(ValueError, "voice_source provenance"):
            evidence_vault.validate_record(record)

    def test_voice_source_rejects_generated_engine_v3_draft_origin(self):
        record = make_record(
            evidence_type="voice_source",
            authority="voice",
            provenance={
                "source_kind": "provenance_validated_own_source",
                "origin": "engine_v3_draft",
                "source_run_id": "engine-run",
                "source_item_id": "draft-01",
                "brief_id": "slam-01",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
        )

        with self.assertRaisesRegex(ValueError, "voice_source provenance"):
            evidence_vault.validate_record(record)

    def test_active_guard_requires_scope_and_parent(self):
        record = make_record(status="active", scope=[])
        record["provenance"]["parent_evidence_ids"] = []

        with self.assertRaisesRegex(ValueError, "scope"):
            evidence_vault.validate_record(record)

        record["scope"] = ["spoken_delivery"]
        with self.assertRaisesRegex(ValueError, "parent"):
            evidence_vault.validate_record(record)

    def test_record_rejects_unknown_type_and_status(self):
        with self.assertRaisesRegex(ValueError, "evidence_type"):
            evidence_vault.validate_record(make_record(evidence_type="speculation"))
        with self.assertRaisesRegex(ValueError, "status"):
            evidence_vault.validate_record(make_record(status="published"))


class ProjectionTests(unittest.TestCase):
    def test_projection_applies_pending_to_active_decision(self):
        record = make_record(evidence_type="guard", status="pending_review")
        decision = make_decision(record["evidence_id"], "active")

        state = evidence_vault.project_state([record], [decision])

        self.assertEqual(state[record["evidence_id"]]["status"], "active")

    def test_projection_rejects_decision_for_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, "missing evidence"):
            evidence_vault.project_state([], [make_decision("ev-" + "3" * 24, "active")])

    def test_projection_rejects_invalid_transition(self):
        record = make_record(status="rejected")

        with self.assertRaisesRegex(ValueError, "invalid transition"):
            evidence_vault.project_state([record], [make_decision(record["evidence_id"], "active")])

    def test_projection_rejects_same_id_with_different_content(self):
        original = make_record()
        conflicting = make_record(content={"directive": "Different instruction."})

        with self.assertRaisesRegex(ValueError, "duplicate evidence_id"):
            evidence_vault.project_state([original, conflicting], [])

    def test_projection_rejects_non_monotonic_decision_time(self):
        record = make_record()
        first = make_decision(record["evidence_id"], "active", decided_at="2026-08-19T14:00:00+00:00")
        second = make_decision(record["evidence_id"], "retired", decided_at="2026-08-19T13:00:00+00:00")

        with self.assertRaisesRegex(ValueError, "non-monotonic"):
            evidence_vault.project_state([record], [first, second])


class LedgerAndPolicyTests(unittest.TestCase):
    def test_read_jsonl_reports_path_and_line_for_malformed_row(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "evidence.jsonl"
            ledger.write_text('{"valid": true}\n{broken}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"evidence\.jsonl.*line 2"):
                evidence_vault.read_jsonl(ledger)

    def test_policy_loads_versioned_static_configuration(self):
        policy = evidence_vault.load_policy(POLICY_PATH)

        self.assertEqual(policy["schema"], "mind-vault-evidence-policy/v1")
        self.assertEqual(policy["policy_version"], "2026-08-19.1")
        self.assertIn("spoken_delivery", policy["allowed_scopes"])


class HumanBlindImportTests(unittest.TestCase):
    def test_import_builds_pending_observation_without_side_mapping(self):
        records = importer.build_observation_records(make_human_result(), make_private_key())

        self.assertEqual(len(records), 2)
        self.assertTrue(all(item["status"] == "pending_review" for item in records))
        rendered = json.dumps(records, ensure_ascii=False)
        self.assertNotIn('"left"', rendered)
        self.assertNotIn('"right"', rendered)
        self.assertNotIn("SECRET FULL DRAFT", rendered)
        self.assertEqual(
            set(records[0]["content"]["draft_sha256_by_system"]), {"engine_v3", "legacy"}
        )
        self.assertEqual(records[0]["evidence_type"], "evaluation_observation")
        evidence_vault.validate_record(records[0])

    def test_import_is_idempotent(self):
        records = importer.build_observation_records(make_human_result(), make_private_key())
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "evidence.jsonl"
            self.assertEqual(importer.append_new_records(records, ledger), 2)
            self.assertEqual(importer.append_new_records(records, ledger), 0)
            self.assertEqual(len(evidence_vault.read_jsonl(ledger)), 2)

    def test_import_records_do_not_mutate_the_immutable_result(self):
        result = make_human_result()
        records = importer.build_observation_records(result, make_private_key())

        records[0]["content"]["candidate_feedback"]["engine_v3"]["note"] = "Changed later"

        self.assertEqual(result["items"][0]["candidate_feedback"]["engine_v3"]["note"], "Natural.")

    def test_import_preserves_valid_string_candidate_feedback(self):
        records = importer.build_observation_records(make_human_result(), make_private_key())

        self.assertEqual(
            records[0]["content"]["candidate_feedback"],
            {
                "engine_v3": {"highlight": "Strong line", "note": "Natural."},
                "legacy": {"highlight": "", "note": "Stilted."},
            },
        )

    def test_import_rejects_candidate_feedback_nested_full_draft_key(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["engine_v3"]["full_draft"] = {
            "text": "SECRET FULL DRAFT",
        }

        with self.assertRaisesRegex(ValueError, "candidate_feedback"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_candidate_feedback_side_key(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["legacy"]["left"] = "SECRET FULL DRAFT"

        with self.assertRaisesRegex(ValueError, "candidate_feedback"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_candidate_feedback_candidate_label_key(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["engine_v3"]["candidate_label"] = "A"

        with self.assertRaisesRegex(ValueError, "candidate_feedback"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_non_string_candidate_feedback_values(self):
        for field, value in (("highlight", {"text": "SECRET FULL DRAFT"}), ("note", ["not text"])):
            with self.subTest(field=field):
                result = make_human_result()
                result["items"][0]["candidate_feedback"]["engine_v3"][field] = value
                with self.assertRaisesRegex(ValueError, "candidate_feedback"):
                    importer.build_observation_records(result, make_private_key())

    def test_import_cli_does_not_append_rejected_candidate_feedback(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["engine_v3"]["full_draft"] = {
            "text": "SECRET FULL DRAFT",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            private_key_path = root / "private-key.json"
            ledger = root / "evidence.jsonl"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            private_key_path.write_text(json.dumps(make_private_key()), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(IMPORTER_PATH), "--result", str(result_path),
                 "--private-key", str(private_key_path), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(ledger.exists())

    def test_import_accepts_actual_finalized_shape_without_boolean_marker(self):
        importer.validate_human_result(make_human_result())

    def test_import_rejects_explicit_false_finalized_marker(self):
        with self.assertRaisesRegex(ValueError, "finalized"):
            importer.validate_human_result(make_human_result(finalized=False))

    def test_import_rejects_missing_or_invalid_finalized_timestamp(self):
        missing = make_human_result()
        missing.pop("finalized_at")
        with self.assertRaisesRegex(ValueError, "finalized_at"):
            importer.validate_human_result(missing)
        with self.assertRaisesRegex(ValueError, "finalized_at"):
            importer.validate_human_result(make_human_result(finalized_at="not-a-timestamp"))

    def test_import_rejects_item_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "item_count"):
            importer.validate_human_result(make_human_result(item_count=2, items=[]))

    def test_import_rejects_duplicate_brief_ids(self):
        result = make_human_result()
        result["items"][1]["brief_id"] = result["items"][0]["brief_id"]
        with self.assertRaisesRegex(ValueError, "brief_id"):
            importer.validate_human_result(result)

    def test_import_rejects_invalid_draft_hash(self):
        result = make_human_result()
        result["items"][0]["draft_hashes"]["left"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "draft_hashes"):
            importer.validate_human_result(result)

    def test_import_rejects_unknown_system(self):
        result = make_human_result()
        result["items"][0]["chosen_system"] = "unknown"
        with self.assertRaisesRegex(ValueError, "chosen_system"):
            importer.validate_human_result(result)

    def test_import_rejects_safety_flags_that_allow_learning(self):
        for field, value in (
            ("utility_written", True),
            ("learned_preference_claimed", True),
            ("feedback_review_required", False),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    importer.validate_human_result(make_human_result(**{field: value}))

    def test_import_rejects_private_key_brief_or_system_mapping_mismatch(self):
        bad_brief = make_private_key()
        bad_brief["items"]["item-01"]["brief_id"] = "other-brief"
        with self.assertRaisesRegex(ValueError, "brief_id"):
            importer.build_observation_records(make_human_result(), bad_brief)

        bad_system = make_private_key()
        bad_system["items"]["item-01"]["right"] = "unknown"
        with self.assertRaisesRegex(ValueError, "system mapping"):
            importer.build_observation_records(make_human_result(), bad_system)

    def test_import_cli_reports_atomic_append_counts_and_ledger_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            private_key_path = root / "private-key.json"
            ledger = root / "evidence.jsonl"
            result_path.write_text(json.dumps(make_human_result()), encoding="utf-8")
            private_key_path.write_text(json.dumps(make_private_key()), encoding="utf-8")

            first = subprocess.run(
                [sys.executable, str(IMPORTER_PATH), "--result", str(result_path),
                 "--private-key", str(private_key_path), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(first.stdout, first.stderr)
            self.assertEqual(json.loads(first.stdout)["added_records"], 2)

            second = subprocess.run(
                [sys.executable, str(IMPORTER_PATH), "--result", str(result_path),
                 "--private-key", str(private_key_path), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertTrue(second.stdout, second.stderr)
            report = json.loads(second.stdout)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(report["source_run_id"], "hbt-" + "a" * 24)
            self.assertEqual(report["input_items"], 2)
            self.assertEqual(report["added_records"], 0)
            self.assertEqual(report["existing_records"], 2)
            self.assertRegex(report["ledger_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
