import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("generation_critique_workflow", SCRIPTS / "generation_critique_workflow.py")
workflow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(workflow)


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


class GenerationCritiqueWorkflowTests(unittest.TestCase):
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

    def test_attached_draft_has_integrity_hash_but_feedback_stores_no_text(self):
        public, _ = workflow.build_workflow(engine_packet())
        attached = workflow.attach_draft(public, "A kész draft.")

        self.assertEqual(attached["critique_job"]["draft"], "A kész draft.")
        self.assertEqual(len(attached["critique_job"]["draft_sha256"]), 64)
        self.assertFalse(attached["feedback_contract"]["store_raw_brief_or_draft"])


if __name__ == "__main__":
    unittest.main()
