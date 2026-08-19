import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("generation_critique_workflow", SCRIPTS / "generation_critique_workflow.py")
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow)

ENGINE_SPEC = importlib.util.spec_from_file_location("mind_vault_engine_for_workflow_test", SCRIPTS / "mind_vault_engine.py")
engine = importlib.util.module_from_spec(ENGINE_SPEC)
assert ENGINE_SPEC.loader is not None
ENGINE_SPEC.loader.exec_module(engine)


def engine_packet(state="cold-start"):
    return {
        "brief_plan": {
            "brief": "Írj rövid slamet egy elromlott kávéfőzőről.",
            "genre": {"value": "slam"},
            "purpose": {"value": "előadás"},
            "audience": {"value": "klubközönség"},
            "negative_preferences": ["Ne legyen technológiai motívumkatalógus."],
        },
        "channels": {"dialogue": {"active": False}},
        "preference_reranker": {
            "state": state,
            "ranked": [
                {"id": "alpha", "channel": "content", "technique_tags": ["callback"], "evidence": [{"text": "részlet"}]},
                {"id": "beta", "channel": "style", "technique_tags": ["spoken-orality"], "evidence": []},
            ],
        },
        "evidence_compiler": {
            "execution_evidence": [
                {"id": "alpha", "channel": "content", "technique_tags": ["callback"], "evidence": [{"text": "részlet"}]},
                {"id": "beta", "channel": "style", "technique_tags": ["spoken-orality"], "evidence": []},
            ],
            "generation_contract": {"do": ["Mechanikát vigyél át."], "do_not": ["Ne másolj mondatot."]},
        },
        "retrieval": {"run_id": "run-1", "variation_seed": "seed-1"},
    }


def v1_packet():
    packet = engine_packet()
    packet["schema"] = "mind-vault-engine-packet/v1"
    return packet


def v2_packet_with_curated_evidence():
    packet = engine_packet()
    packet["schema"] = "mind-vault-engine-packet/v2"
    packet["evidence_policy"] = {
        "schema": "mind-vault-evidence-policy/v1",
        "policy_version": "policy-7",
        "state": "manual_policy_cold_start",
        "ledger_sha256": "a" * 64,
    }
    packet["selected_evidence"] = {
        "voice": [],
        "mechanisms": [
            {
                "evidence_id": "ev-mechanism",
                "genre": ["slam"],
                "scope": ["spoken_delivery"],
                "directive": "Építs visszatérő színpadi motívumot.",
                "level": "soft",
                "confidence": "high",
                "score": 1.7,
                "reasons": ["human reason"],
                "observation": "private observation",
                "parent_evidence_ids": ["ev-private-parent"],
                "source_path": "C:/private/evidence.jsonl",
            }
        ],
        "guards": [
            {
                "evidence_id": "ev-hard-guard",
                "genre": ["slam"],
                "scope": ["output_surface"],
                "directive": "Ne használj Markdown címsort nem Markdown célfelületen.",
                "level": "hard",
                "confidence": "high",
                "score": 2.1,
                "reasons": ["human reason"],
                "observation": "private observation",
                "parent_evidence_ids": ["ev-private-parent"],
                "source_path": "C:/private/evidence.jsonl",
            },
            {
                "evidence_id": "ev-soft-guard",
                "genre": ["slam"],
                "scope": ["spoken_delivery"],
                "directive": "Lehetőleg rövidítsd a levegőtlen mondatokat.",
                "level": "soft",
                "confidence": "medium",
                "reasons": ["human reason"],
            },
        ],
    }
    return packet


