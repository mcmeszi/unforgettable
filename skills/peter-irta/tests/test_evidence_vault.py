import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

MODULE_PATH = SCRIPTS / "evidence_vault.py"
SPEC = importlib.util.spec_from_file_location("evidence_vault", MODULE_PATH)
evidence_vault = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evidence_vault)

IMPORTER_PATH = SCRIPTS / "import_human_blind_feedback.py"
IMPORTER_SPEC = importlib.util.spec_from_file_location("import_human_blind_feedback", IMPORTER_PATH)
importer = importlib.util.module_from_spec(IMPORTER_SPEC)
assert IMPORTER_SPEC.loader is not None
IMPORTER_SPEC.loader.exec_module(importer)

CURATOR_PATH = SCRIPTS / "curate_evidence.py"
CURATOR_SPEC = importlib.util.spec_from_file_location("curate_evidence", CURATOR_PATH)
curator = importlib.util.module_from_spec(CURATOR_SPEC)
assert CURATOR_SPEC.loader is not None
CURATOR_SPEC.loader.exec_module(curator)


POLICY_PATH = Path(__file__).resolve().parents[1] / "references" / "evidence-policy.json"
SKILL_ROOT = Path(__file__).resolve().parents[1]
ENGINE_V3_DOC_PATH = SKILL_ROOT / "references" / "engine-v3.md"
SKILL_DOC_PATH = SKILL_ROOT / "SKILL.md"


def make_record(**overrides):
    base = {
        "schema": "mind-vault-evidence/v1",
        "evidence_id": "ev-" + "1" * 24,
        "evidence_type": "guard",
        "genre": ["slam"],
        "scope": ["spoken_delivery"],
        "status": "pending_review",
        "authority": "generation_guard",
        "content": {"directive": "A slam legyen kimondható."},
        "provenance": {
            "source_kind": "human_blind_test",
            "source_run_id": "hbt-abc",
            "source_item_id": "item-01",
            "brief_id": "slam-01",
            "source_sha256": "a" * 64,
            "parent_evidence_ids": ["ev-" + "2" * 24],
        },
        "confidence": {"level": "high", "basis": "explicit human feedback"},
        "created_at": "2026-08-19T12:00:00+00:00",
        "supersedes": [],
    }
    base.update(overrides)
    return base


def make_decision(evidence_id, status, **overrides):
    base = {
        "schema": "mind-vault-evidence-decision/v1",
        "evidence_id": evidence_id,
        "status": status,
        "reason": "Curation decision.",
        "curator": "peter",
        "decided_at": "2026-08-19T13:00:00+00:00",
    }
    base.update(overrides)
    return base


def make_human_result(item_count=2, **overrides):
    items = []
    for number in range(1, item_count + 1):
        items.append({
            "item_id": f"item-{number:02d}",
            "brief_id": f"slam-{number:02d}",
            "genre": "slam",
            "choice": "left",
            "chosen_system": "engine_v3",
            "reason": f"Reason {number} is explicit.",
            "flags": ["brief_mismatch"],
            "candidate_feedback": {
                "engine_v3": {"highlight": "Strong line", "note": "Natural."},
                "legacy": {"highlight": "", "note": "Stilted."},
            },
            "general_note": "Compare the two approaches.",
            "answered_at": "2026-08-19T10:00:00+00:00",
            "draft_hashes": {"left": "a" * 64, "right": "b" * 64},
            "left_text": "SECRET FULL DRAFT",
        })
    base = {
        "schema_version": 1,
        "run_id": "hbt-" + "a" * 24,
        "seed": 20260818,
        "public_sha256": "c" * 64,
        "private_sha256": "d" * 64,
        "finalized_at": "2026-08-19T11:00:00+00:00",
        "item_count": item_count,
        "overall": {"legacy": 0, "engine_v3": item_count, "tie": 0},
        "by_genre": {"slam": {"legacy": 0, "engine_v3": item_count, "tie": 0}},
        "items": items,
        "utility_written": False,
        "learned_preference_claimed": False,
        "feedback_review_required": True,
    }
    base.update(overrides)
    if "private_sha256" not in overrides:
        base["private_sha256"] = evidence_vault.canonical_sha256(make_private_key(item_count))
    return base


def make_private_key(item_count=2):
    return {
        "schema_version": 1,
        "items": {
            f"item-{number:02d}": {
                "brief_id": f"slam-{number:02d}",
                "left": "engine_v3",
                "right": "legacy",
                "left_candidate": "A",
                "right_candidate": "B",
            }
            for number in range(1, item_count + 1)
        },
    }


def write_ledgers(root: Path, records: list[dict], decisions: list[dict]) -> tuple[Path, Path]:
    evidence_path = root / "evidence.jsonl"
    decision_path = root / "decisions.jsonl"
    if records:
        evidence_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
    if decisions:
        decision_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in decisions),
            encoding="utf-8",
        )
    return evidence_path, decision_path


def wait_for_markers(markers: list[Path], processes: list[subprocess.Popen], timeout: float = 10.0) -> None:
    """Wait until synchronized child writers are ready without hiding early failures."""
    deadline = time.monotonic() + timeout
    while not all(marker.is_file() for marker in markers):
        failed = [process for process in processes if process.poll() is not None]
        if failed:
            stdout, stderr = failed[0].communicate()
            raise AssertionError(f"child writer exited before synchronization: {stdout}\n{stderr}")
        if time.monotonic() >= deadline:
            raise AssertionError("child writers did not reach the synchronization point")
        time.sleep(0.01)


def process_is_blocked(process: subprocess.Popen, timeout: float = 1.0) -> bool:
    """Return whether a synchronized child remains blocked for the bounded interval."""
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return True
    return False


