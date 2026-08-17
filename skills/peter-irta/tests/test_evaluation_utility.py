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


evaluation_packet = load_module("evaluation_packet")
retrieval_feedback = load_module("retrieval_feedback")


class EvaluationPacketTests(unittest.TestCase):
    def test_packet_has_four_dimensions_three_judges_and_reversed_order(self):
        packet = evaluation_packet.build_packet(
            brief="Írj rövid slamet az apáról és a technológiáról.",
            genre="slam",
            draft_a="A változat",
            draft_b="B változat",
            portfolio={"run_id": "run-1", "sources": [{"id": "source-1"}]},
        )

        self.assertEqual(
            set(packet["dimensions"]),
            {
                "brief_fidelity",
                "genre_naturalness",
                "author_style_match",
                "originality_anti_caricature",
            },
        )
        self.assertEqual(len(packet["judge_assignments"]), 6)
        orders = {tuple(item["candidate_order"]) for item in packet["judge_assignments"]}
        self.assertEqual(orders, {("A", "B"), ("B", "A")})
        self.assertEqual(
            {item["judge"] for item in packet["judge_assignments"]},
            {"brief-editor", "genre-practitioner", "authorship-skeptic"},
        )

    def test_packet_exposes_genre_guards_to_every_judge(self):
        packet = evaluation_packet.build_packet(
            brief="Írj énekelhető dalt kifinomult rímekkel.",
            genre="dalszoveg",
            draft_a="A változat",
            draft_b="B változat",
            portfolio={"run_id": "run-2", "sources": []},
        )

        guard_ids = {item["id"] for item in packet["genre_quality_contract"]["release_checks"]}
        self.assertIn("rhyme-prosody", guard_ids)
        self.assertTrue(all(assignment["genre_guard_ids"] == sorted(guard_ids) for assignment in packet["judge_assignments"]))


class RetrievalFeedbackTests(unittest.TestCase):
    def test_feedback_records_execution_source_roles_without_copying_text(self):
        portfolio = {
            "run_id": "run-1",
            "genre": "slam",
            "query": "sensitive brief text",
            "sources": [
                {"id": "one", "retrieval_channel": "content", "portfolio_role": "anchor"},
                {"id": "two", "retrieval_channel": "style", "portfolio_role": "range-sample"},
            ],
            "contrastive_calibration": {
                "execution_set": [{"id": "one"}, {"id": "two"}],
            },
        }

        entry = retrieval_feedback.build_entry(
            portfolio,
            utility=1.0,
            note="elfogadva",
            dimensions={"brief_fidelity": 2.0, "author_style_match": 1.5},
            recorded_at="2026-08-14T00:00:00+00:00",
        )

        self.assertEqual(entry["source_ids"], ["one", "two"])
        self.assertEqual(entry["source_uses"][1]["channel"], "style")
        self.assertEqual(entry["dimensions"]["author_style_match"], 1.5)
        self.assertNotIn("query", entry)
        self.assertNotIn("draft", entry)


if __name__ == "__main__":
    unittest.main()