def producer_portfolio():
    return {
        "run_id": "engine-run-actual",
        "rag_root": "safe-rag",
        "retrieval_confidence": {"level": "high"},
        "selection_policy": {"method": "dual-channel"},
        "portfolio_coverage": {"modes": ["spoken-performance"]},
        "author_writing_sheet": {"dialogue_support": {"transfer_strength": "none"}},
        "sources": [
            {
                "id": "alpha",
                "title": "Első",
                "retrieval_channel": "content",
                "portfolio_role": "anchor",
                "technique_tags": ["callback"],
                "evidence": [{"text": "Biztonságos saját evidence."}],
            }
        ],
        "contrastive_calibration": {
            "execution_set": [
                {
                    "id": "alpha",
                    "title": "Első",
                    "distance": 0.1,
                    "use": "Extract one transferable mechanism for this brief.",
                }
            ],
            "contrast_set": [],
        },
        "cross_genre_bridges": [],
    }


class GenerationCritiqueWorkflowTests(unittest.TestCase):
    def test_v2_workflow_transfers_only_sanitized_curated_rules(self):
        public, private = workflow.build_workflow(v2_packet_with_curated_evidence(), "seed-1")

        expected_guard = {
            "evidence_id": "ev-hard-guard",
            "genre": ["slam"],
            "scope": ["output_surface"],
            "directive": "Ne használj Markdown címsort nem Markdown célfelületen.",
            "level": "hard",
            "confidence": "high",
        }
        self.assertEqual(public["generation_job"]["curated_guards"][0], expected_guard)
        self.assertEqual(public["critique_job"]["curated_guards"][0], expected_guard)
        rendered_public = json.dumps(public, ensure_ascii=False)
        rendered_private = json.dumps(private, ensure_ascii=False)
        for secret in ("human reason", "private observation", "ev-private-parent", "C:/private/evidence.jsonl"):
            self.assertNotIn(secret, rendered_public)
            self.assertNotIn(secret, rendered_private)
        self.assertEqual(private["engine_packet_schema"], "mind-vault-engine-packet/v2")
        self.assertEqual(private["evidence_policy_version"], "policy-7")
        self.assertEqual(private["evidence_ledger_sha256"], "a" * 64)
        self.assertFalse(private["learned_preference_claimed"])

    def test_v1_packet_keeps_existing_public_job_shape_with_empty_curated_lists(self):
        public, private = workflow.build_workflow(v1_packet(), "seed-1")

        self.assertEqual(public["generation_job"]["curated_mechanisms"], [])
        self.assertEqual(public["generation_job"]["curated_guards"], [])
        self.assertEqual(public["critique_job"]["curated_mechanisms"], [])
        self.assertEqual(public["critique_job"]["curated_guards"], [])
        self.assertEqual(private["engine_packet_schema"], "mind-vault-engine-packet/v1")
        self.assertIsNone(private["evidence_policy_version"])
        self.assertIsNone(private["evidence_ledger_sha256"])

    def test_curated_guard_identity_changes_with_id_or_directive(self):
        original = v2_packet_with_curated_evidence()
        changed_id = copy.deepcopy(original)
        changed_id["selected_evidence"]["guards"][0]["evidence_id"] = "ev-other-guard"
        changed_directive = copy.deepcopy(original)
        changed_directive["selected_evidence"]["guards"][0]["directive"] = "Másik guard."

        original_public, _ = workflow.build_workflow(original, "seed-1")
        changed_id_public, _ = workflow.build_workflow(changed_id, "seed-1")
        changed_directive_public, _ = workflow.build_workflow(changed_directive, "seed-1")

        self.assertNotEqual(original_public["workflow_id"], changed_id_public["workflow_id"])
        self.assertNotEqual(original_public["workflow_id"], changed_directive_public["workflow_id"])

    def test_only_hard_curated_guards_become_release_checks(self):
        public, _ = workflow.build_workflow(v2_packet_with_curated_evidence(), "seed-1")

        checks = public["critique_job"]["genre_quality_contract"]["release_checks"]
        curated_checks = [item for item in checks if item["id"].startswith("curated:")]
        self.assertEqual(
            curated_checks,
            [
                {
                    "id": "curated:ev-hard-guard",
                    "question": "Ne használj Markdown címsort nem Markdown célfelületen.",
                    "hard": True,
                }
            ],
        )
        self.assertEqual(len(public["generation_job"]["curated_guards"]), 2)

    def test_unknown_engine_packet_schema_is_rejected(self):
        packet = v1_packet()
        packet["schema"] = "mind-vault-engine-packet/v99"

        with self.assertRaisesRegex(ValueError, "Unsupported Engine packet schema"):
            workflow.build_workflow(packet, "seed-1")

    def test_cli_requires_explicit_engine_packet_schema(self):
        packet = engine_packet()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            packet_path = root / "packet.json"
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            argv = [
                "generation_critique_workflow.py",
                "--engine-packet",
                str(packet_path),
                "--output-dir",
                str(root / "output"),
            ]

            with mock.patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(SystemExit, "explicit supported schema"):
                    workflow.main()

    def test_workflow_is_deterministic_and_links_generation_to_critique(self):
        first, _ = workflow.build_workflow(engine_packet())
        second, _ = workflow.build_workflow(engine_packet())

        self.assertEqual(first["workflow_id"], second["workflow_id"])
        self.assertEqual(first["critique_job"]["input_contract"], "A generation_job draftja változtatás nélkül.")
        self.assertIn("spoken-orality", {item["id"] for item in first["critique_job"]["genre_quality_contract"]["release_checks"]})

    def test_public_job_is_blind_while_private_manifest_keeps_provenance(self):
        public, private = workflow.build_workflow(engine_packet())
        rendered = str(public)

        self.assertNotIn("alpha", rendered)
        self.assertNotIn("beta", rendered)
        self.assertEqual([item["source_label"] for item in public["generation_job"]["evidence_sources"]], ["S1", "S2"])
        self.assertEqual(private["source_linkage"], [{"source_label": "S1", "id": "alpha"}, {"source_label": "S2", "id": "beta"}])

    def test_cold_start_is_preserved_without_claiming_learned_preference(self):
        _, private = workflow.build_workflow(engine_packet("cold-start"))

        self.assertEqual(private["reranker_state"], "cold-start")
        self.assertFalse(private["learned_preference_claimed"])

    def test_actual_engine_packet_preserves_mechanism_and_run_provenance(self):
        plan = engine.plan_brief("Írj rövid slamet egy elromlott kávéfőzőről.")
        packet = engine.compile_engine_packet(producer_portfolio(), plan)

        public, private = workflow.build_workflow(packet)
        evidence = public["generation_job"]["evidence_sources"][0]

        self.assertEqual(evidence["technique_tags"], ["callback"])
        self.assertIn("mechanism", evidence["transfer_instruction"])
        self.assertEqual(private["engine_run_id"], "engine-run-actual")

    def test_legacy_singular_mechanism_packet_remains_consumable(self):
        packet = engine_packet()
        packet["retrieval_run_id"] = "legacy-engine-run"
        packet["retrieval"].pop("run_id")
        for source in packet["evidence_compiler"]["execution_evidence"]:
            source["mechanism"] = source["technique_tags"][0]
            source.pop("technique_tags")

        public, private = workflow.build_workflow(packet)
        first = public["generation_job"]["evidence_sources"][0]

        self.assertEqual(first["technique_tags"], ["callback"])
        self.assertIn("callback", first["transfer_instruction"])
        self.assertEqual(private["engine_run_id"], "legacy-engine-run")

    def test_attached_draft_has_integrity_hash_but_feedback_stores_no_text(self):
        public, _ = workflow.build_workflow(engine_packet())
        attached = workflow.attach_draft(public, "A kész draft.")

        self.assertEqual(attached["critique_job"]["draft"], "A kész draft.")
        self.assertEqual(len(attached["critique_job"]["draft_sha256"]), 64)
        self.assertFalse(attached["feedback_contract"]["store_raw_brief_or_draft"])


if __name__ == "__main__":
    unittest.main()