def synchronized_cli_process(module_name: str, marker: Path, argv: list[str]) -> subprocess.Popen:
    """Start a real CLI entrypoint and signal immediately before its writer call."""
    child = (
        "import importlib,sys; from pathlib import Path; "
        "sys.path.insert(0, sys.argv[1]); "
        "module=importlib.import_module(sys.argv[3]); "
        "Path(sys.argv[2]).write_text('ready', encoding='utf-8'); "
        "raise SystemExit(module.main(sys.argv[4:]))"
    )
    return subprocess.Popen(
        [sys.executable, "-c", child, str(SCRIPTS), str(marker), module_name, *argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


class EvidenceIdentityTests(unittest.TestCase):
    def test_evidence_id_is_stable_across_key_order(self):
        left = {"source_run_id": "hbt-abc", "brief_id": "slam-01", "content_sha256": "a" * 64}
        right = {"content_sha256": "a" * 64, "brief_id": "slam-01", "source_run_id": "hbt-abc"}

        self.assertEqual(evidence_vault.derive_evidence_id(left), evidence_vault.derive_evidence_id(right))

    def test_canonical_hash_uses_compact_key_sorted_unicode_json(self):
        self.assertEqual(
            evidence_vault.canonical_sha256({"z": "ár", "a": [1, True]}),
            "a3177e3c49914ac1f3a282a81457a9ef35c902f5e477a633579ecb268097c0da",
        )


class RecordValidationTests(unittest.TestCase):
    def test_voice_source_accepts_provenance_backed_own_source(self):
        record = make_record(
            evidence_type="voice_source",
            authority="voice",
            provenance={
                "source_kind": "provenance_validated_own_source",
                "origin": "drive-original",
                "source_run_id": "rag-abc",
                "source_item_id": "doc-01",
                "brief_id": "source-doc-01",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
        )

        evidence_vault.validate_record(record)

    def test_historical_drive_original_voice_source_ledger_fixture_remains_compatible(self):
        historical_row = {
            "schema": "mind-vault-evidence/v1",
            "evidence_id": "ev-" + "a" * 24,
            "evidence_type": "voice_source",
            "genre": ["slam"],
            "scope": [],
            "status": "active",
            "authority": "voice",
            "content": {"source_id": "MNWrA8207MY", "title": "Fuss az életedért"},
            "provenance": {
                "source_kind": "provenance_validated_own_source",
                "origin": "drive-original",
                "source_run_id": "historical-vault-ledger",
                "source_item_id": "MNWrA8207MY",
                "brief_id": "performance-transcript",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
            "confidence": {"level": "high", "basis": "historical Drive-original provenance"},
            "created_at": "2026-08-07T23:39:37.979288+00:00",
            "supersedes": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "historical-evidence.jsonl"
            ledger.write_text(json.dumps(historical_row, ensure_ascii=False) + "\n", encoding="utf-8")

            loaded = evidence_vault.read_jsonl(ledger)

        self.assertEqual(loaded, [historical_row])
        evidence_vault.validate_record(loaded[0])

    def test_voice_source_rejects_generated_v1_draft_source_kind(self):
        record = make_record(
            evidence_type="voice_source",
            authority="voice",
            provenance={
                "source_kind": "generated_v1_draft",
                "origin": "drive-original",
                "source_run_id": "v1-run",
                "source_item_id": "draft-01",
                "brief_id": "slam-01",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
        )

        with self.assertRaisesRegex(ValueError, "voice_source provenance"):
            evidence_vault.validate_record(record)

    def test_voice_source_rejects_generated_engine_v3_draft_origin(self):
        record = make_record(
            evidence_type="voice_source",
            authority="voice",
            provenance={
                "source_kind": "provenance_validated_own_source",
                "origin": "engine_v3_draft",
                "source_run_id": "engine-run",
                "source_item_id": "draft-01",
                "brief_id": "slam-01",
                "source_sha256": "a" * 64,
                "parent_evidence_ids": [],
            },
        )

        with self.assertRaisesRegex(ValueError, "voice_source provenance"):
            evidence_vault.validate_record(record)

    def test_active_guard_requires_scope_and_parent(self):
        record = make_record(status="active", scope=[])
        record["provenance"]["parent_evidence_ids"] = []

        with self.assertRaisesRegex(ValueError, "scope"):
            evidence_vault.validate_record(record)

        record["scope"] = ["spoken_delivery"]
        with self.assertRaisesRegex(ValueError, "parent"):
            evidence_vault.validate_record(record)

    def test_record_rejects_unknown_type_and_status(self):
        with self.assertRaisesRegex(ValueError, "evidence_type"):
            evidence_vault.validate_record(make_record(evidence_type="speculation"))
        with self.assertRaisesRegex(ValueError, "status"):
            evidence_vault.validate_record(make_record(status="published"))

    def test_derived_guard_allows_missing_legacy_polarity(self):
        evidence_vault.validate_record(make_record(content={"directive": "Legacy directive."}))

    def test_derived_guard_rejects_invalid_explicit_polarity(self):
        with self.assertRaisesRegex(ValueError, "polarity"):
            evidence_vault.validate_record(make_record(content={"directive": "Directive.", "polarity": "must"}))


class ProjectionTests(unittest.TestCase):
    def test_projection_applies_pending_to_active_decision(self):
        record = make_record(evidence_type="guard", status="pending_review")
        parent = make_record(
            evidence_type="evaluation_observation",
            evidence_id="ev-" + "2" * 24,
            status="pending_review",
        )
        decision = make_decision(record["evidence_id"], "active")

        state = evidence_vault.project_state([parent, record], [decision])

        self.assertEqual(state[record["evidence_id"]]["status"], "active")

    def test_projection_rejects_decision_for_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, "missing evidence"):
            evidence_vault.project_state([], [make_decision("ev-" + "3" * 24, "active")])

    def test_projection_rejects_invalid_transition(self):
        record = make_record(evidence_type="evaluation_observation", status="rejected")

        with self.assertRaisesRegex(ValueError, "invalid transition"):
            evidence_vault.project_state([record], [make_decision(record["evidence_id"], "active")])

    def test_projection_rejects_same_id_with_different_content(self):
        original = make_record()
        conflicting = make_record(content={"directive": "Different instruction."})

        with self.assertRaisesRegex(ValueError, "duplicate evidence_id"):
            evidence_vault.project_state([original, conflicting], [])

    def test_projection_rejects_non_monotonic_decision_time(self):
        record = make_record()
        first = make_decision(record["evidence_id"], "active", decided_at="2026-08-19T14:00:00+00:00")
        second = make_decision(record["evidence_id"], "retired", decided_at="2026-08-19T13:00:00+00:00")

        with self.assertRaisesRegex(ValueError, "non-monotonic"):
            evidence_vault.project_state([record], [first, second])


class LedgerAndPolicyTests(unittest.TestCase):
    def test_read_jsonl_reports_path_and_line_for_malformed_row(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "evidence.jsonl"
            ledger.write_text('{"valid": true}\n{broken}\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, r"evidence\.jsonl.*line 2"):
                evidence_vault.read_jsonl(ledger)

    def test_policy_loads_versioned_static_configuration(self):
        policy = evidence_vault.load_policy(POLICY_PATH)

        self.assertEqual(policy["schema"], "mind-vault-evidence-policy/v1")
        self.assertEqual(policy["policy_version"], "2026-08-19.1")
        self.assertIn("spoken_delivery", policy["allowed_scopes"])


class CurationTests(unittest.TestCase):
    def test_create_active_guard_writes_pending_record_then_active_decision(self):
        observation = make_record(evidence_type="evaluation_observation", status="pending_review")
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(Path(directory), [observation], [])

            result = curator.create_derived(
                evidence_path=evidence_path,
                decision_path=decision_path,
                kind="guard",
                genres=["slam"],
                scopes=["spoken_delivery"],
                directive="A slam egyszeri hallásra követhető, kimondható előadói ívet tartson.",
                guard_level="hard",
                confidence="high",
                basis="Explicit human feedback from slam-03.",
                parent_ids=[observation["evidence_id"]],
                activate=True,
            )

            state = evidence_vault.project_state(
                evidence_vault.read_jsonl(evidence_path), evidence_vault.read_jsonl(decision_path)
            )
            self.assertEqual(state[result["evidence_id"]]["status"], "active")
            self.assertEqual(len(evidence_vault.read_jsonl(evidence_path)), 2)
            self.assertEqual(len(evidence_vault.read_jsonl(decision_path)), 1)

    def test_derived_record_rejects_non_observation_parent(self):
        parent = make_record(evidence_type="guard", status="active")

        with self.assertRaisesRegex(ValueError, "evaluation_observation"):
            curator.build_derived_record(
                kind="guard",
                genres=["slam"],
                scopes=["spoken_delivery"],
                directive="A slam legyen egyszeri hallásra követhető.",
                guard_level="hard",
                confidence="high",
                basis="Explicit human feedback.",
                parents=[parent],
            )

    def test_decision_rejects_missing_curation_reason(self):
        with self.assertRaisesRegex(ValueError, "curation reason is required"):
            curator.build_decision("ev-" + "1" * 24, "active", "   ")

    def test_derived_record_rejects_unknown_scope(self):
        parent = make_record(evidence_type="evaluation_observation")

        with self.assertRaisesRegex(ValueError, "scope"):
            curator.build_derived_record(
                kind="guard",
                genres=["slam"],
                scopes=["unrecognized_scope"],
                directive="A slam legyen egyszeri hallásra követhető.",
                guard_level="hard",
                confidence="high",
                basis="Explicit human feedback.",
                parents=[parent],
            )

    def test_derived_record_rejects_invalid_guard_level(self):
        parent = make_record(evidence_type="evaluation_observation")

        with self.assertRaisesRegex(ValueError, "guard level"):
            curator.build_derived_record(
                kind="guard",
                genres=["slam"],
                scopes=["spoken_delivery"],
                directive="A slam legyen egyszeri hallásra követhető.",
                guard_level="mandatory",
                confidence="high",
                basis="Explicit human feedback.",
                parents=[parent],
            )

    def test_derived_record_authors_explicit_polarity_and_active_supersession(self):
        parent = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        target = make_record(
            evidence_type="guard",
            evidence_id="ev-" + "3" * 24,
            status="active",
            content={"directive": "Régi szabály.", "guard_level": "hard", "polarity": "require"},
        )

        record = curator.build_derived_record(
            kind="guard",
            genres=["slam"],
            scopes=["spoken_delivery"],
            directive="Új szabály.",
            guard_level="hard",
            confidence="high",
            basis="Explicit human feedback.",
            parents=[parent],
            polarity="forbid",
            supersedes=[target],
        )

        self.assertEqual(record["content"]["polarity"], "forbid")
        self.assertEqual(record["supersedes"], [target["evidence_id"]])

    def test_derived_record_rejects_non_active_supersession_target(self):
        parent = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        target = make_record(evidence_type="guard", evidence_id="ev-" + "3" * 24)

        with self.assertRaisesRegex(ValueError, "supersedes.*active"):
            curator.build_derived_record(
                kind="guard",
                genres=["slam"],
                scopes=["spoken_delivery"],
                directive="Új szabály.",
                guard_level="hard",
                confidence="high",
                basis="Explicit human feedback.",
                parents=[parent],
                polarity="require",
                supersedes=[target],
            )

    def test_derived_record_rejects_duplicate_parent_ids(self):
        parent = make_record(evidence_type="evaluation_observation")

        with self.assertRaisesRegex(ValueError, "duplicate parent"):
            curator.build_derived_record(
                kind="guard",
                genres=["slam"],
                scopes=["spoken_delivery"],
                directive="A slam legyen egyszeri hallásra követhető.",
                guard_level="hard",
                confidence="high",
                basis="Explicit human feedback.",
                parents=[parent, parent],
            )

    def test_rejected_record_cannot_transition_to_active(self):
        record = make_record(evidence_type="evaluation_observation", status="rejected")

        with self.assertRaisesRegex(ValueError, "invalid transition"):
            evidence_vault.project_state([record], [make_decision(record["evidence_id"], "active")])

    def test_active_derived_record_requires_observation_parent(self):
        record = make_record(
            evidence_type="mechanism",
            authority="genre_mechanism",
            status="pending_review",
            provenance={
                "source_kind": "curated_evaluation_observations",
                "source_run_id": "curation-01",
                "source_item_id": "derived-rule",
                "brief_id": "curated-derived",
                "source_sha256": "b" * 64,
                "parent_evidence_ids": ["ev-" + "2" * 24],
            },
        )
        parent = make_record(
            evidence_type="utility_observation",
            authority="utility_only",
            status="active",
            evidence_id="ev-" + "2" * 24,
        )

        with self.assertRaisesRegex(ValueError, "evaluation_observation"):
            evidence_vault.project_state(
                [parent, record], [make_decision(record["evidence_id"], "active")]
            )

    def test_supersedes_rejects_missing_or_non_active_record(self):
        observation = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        record = make_record(
            evidence_type="guard",
            status="pending_review",
            supersedes=["ev-" + "3" * 24],
        )

        with self.assertRaisesRegex(ValueError, "supersedes.*missing"):
            evidence_vault.project_state([observation, record], [make_decision(record["evidence_id"], "active")])

        retired = make_record(
            evidence_type="evaluation_observation",
            evidence_id="ev-" + "3" * 24,
            status="retired",
        )
        with self.assertRaisesRegex(ValueError, "supersedes.*active"):
            evidence_vault.project_state([observation, retired, record], [make_decision(record["evidence_id"], "active")])

    def test_create_derived_validates_final_state_before_writing(self):
        observation = make_record(evidence_type="evaluation_observation", status="pending_review")
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(
                Path(directory), [observation], [make_decision(observation["evidence_id"], "rejected")]
            )
            before_evidence = evidence_path.read_bytes()
            before_decisions = decision_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "evaluation_observation"):
                curator.create_derived(
                    evidence_path=evidence_path,
                    decision_path=decision_path,
                    kind="guard",
                    genres=["slam"],
                    scopes=["spoken_delivery"],
                    directive="A slam legyen egyszeri hallásra követhető.",
                    guard_level="hard",
                    confidence="high",
                    basis="Explicit human feedback.",
                    parent_ids=[observation["evidence_id"]],
                    activate=True,
                )

            self.assertEqual(evidence_path.read_bytes(), before_evidence)
            self.assertEqual(decision_path.read_bytes(), before_decisions)

    def test_create_derived_is_idempotent_after_activation(self):
        observation = make_record(evidence_type="evaluation_observation", status="pending_review")
        arguments = {
            "kind": "guard",
            "genres": ["slam"],
            "scopes": ["spoken_delivery"],
            "directive": "A slam legyen egyszeri hallásra követhető.",
            "guard_level": "hard",
            "confidence": "high",
            "basis": "Explicit human feedback.",
            "parent_ids": [observation["evidence_id"]],
            "activate": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(Path(directory), [observation], [])
            first = curator.create_derived(evidence_path=evidence_path, decision_path=decision_path, **arguments)
            evidence_after_first = evidence_path.read_bytes()
            decisions_after_first = decision_path.read_bytes()
            second = curator.create_derived(evidence_path=evidence_path, decision_path=decision_path, **arguments)

            self.assertEqual(second["evidence_id"], first["evidence_id"])
            self.assertEqual(evidence_path.read_bytes(), evidence_after_first)
            self.assertEqual(decision_path.read_bytes(), decisions_after_first)

    def test_cli_authors_require_forbid_conflict(self):
        observation = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(Path(directory), [observation], [])
            common = [
                sys.executable,
                str(CURATOR_PATH),
                "create-derived",
                "--evidence-ledger", str(evidence_path),
                "--decision-ledger", str(decision_path),
                "--type", "guard",
                "--genre", "slam",
                "--scope", "spoken_delivery",
                "--guard-level", "hard",
                "--confidence", "high",
                "--basis", "Explicit conflict evidence.",
                "--parent-run", observation["provenance"]["source_run_id"],
                "--parent-brief", observation["provenance"]["brief_id"],
                "--activate",
            ]
            required = subprocess.run(
                common + ["--directive", "A szabályt alkalmazd.", "--polarity", "require"],
                capture_output=True,
                text=True,
                check=False,
            )
            forbidden = subprocess.run(
                common + ["--directive", "A szabályt ne alkalmazd.", "--polarity", "forbid"],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(required.returncode, 0, required.stderr)
            self.assertEqual(forbidden.returncode, 0, forbidden.stderr)
            state = evidence_vault.project_state(
                evidence_vault.read_jsonl(evidence_path), evidence_vault.read_jsonl(decision_path)
            )
            selected = evidence_vault.select_evidence(
                selector_portfolio(), selector_plan(), state, evidence_vault.load_policy(POLICY_PATH)
            )
            self.assertEqual(selected["guards"], [])
            self.assertEqual(len(selected["conflicts"]), 1)

    def test_cli_authors_repeatable_supersession_of_active_rules(self):
        observation = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        targets = [
            make_record(
                evidence_type="guard",
                evidence_id=f"ev-{number:024x}",
                status="active",
                content={
                    "directive": f"Régi szabály {number}.",
                    "guard_level": "hard",
                    "polarity": "require",
                },
            )
            for number in (3, 4)
        ]
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(Path(directory), [observation, *targets], [])
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CURATOR_PATH),
                    "create-derived",
                    "--evidence-ledger", str(evidence_path),
                    "--decision-ledger", str(decision_path),
                    "--type", "guard",
                    "--genre", "slam",
                    "--scope", "spoken_delivery",
                    "--guard-level", "hard",
                    "--polarity", "forbid",
                    "--confidence", "high",
                    "--basis", "Explicit supersession evidence.",
                    "--directive", "Az új szabály írja felül a régieket.",
                    "--parent-run", observation["provenance"]["source_run_id"],
                    "--parent-brief", observation["provenance"]["brief_id"],
                    "--supersedes", targets[1]["evidence_id"],
                    "--supersedes", targets[0]["evidence_id"],
                    "--activate",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            record = json.loads(completed.stdout)
            self.assertEqual(record["supersedes"], sorted(item["evidence_id"] for item in targets))
            state = evidence_vault.project_state(
                evidence_vault.read_jsonl(evidence_path), evidence_vault.read_jsonl(decision_path)
            )
            selected = evidence_vault.select_evidence(
                selector_portfolio(), selector_plan(), state, evidence_vault.load_policy(POLICY_PATH)
            )
            self.assertEqual(selected["conflicts"], [])
            self.assertEqual([item["evidence_id"] for item in selected["guards"]], [record["evidence_id"]])

    def test_parent_selector_pairs_must_resolve_exactly_once(self):
        first = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        second = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "3" * 24)
        second["provenance"]["source_run_id"] = first["provenance"]["source_run_id"]
        second["provenance"]["brief_id"] = first["provenance"]["brief_id"]

        with self.assertRaisesRegex(ValueError, "exactly one"):
            curator.resolve_parent_ids(
                [first, second], [first["provenance"]["source_run_id"]], [first["provenance"]["brief_id"]]
            )
        with self.assertRaisesRegex(ValueError, "equal lengths"):
            curator.resolve_parent_ids([first], ["hbt-abc"], [])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            curator.resolve_parent_ids([first], ["hbt-missing"], ["slam-missing"])

    def test_same_resolved_ledger_path_is_rejected_without_changing_bytes(self):
        observation = make_record(evidence_type="evaluation_observation", status="pending_review")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path, _ = write_ledgers(root, [observation], [])
            alias_path = root / "nested" / ".." / "evidence.jsonl"
            before = evidence_path.read_bytes()

            with self.assertRaisesRegex(ValueError, "different files"):
                curator.create_derived(
                    evidence_path=evidence_path,
                    decision_path=alias_path,
                    kind="guard",
                    genres=["slam"],
                    scopes=["spoken_delivery"],
                    directive="A slam legyen egyszeri hallásra követhető.",
                    guard_level="hard",
                    confidence="high",
                    basis="Explicit human feedback.",
                    parent_ids=[observation["evidence_id"]],
                    activate=True,
                )

            self.assertEqual(evidence_path.read_bytes(), before)

    def test_concurrent_create_derived_commands_preserve_both_transactions(self):
        first = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        first["provenance"]["source_run_id"] = "hbt-concurrent-a"
        first["provenance"]["brief_id"] = "slam-concurrent-a"
        second = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "3" * 24)
        second["provenance"]["source_run_id"] = "hbt-concurrent-b"
        second["provenance"]["brief_id"] = "slam-concurrent-b"
        fillers = []
        for number in range(4, 1204):
            filler = make_record(
                evidence_type="evaluation_observation",
                evidence_id=f"ev-{number:024x}",
            )
            filler["provenance"]["source_run_id"] = f"hbt-filler-{number}"
            filler["provenance"]["brief_id"] = f"slam-filler-{number}"
            fillers.append(filler)
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(Path(directory), [first, second, *fillers], [])
            common = [
                sys.executable,
                str(CURATOR_PATH),
                "create-derived",
                "--evidence-ledger", str(evidence_path),
                "--decision-ledger", str(decision_path),
                "--type", "guard",
                "--genre", "slam",
                "--scope", "spoken_delivery",
                "--guard-level", "hard",
                "--confidence", "high",
                "--basis", "Concurrent explicit feedback.",
                "--activate",
            ]
            left = subprocess.Popen(
                common + [
                    "--directive", "Az első párhuzamos slam-szabály.",
                    "--parent-run", first["provenance"]["source_run_id"],
                    "--parent-brief", first["provenance"]["brief_id"],
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            right = subprocess.Popen(
                common + [
                    "--directive", "A második párhuzamos slam-szabály.",
                    "--parent-run", second["provenance"]["source_run_id"],
                    "--parent-brief", second["provenance"]["brief_id"],
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            left_stdout, left_stderr = left.communicate(timeout=30)
            right_stdout, right_stderr = right.communicate(timeout=30)

            self.assertEqual(left.returncode, 0, left_stderr)
            self.assertEqual(right.returncode, 0, right_stderr)
            self.assertTrue(left_stdout)
            self.assertTrue(right_stdout)
            state = evidence_vault.project_state(
                evidence_vault.read_jsonl(evidence_path), evidence_vault.read_jsonl(decision_path)
            )
            derived = [item for item in state.values() if item["evidence_type"] == "guard"]
            self.assertEqual(len(derived), 2)
            self.assertTrue(all(item["status"] == "active" for item in derived))
            self.assertEqual(len(evidence_vault.read_jsonl(decision_path)), 2)

    def test_importer_and_curator_share_the_evidence_ledger_lock(self):
        observation = make_record(
            evidence_type="evaluation_observation",
            evidence_id="ev-" + "2" * 24,
            status="pending_review",
        )
        result = make_human_result(item_count=1)
        private_key = make_private_key(item_count=1)
        result["private_sha256"] = evidence_vault.canonical_sha256(private_key)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path, decision_path = write_ledgers(root, [observation], [])
            result_path = root / "result.json"
            private_path = root / "private.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            private_path.write_text(json.dumps(private_key), encoding="utf-8")
            importer_marker = root / "importer.ready"
            curator_marker = root / "curator.ready"
            processes = []

            with curator._LedgerTransactionLock(evidence_path, decision_path):
                importer_process = synchronized_cli_process(
                    "import_human_blind_feedback",
                    importer_marker,
                    [
                        "--result", str(result_path),
                        "--private-key", str(private_path),
                        "--ledger", str(evidence_path),
                    ],
                )
                curator_process = synchronized_cli_process(
                    "curate_evidence",
                    curator_marker,
                    [
                        "create-derived",
                        "--evidence-ledger", str(evidence_path),
                        "--decision-ledger", str(decision_path),
                        "--type", "guard",
                        "--genre", "slam",
                        "--scope", "spoken_delivery",
                        "--guard-level", "hard",
                        "--confidence", "high",
                        "--basis", "Concurrent explicit feedback.",
                        "--directive", "A párhuzamos slam-szabály.",
                        "--parent-run", observation["provenance"]["source_run_id"],
                        "--parent-brief", observation["provenance"]["brief_id"],
                        "--activate",
                    ],
                )
                processes = [importer_process, curator_process]
                wait_for_markers([importer_marker, curator_marker], processes)
                importer_blocked = process_is_blocked(importer_process)
                curator_blocked = process_is_blocked(curator_process)

            outputs = [process.communicate(timeout=30) for process in processes]
            self.assertTrue(importer_blocked, outputs[0])
            self.assertTrue(curator_blocked, outputs[1])
            for process, (_, stderr) in zip(processes, outputs):
                self.assertEqual(process.returncode, 0, stderr)
            state = evidence_vault.project_state(
                evidence_vault.read_jsonl(evidence_path), evidence_vault.read_jsonl(decision_path)
            )
            self.assertEqual(
                len([item for item in state.values() if item["evidence_type"] == "evaluation_observation"]),
                2,
            )
            guards = [item for item in state.values() if item["evidence_type"] == "guard"]
            self.assertEqual(len(guards), 1)
            self.assertEqual(guards[0]["status"], "active")

    def test_overlapping_ledger_pairs_share_each_per_ledger_lock(self):
        first = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "2" * 24)
        first["provenance"]["source_run_id"] = "hbt-overlap-a"
        first["provenance"]["brief_id"] = "slam-overlap-a"
        second = make_record(evidence_type="evaluation_observation", evidence_id="ev-" + "3" * 24)
        second["provenance"]["source_run_id"] = "hbt-overlap-b"
        second["provenance"]["brief_id"] = "slam-overlap-b"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence_path, decision_a = write_ledgers(root, [first, second], [])
            decision_b = root / "decisions-b.jsonl"
            marker_a = root / "curator-a.ready"
            marker_b = root / "curator-b.ready"
            common = [
                "create-derived",
                "--evidence-ledger", str(evidence_path),
                "--type", "guard",
                "--genre", "slam",
                "--scope", "spoken_delivery",
                "--guard-level", "hard",
                "--confidence", "high",
                "--basis", "Overlapping ledger feedback.",
                "--activate",
            ]

            with curator._LedgerTransactionLock(evidence_path, decision_a):
                first_process = synchronized_cli_process(
                    "curate_evidence",
                    marker_a,
                    [
                        *common,
                        "--decision-ledger", str(decision_a),
                        "--directive", "Az első átfedő szabály.",
                        "--parent-run", first["provenance"]["source_run_id"],
                        "--parent-brief", first["provenance"]["brief_id"],
                    ],
                )
                second_process = synchronized_cli_process(
                    "curate_evidence",
                    marker_b,
                    [
                        *common,
                        "--decision-ledger", str(decision_b),
                        "--directive", "A második átfedő szabály.",
                        "--parent-run", second["provenance"]["source_run_id"],
                        "--parent-brief", second["provenance"]["brief_id"],
                    ],
                )
                processes = [first_process, second_process]
                wait_for_markers([marker_a, marker_b], processes)
                first_blocked = process_is_blocked(first_process)
                second_blocked = process_is_blocked(second_process)

            outputs = [process.communicate(timeout=30) for process in processes]
            self.assertTrue(first_blocked, outputs[0])
            self.assertTrue(second_blocked, outputs[1])
            for process, (_, stderr) in zip(processes, outputs):
                self.assertEqual(process.returncode, 0, stderr)
            records = evidence_vault.read_jsonl(evidence_path)
            self.assertEqual(len([item for item in records if item["evidence_type"] == "guard"]), 2)
            self.assertEqual(len(evidence_vault.read_jsonl(decision_a)), 1)
            self.assertEqual(len(evidence_vault.read_jsonl(decision_b)), 1)

    def test_failed_create_command_releases_lock_for_the_next_command(self):
        observation = make_record(evidence_type="evaluation_observation", status="pending_review")
        with tempfile.TemporaryDirectory() as directory:
            evidence_path, decision_path = write_ledgers(Path(directory), [observation], [])
            common = [
                sys.executable,
                str(CURATOR_PATH),
                "create-derived",
                "--evidence-ledger", str(evidence_path),
                "--decision-ledger", str(decision_path),
                "--type", "guard",
                "--genre", "slam",
                "--scope", "spoken_delivery",
                "--guard-level", "hard",
                "--confidence", "high",
                "--basis", "Explicit human feedback.",
                "--parent-run", observation["provenance"]["source_run_id"],
                "--parent-brief", observation["provenance"]["brief_id"],
                "--activate",
            ]
            failed = subprocess.run(
                common + ["--directive", "A slam szabálya.", "--scope", "unknown_scope"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertNotEqual(failed.returncode, 0)

            valid = subprocess.run(
                common + ["--directive", "A slam legyen egyszeri hallásra követhető."],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertEqual(len(evidence_vault.read_jsonl(decision_path)), 1)


def selector_portfolio(execution_ids=("one", "two")):
    return {
        "sources": [
            {"id": source_id, "title": f"Source {source_id}", "raw_observation": "private source text"}
            for source_id in execution_ids
        ],
        "contrastive_calibration": {
            "execution_set": [{"id": source_id} for source_id in execution_ids],
        },
    }


def selector_plan(genre="slam", *, text="spoken delivery"):
    return {
        "brief": text,
        "genre": {"value": genre},
        "purpose": {"value": "clear delivery"},
        "audience": {"value": "live audience"},
        "query": {"value": text},
        "negative_preferences": ["avoid generic phrasing"],
    }


def active_derived(kind, number, *, genres=("slam",), scopes=("spoken_delivery",),
                   level="soft", polarity="prefer", supersedes=()):
    return make_record(
        evidence_id=f"ev-{number:024x}",
        evidence_type=kind,
        status="active",
        authority="generation_guard" if kind == "guard" else "genre_mechanism",
        genre=list(genres),
        scope=list(scopes),
        content={
            "directive": f"Directive {number}",
            "level": level,
            "polarity": polarity,
            "observation": "PRIVATE HUMAN OBSERVATION",
        },
        supersedes=list(supersedes),
    )


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.policy = evidence_vault.load_policy(POLICY_PATH)

    def select(self, items, *, plan=None, portfolio=None):
        projected = {item["evidence_id"]: item for item in items}
        return evidence_vault.select_evidence(
            portfolio or selector_portfolio(), plan or selector_plan(), projected, self.policy
        )

    def test_genre_specific_mechanism_beats_equivalent_global_record(self):
        global_item = active_derived("mechanism", 2, genres=("global",))
        slam_item = active_derived("mechanism", 1, genres=("slam",))

        selected = self.select([global_item, slam_item])

        self.assertEqual(selected["mechanisms"][0]["evidence_id"], slam_item["evidence_id"])

    def test_exact_genre_precedes_higher_scoring_global_mechanism(self):
        exact = active_derived("mechanism", 1, genres=("slam",), scopes=("campaign_coherence",))
        exact["confidence"]["level"] = "low"
        global_item = active_derived("mechanism", 2, genres=("global",), scopes=("spoken_delivery",))

        selected = self.select([global_item, exact])
        trace_by_id = {item["evidence_id"]: item for item in selected["selection_trace"]}

        self.assertLess(
            next(item["score"] for item in selected["mechanisms"] if item["evidence_id"] == exact["evidence_id"]),
            next(item["score"] for item in selected["mechanisms"] if item["evidence_id"] == global_item["evidence_id"]),
        )
        self.assertEqual(
            [item["evidence_id"] for item in selected["mechanisms"]],
            [exact["evidence_id"], global_item["evidence_id"]],
        )
        self.assertEqual(trace_by_id[exact["evidence_id"]]["genre_tier"], "exact")
        self.assertIn("genre:exact", trace_by_id[exact["evidence_id"]]["reasons"])

    def test_conflicting_guards_are_reported_and_both_excluded(self):
        require = active_derived("guard", 1, genres=("cikk",), scopes=("output_surface_markdown",), polarity="require")
        forbid = active_derived("guard", 2, genres=("cikk",), scopes=("output_surface_markdown",), polarity="forbid")

        selected = self.select([require, forbid], plan=selector_plan("cikk", text="markdown output"))

        self.assertEqual(selected["guards"], [])
        self.assertEqual(
            selected["conflicts"][0]["evidence_ids"],
            sorted([require["evidence_id"], forbid["evidence_id"]]),
        )

    def test_direct_supersession_avoids_a_guard_conflict(self):
        require = active_derived("guard", 1, genres=("cikk",), scopes=("output_surface_markdown",), polarity="require")
        forbid = active_derived(
            "guard", 2, genres=("cikk",), scopes=("output_surface_markdown",), polarity="forbid", supersedes=(require["evidence_id"],)
        )

        selected = self.select([require, forbid], plan=selector_plan("cikk", text="markdown output"))

        self.assertEqual(selected["conflicts"], [])
        self.assertEqual([item["evidence_id"] for item in selected["guards"]], [forbid["evidence_id"]])

    def test_hard_guards_survive_the_soft_limit(self):
        hard = active_derived("guard", 10, level="hard")
        soft = [active_derived("guard", number) for number in range(1, 5)]

        selected = self.select([hard, *soft])

        self.assertIn(hard["evidence_id"], [item["evidence_id"] for item in selected["guards"]])
        self.assertEqual(len(selected["guards"]), 4)

    def test_inactive_observations_are_never_selected(self):
        observation = make_record(
            evidence_id="ev-" + "f" * 24,
            evidence_type="evaluation_observation",
            status="active",
            authority="evaluation_only",
            content={"observation": "PRIVATE HUMAN OBSERVATION"},
        )

        selected = self.select([observation])

        self.assertEqual(selected["mechanisms"], [])
        self.assertEqual(selected["guards"], [])
        self.assertNotIn("PRIVATE HUMAN OBSERVATION", json.dumps(selected, ensure_ascii=False))

    def test_equal_scores_use_evidence_id_tie_breaking(self):
        later = active_derived("mechanism", 2)
        earlier = active_derived("mechanism", 1)

        selected = self.select([later, earlier])

        self.assertEqual(
            [item["evidence_id"] for item in selected["mechanisms"]],
            [earlier["evidence_id"], later["evidence_id"]],
        )

    def test_irrelevant_genre_is_excluded(self):
        article_only = active_derived("mechanism", 1, genres=("cikk",))

        selected = self.select([article_only], plan=selector_plan("slam"))

        self.assertEqual(selected["mechanisms"], [])

    def test_empty_ledger_has_a_deterministic_voice_only_fallback(self):
        selected = self.select([], portfolio=selector_portfolio(("one", "two")))

        self.assertEqual(set(selected), {
            "voice", "mechanisms", "guards", "conflicts", "selection_trace", "ledger_sha256", "policy_version",
        })
        self.assertEqual([item["evidence_id"] for item in selected["voice"]], ["voice-one", "voice-two"])
        self.assertEqual(selected["mechanisms"], [])
        self.assertEqual(selected["guards"], [])
        self.assertEqual(selected["conflicts"], [])
        self.assertEqual(selected["ledger_sha256"], evidence_vault.canonical_sha256({}))

    def test_voice_limit_preserves_execution_order(self):
        source_ids = tuple(f"source-{number}" for number in range(1, 8))

        selected = self.select([], portfolio=selector_portfolio(source_ids))

        self.assertEqual(
            [item["evidence_id"] for item in selected["voice"]],
            [f"voice-{source_id}" for source_id in source_ids[:5]],
        )

    def test_selected_derived_entries_are_sanitized(self):
        selected = self.select([active_derived("mechanism", 1)])

        self.assertEqual(
            set(selected["mechanisms"][0]),
            {"evidence_id", "evidence_type", "genre", "scope", "directive", "level", "confidence", "score", "reasons"},
        )
        self.assertNotIn("PRIVATE HUMAN OBSERVATION", json.dumps(selected, ensure_ascii=False))

    def test_trace_explains_every_selected_and_excluded_candidate_deterministically(self):
        selected_hard = active_derived("guard", 1, level="hard")
        inactive = active_derived("guard", 2)
        inactive["status"] = "pending_review"
        genre_mismatch = active_derived("mechanism", 3, genres=("cikk",))
        superseded = active_derived("mechanism", 4)
        replacement = active_derived("mechanism", 5, supersedes=(superseded["evidence_id"],))
        conflict_require = active_derived("guard", 6, polarity="require")
        conflict_forbid = active_derived("guard", 7, polarity="forbid")
        soft_guards = [active_derived("guard", number) for number in range(8, 12)]
        mechanisms = [active_derived("mechanism", number) for number in range(12, 15)]
        unsupported = make_record(
            evidence_id="ev-" + "f" * 24,
            evidence_type="evaluation_observation",
            authority="evaluation_only",
            content={"observation": "PRIVATE HUMAN OBSERVATION"},
        )
        items = [
            selected_hard,
            inactive,
            genre_mismatch,
            superseded,
            replacement,
            conflict_require,
            conflict_forbid,
            *soft_guards,
            *mechanisms,
            unsupported,
        ]
        portfolio = selector_portfolio(tuple(f"source-{number}" for number in range(1, 8)))

        selected = self.select(items, portfolio=portfolio)
        reversed_selection = self.select(list(reversed(items)), portfolio=portfolio)
        trace = selected["selection_trace"]
        trace_by_id = {row["evidence_id"]: row for row in trace}

        expected_ids = {item["evidence_id"] for item in items} | {
            f"voice-source-{number}" for number in range(1, 8)
        }
        self.assertEqual(set(trace_by_id), expected_ids)
        self.assertEqual(trace, reversed_selection["selection_trace"])
        self.assertEqual(trace_by_id[inactive["evidence_id"]]["exclusion_reason"], "inactive")
        self.assertEqual(trace_by_id[genre_mismatch["evidence_id"]]["exclusion_reason"], "genre_mismatch")
        self.assertEqual(trace_by_id[superseded["evidence_id"]]["exclusion_reason"], "superseded")
        self.assertEqual(trace_by_id[conflict_require["evidence_id"]]["exclusion_reason"], "conflict")
        self.assertEqual(trace_by_id[conflict_forbid["evidence_id"]]["exclusion_reason"], "conflict")
        self.assertEqual(trace_by_id[soft_guards[-1]["evidence_id"]]["exclusion_reason"], "soft_guard_limit")
        self.assertEqual(trace_by_id[mechanisms[-1]["evidence_id"]]["exclusion_reason"], "mechanism_limit")
        self.assertEqual(trace_by_id[unsupported["evidence_id"]]["exclusion_reason"], "unsupported_type")
        self.assertEqual(trace_by_id["voice-source-6"]["exclusion_reason"], "voice_limit")
        self.assertTrue(trace_by_id[selected_hard["evidence_id"]]["selected"])
        self.assertIsNone(trace_by_id[selected_hard["evidence_id"]]["exclusion_reason"])
        self.assertEqual(trace_by_id[mechanisms[-1]["evidence_id"]]["genre_tier"], "exact")
        self.assertIsInstance(trace_by_id[mechanisms[-1]["evidence_id"]]["score"], float)
        self.assertNotIn("PRIVATE HUMAN OBSERVATION", json.dumps(trace, ensure_ascii=False))


class HumanBlindImportTests(unittest.TestCase):
    def test_import_builds_pending_observation_without_side_mapping(self):
        records = importer.build_observation_records(make_human_result(), make_private_key())

        self.assertEqual(len(records), 2)
        self.assertTrue(all(item["status"] == "pending_review" for item in records))
        rendered = json.dumps(records, ensure_ascii=False)
        self.assertNotIn('"left"', rendered)
        self.assertNotIn('"right"', rendered)
        self.assertNotIn("SECRET FULL DRAFT", rendered)
        self.assertEqual(
            set(records[0]["content"]["draft_sha256_by_system"]), {"engine_v3", "legacy"}
        )
        self.assertEqual(records[0]["evidence_type"], "evaluation_observation")
        evidence_vault.validate_record(records[0])

    def test_import_is_idempotent(self):
        records = importer.build_observation_records(make_human_result(), make_private_key())
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "evidence.jsonl"
            self.assertEqual(importer.append_new_records(records, ledger), 2)
            self.assertEqual(importer.append_new_records(records, ledger), 0)
            self.assertEqual(len(evidence_vault.read_jsonl(ledger)), 2)

    def test_import_records_do_not_mutate_the_immutable_result(self):
        result = make_human_result()
        records = importer.build_observation_records(result, make_private_key())

        records[0]["content"]["candidate_feedback"]["engine_v3"]["note"] = "Changed later"

        self.assertEqual(result["items"][0]["candidate_feedback"]["engine_v3"]["note"], "Natural.")

    def test_import_preserves_valid_string_candidate_feedback(self):
        records = importer.build_observation_records(make_human_result(), make_private_key())

        self.assertEqual(
            records[0]["content"]["candidate_feedback"],
            {
                "engine_v3": {"highlight": "Strong line", "note": "Natural."},
                "legacy": {"highlight": "", "note": "Stilted."},
            },
        )

    def test_import_sanitizes_hungarian_candidate_side_references_by_private_mapping(self):
        result = make_human_result(item_count=1)
        result["items"][0]["reason"] = (
            "A baloldali szakmaibb, a jobboldaliban több a játékosság. "
            "A jobb oldalihoz húzok, a baloldalinál viszont jobb a ritmus. "
            "Túl klisés a bal, a baloldalo mégis nyert."
        )
        result["items"][0]["general_note"] = "A bal oldaliban tisztább a zárás."
        result["items"][0]["candidate_feedback"]["engine_v3"]["note"] = (
            "A baloldali jó; a jobb oldalán egy kutyás matrica látszik."
        )

        record = importer.build_observation_records(result, make_private_key(item_count=1))[0]
        rendered = json.dumps(record["content"], ensure_ascii=False).casefold()

        self.assertNotRegex(rendered, r"\b(?:bal|jobb)\s*oldal(?:i|o)")
        self.assertNotRegex(rendered, r"\ba (?:bal|jobb)\s*[,.;:!?]")
        self.assertIn("engine v3-változat", rendered)
        self.assertIn("legacy-változat", rendered)
        self.assertIn("jobb oldalán egy kutyás matrica", rendered)

    def test_import_sanitizes_english_and_common_hungarian_candidate_references(self):
        result = make_human_result(item_count=1)
        result["items"][0]["reason"] = (
            "The left candidate wins; the right one is weaker. "
            "A bal nyert, a jobb gyengébb. "
            "A bal oldalon lévő változat szakmaibb."
        )

        record = importer.build_observation_records(result, make_private_key(item_count=1))[0]
        rendered = record["content"]["reason"].casefold()

        self.assertNotRegex(rendered, r"\b(?:left|right)\s+(?:candidate|one|version)")
        self.assertNotRegex(rendered, r"\ba (?:bal|jobb)\b")
        self.assertNotRegex(rendered, r"\b(?:bal|jobb) oldalon lévő")
        self.assertIn("engine v3", rendered)
        self.assertIn("legacy", rendered)

    def test_import_sanitizes_candidate_ordinals_but_preserves_quoted_source_words(self):
        result = make_human_result(item_count=1)
        result["items"][0]["reason"] = (
            "Az első változat lendületesebb, de a másodikban klisés a felállás. "
            "Az első ötletet viszont általában érdemes elvetni."
        )
        quoted_source = "Az „első” még kicsi szám."
        result["items"][0]["candidate_feedback"]["engine_v3"]["highlight"] = quoted_source

        record = importer.build_observation_records(result, make_private_key(item_count=1))[0]

        self.assertNotRegex(
            record["content"]["reason"].casefold(),
            r"\b(?:első|második)(?:ban|ben|nál|nél)|"
            r"\b(?:első|második) (?:változat|jelölt|szöveg|verzió|opció|válasz)\b",
        )
        self.assertIn("Engine v3-változat", record["content"]["reason"])
        self.assertIn("legacy-változatban", record["content"]["reason"])
        self.assertIn("Az első ötletet", record["content"]["reason"])
        self.assertEqual(
            quoted_source,
            record["content"]["candidate_feedback"]["engine_v3"]["highlight"],
        )

    def test_import_uses_reversed_private_mapping_when_naming_candidate_references(self):
        private_key = make_private_key(item_count=1)
        mapping = private_key["items"]["item-01"]
        mapping["left"], mapping["right"] = mapping["right"], mapping["left"]
        result = make_human_result(item_count=1)
        result["items"][0]["chosen_system"] = "legacy"
        result["items"][0]["reason"] = "A baloldali nyert, a jobboldali gyengébb."
        result["private_sha256"] = evidence_vault.canonical_sha256(private_key)

        record = importer.build_observation_records(result, private_key)[0]

        self.assertIn("A legacy-változat nyert", record["content"]["reason"])
        self.assertIn("az Engine v3-változat gyengébb", record["content"]["reason"])

    def test_import_rejects_candidate_feedback_nested_full_draft_key(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["engine_v3"]["full_draft"] = {
            "text": "SECRET FULL DRAFT",
        }

        with self.assertRaisesRegex(ValueError, "candidate_feedback"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_candidate_feedback_side_key(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["legacy"]["left"] = "SECRET FULL DRAFT"

        with self.assertRaisesRegex(ValueError, "candidate_feedback"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_candidate_feedback_candidate_label_key(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["engine_v3"]["candidate_label"] = "A"

        with self.assertRaisesRegex(ValueError, "candidate_feedback"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_non_string_candidate_feedback_values(self):
        for field, value in (("highlight", {"text": "SECRET FULL DRAFT"}), ("note", ["not text"])):
            with self.subTest(field=field):
                result = make_human_result()
                result["items"][0]["candidate_feedback"]["engine_v3"][field] = value
                with self.assertRaisesRegex(ValueError, "candidate_feedback"):
                    importer.build_observation_records(result, make_private_key())

    def test_import_cli_does_not_append_rejected_candidate_feedback(self):
        result = make_human_result()
        result["items"][0]["candidate_feedback"]["engine_v3"]["full_draft"] = {
            "text": "SECRET FULL DRAFT",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            private_key_path = root / "private-key.json"
            ledger = root / "evidence.jsonl"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            private_key_path.write_text(json.dumps(make_private_key()), encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(IMPORTER_PATH), "--result", str(result_path),
                 "--private-key", str(private_key_path), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(ledger.exists())

    def test_import_accepts_actual_finalized_shape_without_boolean_marker(self):
        importer.validate_human_result(make_human_result())

    def test_import_rejects_explicit_false_finalized_marker(self):
        with self.assertRaisesRegex(ValueError, "finalized"):
            importer.validate_human_result(make_human_result(finalized=False))

    def test_import_rejects_missing_or_invalid_finalized_timestamp(self):
        missing = make_human_result()
        missing.pop("finalized_at")
        with self.assertRaisesRegex(ValueError, "finalized_at"):
            importer.validate_human_result(missing)
        with self.assertRaisesRegex(ValueError, "finalized_at"):
            importer.validate_human_result(make_human_result(finalized_at="not-a-timestamp"))

    def test_import_rejects_item_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "item_count"):
            importer.validate_human_result(make_human_result(item_count=2, items=[]))

    def test_import_rejects_duplicate_brief_ids(self):
        result = make_human_result()
        result["items"][1]["brief_id"] = result["items"][0]["brief_id"]
        with self.assertRaisesRegex(ValueError, "brief_id"):
            importer.validate_human_result(result)

    def test_import_rejects_invalid_draft_hash(self):
        result = make_human_result()
        result["items"][0]["draft_hashes"]["left"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "draft_hashes"):
            importer.validate_human_result(result)

    def test_import_rejects_unknown_system(self):
        result = make_human_result()
        result["items"][0]["chosen_system"] = "unknown"
        with self.assertRaisesRegex(ValueError, "chosen_system"):
            importer.validate_human_result(result)

    def test_import_rejects_unknown_choice(self):
        result = make_human_result()
        result["items"][0]["choice"] = "middle"

        with self.assertRaisesRegex(ValueError, "choice"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_chosen_system_that_disagrees_with_private_choice_mapping(self):
        result = make_human_result()
        result["items"][0]["chosen_system"] = "legacy"

        with self.assertRaisesRegex(ValueError, "choice.*chosen_system|chosen_system.*choice"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_private_key_canonical_hash_mismatch(self):
        result = make_human_result(private_sha256="0" * 64)

        with self.assertRaisesRegex(ValueError, "private_sha256"):
            importer.build_observation_records(result, make_private_key())

    def test_import_rejects_safety_flags_that_allow_learning(self):
        for field, value in (
            ("utility_written", True),
            ("learned_preference_claimed", True),
            ("feedback_review_required", False),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    importer.validate_human_result(make_human_result(**{field: value}))

    def test_import_rejects_private_key_brief_or_system_mapping_mismatch(self):
        bad_brief = make_private_key()
        bad_brief["items"]["item-01"]["brief_id"] = "other-brief"
        bad_brief_result = make_human_result()
        bad_brief_result["private_sha256"] = evidence_vault.canonical_sha256(bad_brief)
        with self.assertRaisesRegex(ValueError, "brief_id"):
            importer.build_observation_records(bad_brief_result, bad_brief)

        bad_system = make_private_key()
        bad_system["items"]["item-01"]["right"] = "unknown"
        bad_system_result = make_human_result()
        bad_system_result["private_sha256"] = evidence_vault.canonical_sha256(bad_system)
        with self.assertRaisesRegex(ValueError, "system mapping"):
            importer.build_observation_records(bad_system_result, bad_system)

    def test_import_cli_reports_atomic_append_counts_and_ledger_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            private_key_path = root / "private-key.json"
            ledger = root / "evidence.jsonl"
            result_path.write_text(json.dumps(make_human_result()), encoding="utf-8")
            private_key_path.write_text(json.dumps(make_private_key()), encoding="utf-8")

            first = subprocess.run(
                [sys.executable, str(IMPORTER_PATH), "--result", str(result_path),
                 "--private-key", str(private_key_path), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(first.stdout, first.stderr)
            self.assertEqual(json.loads(first.stdout)["added_records"], 2)

            second = subprocess.run(
                [sys.executable, str(IMPORTER_PATH), "--result", str(result_path),
                 "--private-key", str(private_key_path), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertTrue(second.stdout, second.stderr)
            report = json.loads(second.stdout)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(report["source_run_id"], "hbt-" + "a" * 24)
            self.assertEqual(report["input_items"], 2)
            self.assertEqual(report["added_records"], 0)
            self.assertEqual(report["existing_records"], 2)
            self.assertRegex(report["ledger_sha256"], r"^[0-9a-f]{64}$")


class DocumentationContractTests(unittest.TestCase):
    def test_live_evidence_workflow_and_safety_contract_are_documented(self):
        engine_documentation = ENGINE_V3_DOC_PATH.read_text(encoding="utf-8")
        skill_documentation = SKILL_DOC_PATH.read_text(encoding="utf-8")

        engine_contracts = (
            "curate_evidence.py",
            "--evidence-ledger skills/peter-irta/state/evidence-vault/evidence.jsonl",
            "--decision-ledger skills/peter-irta/state/evidence-vault/decisions.jsonl",
            "--polarity",
            "--supersedes",
            "nem ír automatikusan retrieval-utility",
        )
        for contract in engine_contracts:
            with self.subTest(document="engine-v3.md", contract=contract):
                self.assertIn(contract, engine_documentation)

        skill_contracts = (
            "evidence_policy",
            "selected_evidence",
            "selection_trace",
            "conflicts",
            "manual_policy_cold_start",
        )
        for contract in skill_contracts:
            with self.subTest(document="SKILL.md", contract=contract):
                self.assertIn(contract, skill_documentation)


if __name__ == "__main__":
    unittest.main()
