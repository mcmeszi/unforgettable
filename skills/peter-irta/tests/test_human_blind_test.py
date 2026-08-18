import importlib.util
import http.client
import json
import shutil
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
ASSET_ROOT = Path(__file__).resolve().parents[1] / "assets" / "human-blind-test"
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
            "seed": 20260818,
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

    def test_only_design_error_flags_are_accepted_and_survive_finalization(self):
        expected_flags = [
            "brief_mismatch",
            "genre_mismatch",
            "false_peter_voice",
            "mannerism_caricature",
            "hard_guard_problem",
        ]
        run = self.make_run()
        snapshot = run.save_answer(
            "item-01", "left", "legalább tíz karakter", flags=expected_flags,
        )
        answer = next(item["answer"] for item in snapshot["items"] if item["item_id"] == "item-01")
        self.assertEqual(answer["flags"], expected_flags)

        for unsupported in ("tie", "both_weak", "both_strong", "brief_problem", "unclear", "other"):
            with self.subTest(unsupported=unsupported):
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    self.make_run().save_answer(
                        "item-01", "left", "legalább tíz karakter", flags=[unsupported],
                    )

        self.answer_remaining(run)
        result_item = run.finalize()["items"][0]
        self.assertEqual(result_item["flags"], expected_flags)

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

    def test_final_result_has_manifest_seed_and_stable_output_bound_run_id(self):
        run = self.make_run()
        self.answer_all(run)
        result = run.finalize()
        self.assertEqual(result["seed"], 20260818)
        self.assertRegex(result["run_id"], r"^hbt-[0-9a-f]{24}$")
        self.assertNotIn(str(self.drafts), result["run_id"])
        self.assertEqual(self.make_run().finalized_result()["run_id"], result["run_id"])

        public, private, manifest = human_blind.build_pack(
            self.result, self.jobs, self.drafts, self.blind_key, seed=20260818
        )
        other = human_blind.BlindTestRun(
            public, private, manifest,
            self.drafts / "other-progress.json",
            self.drafts / "other-result.json",
        )
        self.answer_all(other)
        self.assertNotEqual(other.finalize()["run_id"], result["run_id"])

    def test_run_rejects_manifest_without_seed(self):
        public, private, manifest = human_blind.build_pack(
            self.result, self.jobs, self.drafts, self.blind_key, seed=20260818
        )
        manifest.pop("seed")
        with self.assertRaisesRegex(ValueError, "seed"):
            human_blind.BlindTestRun(
                public, private, manifest,
                self.drafts / "missing-seed-progress.json",
                self.drafts / "missing-seed-result.json",
            )

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

    def test_frontend_assets_and_required_copy_exist(self):
        html = (ASSET_ROOT / "index.html").read_text(encoding="utf-8")
        styles = (ASSET_ROOT / "app.css").read_text(encoding="utf-8")
        script = (ASSET_ROOT / "app.js").read_text(encoding="utf-8")
        for required in (
            'id="left-candidate"', 'id="right-candidate"',
            'id="left-highlight"', 'id="left-note"',
            'id="right-highlight"', 'id="right-note"',
            'id="general-note"', 'id="reason"',
            'value="left"', 'value="right"', 'value="tie"',
            "Véglegesítés",
            'value="brief_mismatch"', 'Brief-tévesztés',
            'value="genre_mismatch"', 'Műfajidegenség',
            'value="false_peter_voice"', 'Hamis Péter-hang',
            'value="mannerism_caricature"', 'Modorosság / karikatúra',
            'value="hard_guard_problem"', 'Hard-guard probléma',
        ):
            with self.subTest(required=required):
                self.assertIn(required, html)
        for focus_target in (
            "loading-title", "error-title", "start-title",
            "compare-title", "review-title", "results-title",
        ):
            with self.subTest(focus_target=focus_target):
                self.assertIn(f'id="{focus_target}" tabindex="-1"', html)
        for endpoint in ("/api/test", "/api/progress", "/api/answer", "/api/finalize", "/api/results"):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, script)
        for design_contract in (
            "#F7F4EE", "#24211D", "#7A2E34",
            "@media (max-width: 759px)", "prefers-reduced-motion",
            ".step-navigation { position: static;",
        ):
            with self.subTest(design_contract=design_contract):
                self.assertIn(design_contract, styles)

    def test_programmatic_view_heading_focus_rule_is_scoped_to_headings(self):
        styles = (ASSET_ROOT / "app.css").read_text(encoding="utf-8")
        self.assertIn('h1[tabindex="-1"]:focus { outline: none; }', styles)
        self.assertNotIn('\n[tabindex="-1"]:focus { outline: none; }', styles)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for frontend behavior validation")
    def test_frontend_state_validation_and_answer_payload_contract(self):
        node_program = r"""
const app = require(process.argv[1]);
const result = {
  states: [
    app.deriveState({started: false, finalized: false, answeredCount: 0, itemCount: 30}),
    app.deriveState({started: true, finalized: false, answeredCount: 4, itemCount: 30}),
    app.deriveState({started: true, finalized: false, answeredCount: 30, itemCount: 30}),
    app.deriveState({started: true, finalized: true, answeredCount: 30, itemCount: 30})
  ],
  invalidMissingChoice: app.validateAnswer({choice: "", reason: "legalább tíz karakter"}),
  invalidShortReason: app.validateAnswer({choice: "left", reason: " rövid "}),
  validTie: app.validateAnswer({choice: "tie", reason: "  legalább tíz karakter  "}),
  navigation: [
    app.navigationAvailability({currentIndex: 0, busy: false}),
    app.navigationAvailability({currentIndex: 1, busy: false}),
    app.navigationAvailability({currentIndex: 1, busy: true})
  ],
  scrollBehavior: [app.scrollBehavior(false), app.scrollBehavior(true)],
  focusTargets: ["loading", "error", "start", "compare", "review", "finalized", "unknown"]
    .map((view) => app.focusTargetForState(view)),
  payload: app.buildAnswerPayload("item-07", {
    choice: "right", reason: "  legalább tíz karakter  ",
    flags: ["brief_mismatch", "hard_guard_problem"],
    leftHighlight: " bal idézet ", leftNote: " bal jegyzet ",
    rightHighlight: " jobb idézet ", rightNote: " jobb jegyzet ",
    generalNote: " általános "
  })
};
process.stdout.write(JSON.stringify(result));
"""
        completed = subprocess.run(
            [shutil.which("node"), "-e", node_program, str(ASSET_ROOT / "app.js")],
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode(errors="replace"))
        result = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(result["states"], ["start", "compare", "review", "finalized"])
        self.assertFalse(result["invalidMissingChoice"]["valid"])
        self.assertFalse(result["invalidShortReason"]["valid"])
        self.assertTrue(result["validTie"]["valid"])
        self.assertEqual(result["navigation"], [
            {"backEnabled": False}, {"backEnabled": True}, {"backEnabled": False},
        ])
        self.assertEqual(result["scrollBehavior"], ["smooth", "auto"])
        self.assertEqual(result["focusTargets"], [
            "loading-title", "error-title", "start-title", "compare-title",
            "review-title", "results-title", "main-content",
        ])
        self.assertEqual(result["payload"], {
            "item_id": "item-07", "choice": "right", "reason": "legalább tíz karakter",
            "flags": ["brief_mismatch", "hard_guard_problem"],
            "left_highlight": "bal idézet", "left_note": "bal jegyzet",
            "right_highlight": "jobb idézet", "right_note": "jobb jegyzet",
            "general_note": "általános",
        })

    def test_loopback_server_serves_only_the_frontend_asset_contract(self):
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
            expected = {
                "/": ("text/html", "EMBERI VAKTESZT"),
                "/app.css": ("text/css", "--paper"),
                "/app.js": ("text/javascript", "/api/answer"),
            }
            for path, (content_type, marker) in expected.items():
                with self.subTest(path=path):
                    connection.request("GET", path)
                    response = connection.getresponse()
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn(content_type, response.getheader("Content-Type"))
                    self.assertIn(marker, body)
            connection.request("GET", "/favicon.ico")
            response = connection.getresponse()
            self.assertEqual(response.status, 204)
            response.read()
            connection.request("GET", "/../human_blind_test.py")
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
