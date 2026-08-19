import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


def policy(state="manual_policy_cold_start"):
    return {
        "schema": "mind-vault-evidence-policy/v1",
        "policy_version": "test-policy-v1",
        "state": state,
        "authority_weights": {
            "voice": 1.0,
            "genre_mechanism": 0.7,
            "generation_guard": 0.7,
            "evaluation_only": 0.0,
            "utility_only": 0.0,
        },
        "confidence_weights": {"low": 0.1, "medium": 0.2, "high": 0.3},
        "selection_limits": {"voice": 5, "mechanisms": 3, "soft_guards": 3},
        "genre_exact_bonus": 0.5,
        "genre_global_bonus": 0.1,
        "scope_brief_match_bonus": 0.4,
        "allowed_scopes": ["spoken_delivery", "output_surface_markdown"],
    }


def observation():
    return {
        "schema": "mind-vault-evidence/v1",
        "evidence_id": "ev-" + "f" * 24,
        "evidence_type": "evaluation_observation",
        "status": "pending_review",
        "authority": "evaluation_only",
        "genre": ["slam"],
        "scope": [],
        "content": {"observation": "PRIVATE HUMAN OBSERVATION"},
        "provenance": {
            "source_kind": "human_blind_evaluation",
            "source_run_id": "test-run",
            "source_item_id": "test-item",
            "brief_id": "test-brief",
            "source_sha256": "a" * 64,
            "parent_evidence_ids": [],
        },
        "confidence": {"level": "high", "basis": "test fixture"},
        "created_at": "2026-08-19T08:00:00Z",
        "supersedes": [],
    }


def active_derived(kind, number, directive, *, genre="slam", scope="spoken_delivery",
                   level="soft", polarity="prefer"):
    return {
        "schema": "mind-vault-evidence/v1",
        "evidence_id": f"ev-{number:024x}",
        "evidence_type": kind,
        "status": "active",
        "authority": "generation_guard" if kind == "guard" else "genre_mechanism",
        "genre": [genre],
        "scope": [scope],
        "content": {
            "directive": directive,
            "level": level,
            "polarity": polarity,
            "observation": "PRIVATE HUMAN OBSERVATION",
        },
        "provenance": {
            "source_kind": "curated_evaluation_derivative",
            "source_run_id": "test-run",
            "source_item_id": f"derived-{number}",
            "brief_id": "test-brief",
            "source_sha256": f"{number:064x}",
            "parent_evidence_ids": [observation()["evidence_id"]],
        },
        "confidence": {"level": "high", "basis": "test fixture"},
        "created_at": "2026-08-19T08:01:00Z",
        "supersedes": [],
    }


def decision(evidence_id, status):
    return {
        "schema": "mind-vault-evidence-decision/v1",
        "evidence_id": evidence_id,
        "status": status,
        "reason": "test decision",
        "curator": "peter",
        "decided_at": "2026-08-19T09:00:00Z",
    }


def plan(brief="Írj slamet spoken deliveryre.", genre="slam"):
    return engine.plan_brief(brief, genre=genre)


