import importlib.util
import http.client
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from collections import Counter
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "human_blind_test.py"
PREPARER_PATH = SCRIPTS / "prepare_human_blind_test.py"
SERVER_PATH = SCRIPTS / "human_blind_test_server.py"
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

    def make_run(self):
        public, private, manifest = human_blind.build_pack(
            self.result, self.jobs, self.drafts, self.blind_key, seed=20260818
        )
        return human_blind.BlindTestRun(
            public, private, manifest,
            self.drafts / "human-test-progress.json",
            self.drafts / "human-test-result.json",
        )

    def make_smaller_run(self):
        public, private, _manifest = human_blind.build_pack(
            self.result, self.jobs, self.drafts, self.blind_key, seed=20260818
        )
        item = public["items"][0]
        smaller_public = {"schema_version": 1, "items": [item]}
        smaller_private = {"schema_version": 1, "items": {item["item_id"]: private["items"][item["item_id"]]}}
        smaller_manifest = {
            "schema_version": 1,
            "item_count": 1,
            "public_sha256": human_blind.canonical_sha256(smaller_public),
            "private_sha256": human_blind.canonical_sha256(smaller_private),
        }
        return human_blind.BlindTestRun(
            smaller_public, smaller_private, smaller_manifest,
            self.drafts / "small-progress.json",
            self.drafts / "small-result.json",
        )

    def answer_remaining(self, run):
        for item in run.snapshot()["items"]:
            if item["item_id"] != "item-01":
                run.save_answer(item["item_id"], "right", "legalább tíz karakter")

    def answer_all(self, run):
        for item in run.snapshot()["items"]:
            run.save_answer(item["item_id"], "left", "legalább tíz karakter")

    def test_answer_requires_known_item_choice_and_reason(self):
        run = self.make_run()
        with self.assertRaisesRegex(ValueError, "reason"):
            run.save_answer("item-01", "left", "rövid")
        with self.assertRaisesRegex(ValueError, "choice"):
            run.save_answer("item-01", "engine_v3", "legalább tíz karakter")

    def test_candidate_notes_are_bounded_and_unblinded_to_the_correct_system(self):
        run = self.make_run()
        with self.assertRaisesRegex(ValueError, "500"):
            run.save_answer("item-01", "left", "legalább tíz karakter",
                            left_highlight="x" * 501)
        run.save_answer("item-01", "left", "legalább tíz karakter",
                        left_highlight="ez a sor tetszett",
                        left_note="feszes és természetes",
                        right_note="jó kép, de modoros")
        self.answer_remaining(run)
        item = run.finalize()["items"][0]
        self.assertEqual(item["candidate_feedback"]["engine_v3"]["highlight"],
                         "ez a sor tetszett")

    def test_finalize_is_blocked_until_complete_then_becomes_immutable(self):
        run = self.make_run()
        with self.assertRaisesRegex(RuntimeError, "30"):
            run.finalize()
        self.answer_all(run)
        result = run.finalize()
        self.assertEqual(sum(result["overall"].values()), 30)
        self.assertFalse(result["utility_written"])
        self.assertFalse(result["learned_preference_claimed"])
        self.assertTrue(result["feedback_review_required"])
        self.assertNotIn("left_text", json.dumps(result, ensure_ascii=False))
        self.assertTrue(all("draft_hashes" in item for item in result["items"]))
        with self.assertRaisesRegex(RuntimeError, "finalized"):
            run.save_answer("item-01", "right", "utólag már nem írható át")

    def test_tie_finalization_keeps_both_systems_without_winner(self):
        run = self.make_run()
        run.save_answer("item-01", "tie", "legalább tíz karakter")
        self.answer_remaining(run)
        result = run.finalize()
        item = next(item for item in result["items"] if item["item_id"] == "item-01")
        self.assertIsNone(item["chosen_system"])
        self.assertEqual(result["overall"]["tie"], 1)
        self.assertEqual(result["overall"]["legacy"] + result["overall"]["engine_v3"], 29)
        self.assertEqual(result["by_genre"][item["genre"]]["tie"], 1)

    def test_candidate_and_general_notes_allow_1500_and_reject_1501_characters(self):
        maximum_note = "x" * 1500
        run = self.make_run()
        snapshot = run.save_answer(
            "item-01", "left", "legalább tíz karakter",
            left_note=maximum_note, right_note=maximum_note, general_note=maximum_note,
        )
        answer = next(item["answer"] for item in snapshot["items"] if item["item_id"] == "item-01")
        self.assertEqual(answer["left_note"], maximum_note)
        self.assertEqual(answer["right_note"], maximum_note)
        self.assertEqual(answer["general_note"], maximum_note)
        for field in ("left_note", "right_note", "general_note"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "1500"):
                    self.make_run().save_answer(
                        "item-01", "left", "legalább tíz karakter", **{field: "x" * 1501}
                    )

    def test_finalize_requires_30_answers_for_a_complete_smaller_pack(self):
        run = self.make_smaller_run()
        run.save_answer("item-01", "left", "legalább tíz karakter")
        with self.assertRaisesRegex(RuntimeError, "30"):
            run.finalize()

    def test_loopback_api_persists_answers_and_returns_http_contracts(self):
        server_spec = importlib.util.spec_from_file_location("human_blind_test_server", SERVER_PATH)
        server_module = importlib.util.module_from_spec(server_spec)
        assert server_spec.loader is not None
        server_spec.loader.exec_module(server_module)
        httpd = server_module.ThreadingHTTPServer(
            ("127.0.0.1", 0), server_module.make_handler(self.make_run())
        )
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            connection.request("GET", "/api/test")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            public = json.loads(response.read().decode("utf-8"))
            self.assertEqual(public["answered_count"], 0)
            self.assertNotIn("engine_v3", json.dumps(public, ensure_ascii=False))

            connection.request("GET", "/api/results")
            response = connection.getresponse()
            self.assertEqual(response.status, 409)
            response.read()

            payload = json.dumps({
                "item_id": "item-01", "choice": "left", "reason": "legalább tíz karakter"
            }, ensure_ascii=False).encode("utf-8")
            connection.request("POST", "/api/answer", payload, {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read().decode("utf-8"))["answered_count"], 1)

            connection.request("POST", "/api/finalize", b"{}", {"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 409)
            response.read()
            connection.request("GET", "/unknown")
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            connection.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=5)

    def test_server_rejects_non_loopback_host(self):
        completed = subprocess.run(
            [
                sys.executable, str(SERVER_PATH), "--public", "public.json", "--private", "private.json",
                "--manifest", "manifest.json", "--progress", "progress.json", "--result", "result.json",
                "--host", "0.0.0.0",
            ],
            capture_output=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("127.0.0.1", completed.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
