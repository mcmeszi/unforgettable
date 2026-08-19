import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evidence_vault.py"
SPEC = importlib.util.spec_from_file_location("evidence_vault", MODULE_PATH)
evidence_vault = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evidence_vault)


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


if __name__ == "__main__":
    unittest.main()
