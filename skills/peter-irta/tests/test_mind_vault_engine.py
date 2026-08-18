import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


engine = load_module("mind_vault_engine")


def portfolio(transfer_strength="conditional", utility=0.0):
    return {
        "run_id": "run-1",
        "rag_root": "safe-rag",
        "retrieval_confidence": {"level": "high"},
        "selection_policy": {"method": "dual-channel"},
        "portfolio_coverage": {"modes": ["spoken-performance"]},
        "author_writing_sheet": {
            "genre": "slam",
            "caricature_guards": ["Ne legyen kötelező kérdéshalmozás."],
            "dialogue_support": {
                "transfer_strength": transfer_strength,
                "strong_for": ["response-opening", "question-answer-rhythm"],
                "weak_for": ["rhyme", "image-system"],
                "guardrails": ["Ne másold az elütéseket."],
                "precedence": "fresh feedback > direct corpus > Slack profile",
            },
        },
        "sources": [
            {
                "id": "one",
                "title": "Első",
                "retrieval_channel": "content",
                "portfolio_role": "anchor",
                "technique_tags": ["direct-address"],
                "utility_weight": utility,
                "evidence": [{"text": "Biztonságos saját evidence."}],
            },
            {
                "id": "two",
                "title": "Második",
                "retrieval_channel": "style",
                "portfolio_role": "range-sample",
                "technique_tags": ["question-driven"],
                "utility_weight": 0.0,
                "evidence": [{"text": "Másik evidence."}],
            },
        ],
        "contrastive_calibration": {
            "execution_set": [
                {
                    "id": "one",
                    "title": "Első",
                    "distance": 0.2,
                    "use": "Extract one transferable mechanism for this brief.",
                },
                {
                    "id": "two",
                    "title": "Második",
                    "distance": 0.1,
                    "use": "Extract one transferable mechanism for this brief.",
                },
            ],
            "contrast_set": [{"id": "three", "title": "Más tartomány", "distance": 0.8}],
        },
        "cross_genre_bridges": [],
    }


class BriefPlannerTests(unittest.TestCase):
    def test_explicit_fields_win_and_negative_preferences_are_preserved(self):
        plan = engine.plan_brief(
            "Írj verset. Ne legyen tele technológiai klisékkel.",
            genre="slam",
            audience="szakmai közönség",
        )

        self.assertEqual(plan["genre"], {"value": "slam", "origin": "explicit"})
        self.assertEqual(plan["audience"]["value"], "szakmai közönség")
        self.assertEqual(plan["negative_preferences"], ["Ne legyen tele technológiai klisékkel."])

    def test_genre_and_dialogue_need_can_be_inferred(self):
        plan = engine.plan_brief("Írj egy slamet, amely egy ellenvetésre válaszol.")

        self.assertEqual(plan["genre"]["value"], "slam")
        self.assertTrue(plan["dialogue_need"]["value"])


class EnginePacketTests(unittest.TestCase):
    def test_conditional_dialogue_is_only_active_for_dialogue_brief(self):
        quiet = engine.plan_brief("Írj slamet a hajnalról.")
        active = engine.plan_brief("Írj slamet, amely egy kérdésre válaszol.")

        self.assertFalse(engine.compile_engine_packet(portfolio(), quiet)["channels"]["dialogue"]["active"])
        self.assertTrue(engine.compile_engine_packet(portfolio(), active)["channels"]["dialogue"]["active"])

    def test_dialogue_only_genre_does_not_leak_into_plain_poetry(self):
        plan = engine.plan_brief("Írj verset a hajnalról.")
        packet = engine.compile_engine_packet(portfolio("dialogue-only"), plan)

        self.assertFalse(packet["channels"]["dialogue"]["active"])
        self.assertFalse(packet["source_trace"]["raw_slack_included"])

    def test_negative_channel_combines_contrast_guards_and_brief_constraints(self):
        plan = engine.plan_brief("Írj slamet. Kerüld a közhelyeket.", dialogue_mode="required")
        packet = engine.compile_engine_packet(portfolio(), plan)
        negative = packet["channels"]["negative_examples"]

        self.assertEqual(negative["contrast_sources"][0]["id"], "three")
        self.assertIn("Kerüld a közhelyeket.", negative["guards"])
        self.assertIn("Ne másold az elütéseket.", negative["guards"])

    def test_reranker_reports_cold_start_without_learned_utility(self):
        plan = engine.plan_brief("Írj slamet.")
        packet = engine.compile_engine_packet(portfolio(), plan)

        self.assertEqual(packet["preference_reranker"]["state"], "cold-start")
        self.assertEqual(packet["preference_reranker"]["ranked"][0]["id"], "two")

    def test_positive_utility_can_break_a_close_fit_without_erasing_trace(self):
        plan = engine.plan_brief("Írj slamet.")
        packet = engine.compile_engine_packet(portfolio(utility=0.75), plan)
        ranked = packet["preference_reranker"]["ranked"]

        self.assertEqual(packet["preference_reranker"]["state"], "observed")
        self.assertEqual(ranked[0]["id"], "one")
        self.assertEqual({item["id"] for item in ranked}, {"one", "two"})

    def test_execution_evidence_preserves_the_transfer_contract(self):
        plan = engine.plan_brief("Írj slamet.")
        packet = engine.compile_engine_packet(portfolio(), plan)
        evidence = next(
            item
            for item in packet["evidence_compiler"]["execution_evidence"]
            if item["id"] == "one"
        )

        self.assertEqual(evidence["mechanism"], "direct-address")
        self.assertEqual(evidence.get("technique_tags"), ["direct-address"])
        self.assertEqual(
            evidence["transfer_instruction"],
            "Extract one transferable mechanism for this brief.",
        )

    def test_packet_keeps_four_channels_and_no_raw_slack_payload(self):
        plan = engine.plan_brief("Írj válasz emailt.")
        packet = engine.compile_engine_packet(portfolio("strong"), plan)

        self.assertEqual(
            set(packet["channels"]),
            {"content", "style_mechanics", "dialogue", "negative_examples"},
        )
        rendered = str(packet).casefold()
        self.assertNotIn("slack_message", rendered)
        self.assertNotIn("channel_id", rendered)


if __name__ == "__main__":
    unittest.main()
