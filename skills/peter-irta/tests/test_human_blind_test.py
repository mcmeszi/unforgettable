import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "human_blind_test.py"
PREPARER_PATH = SCRIPTS / "prepare_human_blind_test.py"
SPEC = importlib.util.spec_from_file_location("human_blind_test", MODULE_PATH)
human_blind = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(human_blind)


class HumanBlindTestTests(unittest.TestCase):
    def setUp(self):
        self.genres = [
            "slam", "vers", "dalszoveg", "proza", "cikk",
            "tanulmany", "prezentacio", "reklam", "beszed", "email",
        ]
        self.result = self.benchmark_result()
        self.jobs = [
            {"job_id": f"{brief_id}-{candidate}", "brief_id": brief_id, "candidate": candidate}
            for brief_id in self.genre_by_brief
            for candidate in ("A", "B")
        ]
        self.blind_key = {
            brief_id: {"A": "legacy", "B": "engine_v3"}
            for brief_id in self.genre_by_brief
        }
        self.temporary = tempfile.TemporaryDirectory()
        self.drafts = Path(self.temporary.name)
        for job in self.jobs:
            (self.drafts / f"{job['job_id']}.md").write_text(
                f"Draft for {job['job_id']}", encoding="utf-8"
            )

    def tearDown(self):
        self.temporary.cleanup()

    def benchmark_result(self):
        briefs = []
        self.genre_by_brief = {}
        for genre in self.genres:
            for number in range(1, 4):
                brief_id = f"{genre}-{number:02d}"
                self.genre_by_brief[brief_id] = genre
                briefs.append({"brief_id": brief_id, "genre": genre, "brief": f"{genre} brief {number}"})
        return {"generation_jobs": briefs}

    def test_selection_keeps_all_thirty_briefs_and_three_per_genre(self):
        selected = human_blind.benchmark_briefs(self.benchmark_result())
        self.assertEqual(len(selected), 30)
        self.assertEqual(len(set(selected)), 30)
        counts = Counter(self.genre_by_brief[item] for item in selected)
        self.assertEqual(set(counts), set(self.genres))
        self.assertTrue(all(count == 3 for count in counts.values()))

    def test_public_pack_is_balanced_and_contains_no_system_mapping(self):
        public, private, manifest = human_blind.build_pack(
            self.result, self.jobs, self.drafts, self.blind_key, seed=20260818
        )
        self.assertEqual(len(public["items"]), 30)
        self.assertEqual(sum(value["left"] == "engine_v3" for value in private["items"].values()), 15)
        serialized = json.dumps(public, ensure_ascii=False)
        for forbidden in ("legacy", "engine_v3", '"A"', '"B"', "source_id"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(manifest["public_sha256"], human_blind.canonical_sha256(public))

    def test_preparer_writes_three_deterministic_json_files(self):
        result_path = self.drafts / "results.json"
        jobs_path = self.drafts / "jobs.jsonl"
        blind_key_path = self.drafts / "blind-key.json"
        output_dir = self.drafts / "output"
        result_path.write_text(json.dumps(self.result), encoding="utf-8")
        jobs_path.write_text("\n".join(json.dumps(job) for job in self.jobs) + "\n", encoding="utf-8")
        blind_key_path.write_text(json.dumps(self.blind_key), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable, str(PREPARER_PATH), "--results", str(result_path), "--jobs", str(jobs_path),
                "--drafts-dir", str(self.drafts), "--blind-key", str(blind_key_path), "--seed", "20260818",
                "--output-dir", str(output_dir),
            ],
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        self.assertEqual(
            sorted(path.name for path in output_dir.iterdir()),
            ["human-test-manifest.json", "private-human-key.json", "public-test.json"],
        )

    def test_preparer_refuses_to_overwrite_a_nonempty_output_directory(self):
        result_path = self.drafts / "results.json"
        jobs_path = self.drafts / "jobs.jsonl"
        blind_key_path = self.drafts / "blind-key.json"
        output_dir = self.drafts / "occupied-output"
        output_dir.mkdir()
        (output_dir / "keep.txt").write_text("keep", encoding="utf-8")
        result_path.write_text(json.dumps(self.result), encoding="utf-8")
        jobs_path.write_text("\n".join(json.dumps(job) for job in self.jobs) + "\n", encoding="utf-8")
        blind_key_path.write_text(json.dumps(self.blind_key), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable, str(PREPARER_PATH), "--results", str(result_path), "--jobs", str(jobs_path),
                "--drafts-dir", str(self.drafts), "--blind-key", str(blind_key_path), "--seed", "20260818",
                "--output-dir", str(output_dir),
            ],
            capture_output=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("refusing non-empty output directory", completed.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
