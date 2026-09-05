import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("run_engine_v3_benchmark", SCRIPTS / "run_engine_v3_benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)


class EngineV3BenchmarkTests(unittest.TestCase):
    def test_blind_labels_are_deterministic_and_balanced(self):
        briefs = [{"id": f"brief-{index}"} for index in range(6)]
        first = benchmark.balanced_blind_labels(briefs)
        second = benchmark.balanced_blind_labels(list(reversed(briefs)))
        self.assertEqual(first, second)
        self.assertEqual(sum(order[0] == "legacy" for order in first.values()), 3)
        self.assertEqual(sum(order[0] == "engine_v3" for order in first.values()), 3)

    def test_engine_portfolio_uses_only_execution_sources_in_ranked_order(self):
        packet = {
            "schema": 3,
            "packet_id": "packet-1",
            "retrieval_run_id": "run-1",
            "brief_plan": {"genre": {"value": "slam"}},
            "retrieval": {"confidence": {"level": "high"}},
            "channels": {
                "content": [{"id": "one", "title": "One", "retrieval_channel": "content"}],
                "style_mechanics": [{"id": "two", "title": "Two", "retrieval_channel": "style"}],
                "negative_examples": {"contrast_sources": [{"id": "three"}]},
            },
            "preference_reranker": {"state": "cold-start"},
            "evidence_compiler": {
                "execution_evidence": [
                    {"id": "two", "preference_score": 0.9},
                    {"id": "one", "preference_score": 0.8},
                ]
            },
        }
        result = benchmark.engine_portfolio(packet)
        self.assertEqual([source["id"] for source in result["sources"]], ["two", "one"])
        self.assertEqual(result["engine_metadata"]["reranker_state"], "cold-start")
        self.assertFalse(result["engine_metadata"]["learned_preference_claimed"])
        self.assertEqual(result["contrastive_calibration"]["contrast_set"], [{"id": "three"}])


if __name__ == "__main__":
    unittest.main()