def cli_args(root, *, no_derived_evidence=False):
    return argparse.Namespace(
        brief="Írj slamet.", genre="slam", purpose="", audience="", query="",
        dialogue="auto", target_axis=[], variation_seed="", limit=0, rag_root=None,
        vault_query=engine.VAULT_QUERY, output=root / "packet.json",
        evidence_ledger=root / "evidence.jsonl",
        decision_ledger=root / "decisions.jsonl",
        evidence_policy=root / "policy.json",
        no_derived_evidence=no_derived_evidence,
    )


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
    def test_packet_v2_exposes_selected_evidence_and_manual_cold_start(self):
        guard = active_derived("guard", 1, "Tartsd kimondhatónak.", level="hard")

        packet = engine.compile_engine_packet(
            portfolio(),
            plan(),
            evidence_records=[observation(), guard],
            evidence_decisions=[],
            evidence_policy=policy(),
        )

        self.assertEqual(packet["schema"], "mind-vault-engine-packet/v2")
        self.assertEqual(packet["evidence_policy"]["state"], "manual_policy_cold_start")
        self.assertEqual(packet["selected_evidence"]["guards"][0]["scope"], ["spoken_delivery"])
        self.assertEqual(packet["preference_reranker"]["state"], "cold-start")

    def test_selected_mechanism_and_guard_transfer_only_sanitized_directives(self):
        mechanism = active_derived("mechanism", 2, "Építs visszatérő színpadi motívumot.")
        guard = active_derived("guard", 3, "Kerüld a felolvashatatlan mondatokat.", level="hard")

        packet = engine.compile_engine_packet(
            portfolio(),
            plan(),
            evidence_records=[observation(), mechanism, guard],
            evidence_decisions=[],
            evidence_policy=policy(),
        )

        transferred = packet["evidence_compiler"]["execution_evidence"][-1]
        self.assertEqual(transferred["id"], mechanism["evidence_id"])
        self.assertEqual(transferred["transfer_instruction"], mechanism["content"]["directive"])
        self.assertEqual(transferred["evidence"], [])
        self.assertTrue(transferred["derived"])
        self.assertNotIn("utility_weight", transferred)
        self.assertNotIn("preference_score", transferred)
        self.assertEqual(
            packet["channels"]["negative_examples"]["guards"][-1],
            guard["content"]["directive"],
        )
        self.assertNotIn("PRIVATE HUMAN OBSERVATION", json.dumps(packet, ensure_ascii=False))

    def test_non_matching_genre_derived_evidence_stays_out_of_slam_packet(self):
        article = active_derived("mechanism", 4, "Használj cikkes alcímeket.", genre="cikk")

        packet = engine.compile_engine_packet(
            portfolio(),
            plan(),
            evidence_records=[observation(), article],
            evidence_decisions=[],
            evidence_policy=policy(),
        )

        self.assertEqual(packet["selected_evidence"]["mechanisms"], [])
        self.assertNotIn(article["evidence_id"], [item["id"] for item in packet["evidence_compiler"]["execution_evidence"]])

    def test_guard_conflicts_are_copied_and_not_transferred(self):
        required = active_derived(
            "guard", 5, "Használj Markdown alcímeket.", genre="cikk",
            scope="output_surface_markdown", polarity="require",
        )
        forbidden = active_derived(
            "guard", 6, "Ne használj Markdown alcímeket.", genre="cikk",
            scope="output_surface_markdown", polarity="forbid",
        )

        packet = engine.compile_engine_packet(
            portfolio(),
            plan("Írj cikket markdown outputtal.", genre="cikk"),
            evidence_records=[observation(), required, forbidden],
            evidence_decisions=[],
            evidence_policy=policy(),
        )

        self.assertEqual(packet["selected_evidence"]["guards"], [])
        self.assertEqual(
            packet["conflicts"][0]["evidence_ids"],
            sorted([required["evidence_id"], forbidden["evidence_id"]]),
        )
        guards = packet["channels"]["negative_examples"]["guards"]
        self.assertNotIn(required["content"]["directive"], guards)
        self.assertNotIn(forbidden["content"]["directive"], guards)

    def test_missing_derived_state_preserves_legacy_selection(self):
        packet = engine.compile_engine_packet(portfolio(), plan())

        self.assertEqual(
            [item["id"] for item in packet["evidence_compiler"]["execution_evidence"]],
            [item["id"] for item in packet["preference_reranker"]["ranked"]],
        )
        self.assertEqual(packet["selected_evidence"]["mechanisms"], [])
        self.assertEqual(packet["evidence_policy"]["state"], "state_absent")

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


