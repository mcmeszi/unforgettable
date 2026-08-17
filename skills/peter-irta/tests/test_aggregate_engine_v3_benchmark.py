import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "aggregate_engine_v3_benchmark.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aggregate_engine_v3_benchmark", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AggregateEngineV3BenchmarkTests(unittest.TestCase):
    def setUp(self):
        if not MODULE_PATH.exists():
            self.fail("aggregate_engine_v3_benchmark.py is not implemented")
        self.module = load_module()

    def judgment(self, job_id, winner, left=2.0, right=1.0, left_failures=None, right_failures=None):
        dimensions = {
            "brief_fidelity": left,
            "genre_naturalness": left,
            "author_style_match": left,
            "originality_anti_caricature": left,
        }
        other = {key: right for key in dimensions}
        return {
            "job_id": job_id,
            "scores": {"candidate_1": dimensions, "candidate_2": other},
            "winner": winner,
            "decisive_reason": "teszt",
            "hard_guard_failures": {
                "candidate_1": left_failures or [],
                "candidate_2": right_failures or [],
            },
        }

    def test_reversed_orders_resolve_to_same_system_and_majority_winner(self):
        jobs = []
        order_key = {"jobs": {}}
        judgments = {}
        judges = ("brief-editor", "genre-practitioner", "authorship-skeptic")
        for judge in judges:
            ab = f"slam-01--{judge}--AB"
            ba = f"slam-01--{judge}--BA"
            jobs.extend([{"job_id": ab, "brief_id": "slam-01", "genre": "slam"}, {"job_id": ba, "brief_id": "slam-01", "genre": "slam"}])
            order_key["jobs"][ab] = {"candidate_1": "A", "candidate_2": "B"}
            order_key["jobs"][ba] = {"candidate_1": "B", "candidate_2": "A"}
            judgments[ab] = self.judgment(ab, "candidate_1", left_failures=["spoken-orality"])
            judgments[ba] = self.judgment(ba, "candidate_2", left=1.0, right=2.0, right_failures=["spoken-orality"])
        blind_key = {"slam-01": {"A": "engine_v3", "B": "legacy"}}

        result = self.module.aggregate(jobs, judgments, order_key, blind_key)

        self.assertEqual(result["overall"]["brief_wins"]["engine_v3"], 1)
        self.assertEqual(result["overall"]["judge_votes"]["engine_v3"], 6)
        self.assertEqual(result["order_bias"]["stable_pairs"], 3)
        self.assertEqual(result["overall"]["hard_guard_failures"]["engine_v3"], 6)
        self.assertEqual(result["overall"]["dimension_medians"]["engine_v3"]["brief_fidelity"], 2.0)

    def test_validation_rejects_missing_and_unexpected_judgments(self):
        jobs = [{"job_id": "one"}, {"job_id": "two"}]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "one.json").write_text(json.dumps(self.judgment("one", "tie")), encoding="utf-8")
            (directory / "unexpected.json").write_text(json.dumps(self.judgment("unexpected", "tie")), encoding="utf-8")

            manifest = self.module.validate_and_manifest(jobs, directory)

        self.assertFalse(manifest["valid"])
        self.assertIn("two", manifest["missing_job_ids"])
        self.assertIn("unexpected", manifest["unexpected_job_ids"])


if __name__ == "__main__":
    unittest.main()