class EngineCliTests(unittest.TestCase):
    def test_malformed_explicit_ledgers_report_file_and_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            cases = (
                ("evidence.jsonl", "decisions.jsonl"),
                ("decisions.jsonl", "evidence.jsonl"),
            )
            for malformed_name, valid_name in cases:
                with self.subTest(ledger=malformed_name):
                    (root / malformed_name).write_text("{}\n{broken", encoding="utf-8")
                    (root / valid_name).write_text("", encoding="utf-8")
                    args = cli_args(root)
                    with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                        engine, "run_vault_query", return_value=portfolio()
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            engine.main()
                    message = str(raised.exception)
                    self.assertIn(str(root / malformed_name), message)
                    self.assertIn("line 2", message)

    def test_structurally_invalid_evidence_row_reports_exact_file_and_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            (root / "evidence.jsonl").write_text("\n{}\n", encoding="utf-8")
            (root / "decisions.jsonl").write_text("", encoding="utf-8")
            args = cli_args(root)

            with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                engine, "run_vault_query", return_value=portfolio()
            ):
                with self.assertRaises(SystemExit) as raised:
                    engine.main()

            message = str(raised.exception)
            self.assertIn(str(args.evidence_ledger), message)
            self.assertIn("line 2", message)

    def test_structurally_invalid_decision_row_reports_exact_file_and_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            (root / "evidence.jsonl").write_text(
                json.dumps(observation(), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (root / "decisions.jsonl").write_text("\n\n{}\n", encoding="utf-8")
            args = cli_args(root)

            with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                engine, "run_vault_query", return_value=portfolio()
            ):
                with self.assertRaises(SystemExit) as raised:
                    engine.main()

            message = str(raised.exception)
            self.assertIn(str(args.decision_ledger), message)
            self.assertIn("line 3", message)

    def test_invalid_existing_evidence_is_rejected_when_decision_ledger_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            (root / "evidence.jsonl").write_text("{}\n", encoding="utf-8")
            args = cli_args(root)

            with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                engine, "run_vault_query", return_value=portfolio()
            ):
                with self.assertRaises(SystemExit) as raised:
                    engine.main()

            message = str(raised.exception)
            self.assertIn(str(args.evidence_ledger), message)
            self.assertIn("line 1", message)

    def test_invalid_existing_decision_is_rejected_when_evidence_ledger_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            (root / "decisions.jsonl").write_text("{}\n", encoding="utf-8")
            args = cli_args(root)

            with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                engine, "run_vault_query", return_value=portfolio()
            ):
                with self.assertRaises(SystemExit) as raised:
                    engine.main()

            message = str(raised.exception)
            self.assertIn(str(args.decision_ledger), message)
            self.assertIn("line 1", message)

    def test_valid_existing_ledger_with_missing_counterpart_emits_state_absent(self):
        cases = (
            ("evidence.jsonl", observation()),
            (
                "decisions.jsonl",
                decision("ev-" + "d" * 24, "active"),
            ),
        )
        for ledger_name, item in cases:
            with self.subTest(existing=ledger_name), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
                (root / ledger_name).write_text(json.dumps(item) + "\n", encoding="utf-8")
                args = cli_args(root)

                with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                    engine, "run_vault_query", return_value=portfolio()
                ), mock.patch("builtins.print"):
                    self.assertEqual(engine.main(), 0)

                packet = json.loads(args.output.read_text(encoding="utf-8"))
                self.assertEqual(packet["evidence_policy"]["state"], "state_absent")
                self.assertEqual(packet["selected_evidence"]["mechanisms"], [])
                self.assertEqual(packet["selected_evidence"]["guards"], [])

    def test_static_evidence_reference_errors_precede_missing_decision_fallback(self):
        missing_parent = active_derived("mechanism", 10, "Hiányzó szülő.")
        wrong_type_parent = observation()
        wrong_type_parent["evidence_id"] = "ev-" + "c" * 24
        wrong_type_parent["evidence_type"] = "utility_observation"
        wrong_type_parent["authority"] = "utility_only"
        wrong_type_child = active_derived("mechanism", 11, "Rossz típusú szülő.")
        wrong_type_child["provenance"]["parent_evidence_ids"] = [wrong_type_parent["evidence_id"]]
        missing_superseded = active_derived("mechanism", 12, "Hiányzó előd.")
        missing_superseded["supersedes"] = ["ev-" + "b" * 24]
        cases = (
            ("missing-parent", [missing_parent], 1),
            ("wrong-type-parent", [wrong_type_parent, wrong_type_child], 2),
            ("missing-superseded", [observation(), missing_superseded], 2),
        )

        for name, records, expected_line in cases:
            with self.subTest(error=name), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
                (root / "evidence.jsonl").write_text(
                    "\n".join(json.dumps(item) for item in records) + "\n",
                    encoding="utf-8",
                )
                args = cli_args(root)

                with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                    engine, "run_vault_query", return_value=portfolio()
                ):
                    with self.assertRaises(SystemExit) as raised:
                        engine.main()

                message = str(raised.exception)
                self.assertIn(str(args.evidence_ledger), message)
                self.assertIn(f"line {expected_line}", message)

    def test_supersedes_active_status_is_checked_after_decisions(self):
        parent = observation()
        target = active_derived("mechanism", 13, "Korábbi mechanizmus.")
        replacement = active_derived("mechanism", 14, "Új mechanizmus.")
        target["status"] = "pending_review"
        replacement["status"] = "pending_review"
        replacement["supersedes"] = [target["evidence_id"]]
        target_decision = decision(target["evidence_id"], "active")
        replacement_decision = decision(replacement["evidence_id"], "active")
        replacement_decision["decided_at"] = "2026-08-19T10:00:00Z"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            (root / "evidence.jsonl").write_text(
                "\n".join(json.dumps(item) for item in (parent, target, replacement)) + "\n",
                encoding="utf-8",
            )
            (root / "decisions.jsonl").write_text(
                "\n".join(json.dumps(item) for item in (target_decision, replacement_decision)) + "\n",
                encoding="utf-8",
            )
            args = cli_args(root)

            with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                engine, "run_vault_query", return_value=portfolio()
            ), mock.patch("builtins.print"):
                self.assertEqual(engine.main(), 0)

            packet = json.loads(args.output.read_text(encoding="utf-8"))
            self.assertEqual(
                [item["evidence_id"] for item in packet["selected_evidence"]["mechanisms"]],
                [replacement["evidence_id"]],
            )

    def test_projection_errors_report_the_causal_ledger_row(self):
        base_observation = observation()
        conflicting_duplicate = observation()
        conflicting_duplicate["content"] = {"observation": "different"}
        missing_parent = active_derived("mechanism", 8, "Hiányzó szülő.")
        missing_superseded = active_derived("mechanism", 9, "Hiányzó előd.")
        missing_superseded["supersedes"] = ["ev-" + "e" * 24]
        cases = (
            (
                "duplicate",
                [base_observation, conflicting_duplicate],
                [],
                "evidence.jsonl",
                2,
            ),
            ("missing-parent", [missing_parent], [], "evidence.jsonl", 1),
            (
                "missing-superseded",
                [base_observation, missing_superseded],
                [],
                "evidence.jsonl",
                2,
            ),
            (
                "invalid-transition",
                [base_observation],
                [decision(base_observation["evidence_id"], "retired")],
                "decisions.jsonl",
                1,
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "policy.json").write_text(json.dumps(policy()), encoding="utf-8")
            for name, records, decisions, ledger_name, expected_line in cases:
                with self.subTest(error=name):
                    (root / "evidence.jsonl").write_text(
                        "\n".join(json.dumps(item) for item in records) + "\n",
                        encoding="utf-8",
                    )
                    (root / "decisions.jsonl").write_text(
                        "\n".join(json.dumps(item) for item in decisions) + ("\n" if decisions else ""),
                        encoding="utf-8",
                    )
                    args = cli_args(root)

                    with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                        engine, "run_vault_query", return_value=portfolio()
                    ):
                        with self.assertRaises(SystemExit) as raised:
                            engine.main()

                    message = str(raised.exception)
                    self.assertIn(str(root / ledger_name), message)
                    self.assertIn(f"line {expected_line}", message)

    def test_nested_policy_type_errors_report_path_and_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "evidence.jsonl").write_text("", encoding="utf-8")
            (root / "decisions.jsonl").write_text("", encoding="utf-8")
            cases = (
                ("selection_limits", [1, 2, 3], "selection_limits"),
                (
                    "authority_weights",
                    {**policy()["authority_weights"], "genre_mechanism": "heavy"},
                    "authority_weights.genre_mechanism",
                ),
            )
            for field, malformed, expected_field in cases:
                with self.subTest(field=field):
                    malformed_policy = policy()
                    malformed_policy[field] = malformed
                    (root / "policy.json").write_text(
                        json.dumps(malformed_policy),
                        encoding="utf-8",
                    )
                    args = cli_args(root)

                    with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                        engine, "run_vault_query", return_value=portfolio()
                    ), mock.patch("builtins.print"):
                        with self.assertRaises(SystemExit) as raised:
                            engine.main()

                    message = str(raised.exception)
                    self.assertIn(str(args.evidence_policy), message)
                    self.assertIn(expected_field, message)

    def test_no_derived_evidence_skips_files_and_emits_empty_disabled_layer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for filename in ("evidence.jsonl", "decisions.jsonl", "policy.json"):
                (root / filename).write_text("{broken", encoding="utf-8")
            args = cli_args(root, no_derived_evidence=True)
            with mock.patch.object(engine, "parse_args", return_value=args), mock.patch.object(
                engine, "run_vault_query", return_value=portfolio()
            ), mock.patch("builtins.print"):
                self.assertEqual(engine.main(), 0)

            packet = json.loads(args.output.read_text(encoding="utf-8"))
            self.assertEqual(packet["evidence_policy"]["state"], "disabled_explicitly")
            self.assertEqual(packet["selected_evidence"]["mechanisms"], [])
            self.assertEqual(packet["selected_evidence"]["guards"], [])


if __name__ == "__main__":
    unittest.main()
