import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "run_retrieval_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_retrieval_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark)

PREPARE_PATH = SCRIPTS / "prepare_generation_benchmark.py"
PREPARE_SPEC = importlib.util.spec_from_file_location("prepare_generation_benchmark", PREPARE_PATH)
prepare = importlib.util.module_from_spec(PREPARE_SPEC)
assert PREPARE_SPEC.loader is not None
PREPARE_SPEC.loader.exec_module(prepare)


class BenchmarkDatasetTests(unittest.TestCase):
    def test_default_dataset_has_three_blind_briefs_for_ten_genres(self):
        payload = json.loads(benchmark.DEFAULT_BRIEFS.read_text(encoding="utf-8"))
        briefs = payload["briefs"]
        counts = {}
        for brief in briefs:
            counts[brief["genre"]] = counts.get(brief["genre"], 0) + 1
            self.assertNotIn("expected_source", brief)
            self.assertEqual(set(brief["target_axes"]), set(benchmark.vault_query.RANGE_AXES))
            self.assertTrue(all(0.0 <= value <= 1.0 for value in brief["target_axes"].values()))

        self.assertEqual(len(briefs), 30)
        self.assertEqual(set(counts.values()), {3})
        self.assertEqual(len(counts), 10)


class BenchmarkRunnerTests(unittest.TestCase):
    def test_blind_labels_are_deterministic_and_balanced(self):
        briefs = [{"id": f"brief-{index}"} for index in range(20)]
        labels = benchmark.balanced_blind_labels(briefs)

        self.assertEqual(labels, benchmark.balanced_blind_labels(list(reversed(briefs))))
        self.assertEqual(sum(pair == ("legacy", "v2") for pair in labels.values()), 10)
        self.assertEqual(sum(pair == ("v2", "legacy") for pair in labels.values()), 10)

    def test_family_groups_merge_title_versions_once(self):
        profiled = [
            ({"id": "a", "title": "Borostyán", "provenance": {}}, {"content_family_terms": set()}),
            ({"id": "b", "title": "Borostyán végleges", "provenance": {}}, {"content_family_terms": set()}),
            ({"id": "c", "title": "Cédrus", "provenance": {}}, {"content_family_terms": set()}),
        ]

        groups = benchmark.build_family_groups(profiled)

        self.assertEqual(groups["a"], groups["b"])
        self.assertNotEqual(groups["a"], groups["c"])

    def test_fast_style_supplement_keeps_diversity_rule(self):
        selected = [(12.0, {"id": "base"}, {"feature_tokens": {"spoken"}, "technique_tags": ["spoken"]}, 1.0)]
        candidates = [
            (10.0, {"id": "same"}, {"feature_tokens": {"spoken"}, "technique_tags": ["spoken"]}),
            (9.2, {"id": "varied"}, {"feature_tokens": {"narrative"}, "technique_tags": ["narrative", "image"]}),
        ]
        groups = {"base": "base", "same": "same", "varied": "varied"}

        chosen = benchmark.benchmark_style_supplements(candidates, selected, 1, groups)

        self.assertEqual(chosen[0][1]["id"], "varied")

    def test_diagnostics_reject_blocked_and_duplicate_families(self):
        portfolio = {
            "sources": [
                {"id": "a", "title": "Borostyán", "decision": "include-core", "content_level": "full", "authority": "drive-original", "genre": "slam", "technique_tags": ["spoken"]},
                {"id": "b", "title": "Borostyán végleges", "decision": "include-core", "content_level": "full", "authority": "drive-original", "genre": "slam", "technique_tags": ["spoken"]},
                {"id": "c", "title": "Tiltott", "decision": "reference-only", "content_level": "full", "authority": "web-authored", "genre": "slam", "technique_tags": []},
            ]
        }

        result = benchmark.portfolio_diagnostics(portfolio, "slam")

        self.assertEqual(result["blocked_sources"], 1)
        self.assertEqual(result["duplicate_families"], 1)
        self.assertEqual(result["unique_family_count"], 2)

    def test_summary_does_not_declare_style_winner_from_retrieval_metrics(self):
        summary = benchmark.summarize_results(
            [
                {
                    "brief_id": "x",
                    "legacy": {"blocked_sources": 0, "unique_family_count": 5, "technique_count": 2},
                    "v2": {"blocked_sources": 0, "unique_family_count": 6, "technique_count": 4},
                }
            ]
        )

        self.assertEqual(summary["conclusion_scope"], "retrieval-diagnostics-only")
        self.assertNotIn("winner", summary)
        self.assertTrue(summary["generation_evaluation_required"])


class GenerationPackTests(unittest.TestCase):
    def test_public_writing_sheet_strips_private_source_ids_recursively(self):
        sheet = {
            "genre": "slam",
            "supported_claims": [
                {
                    "signal": "spoken-performance",
                    "source_count": 2,
                    "evidence_family_ids": ["drv-secret-one", "drv-secret-two"],
                }
            ],
        }

        compact = prepare._compact_sheet(sheet)

        self.assertNotIn("drv-secret", str(compact))
        self.assertEqual(compact["supported_claims"][0]["source_count"], 2)

    def test_each_genre_has_structured_quality_guards(self):
        expected_genre_guards = {
            "beszed": "live-specificity",
            "cikk": "tonal-balance",
            "dalszoveg": "rhyme-prosody",
            "email": "relationship-distance",
            "prezentacio": "slide-flow",
            "proza": "image-system",
            "reklam": "behavioral-insight",
            "slam": "spoken-orality",
            "tanulmany": "prose-surface",
            "vers": "image-system",
        }

        for genre, expected_guard in expected_genre_guards.items():
            with self.subTest(genre=genre):
                contract = prepare.genre_quality_contract(genre)
                guard_ids = {item["id"] for item in contract["release_checks"]}
                self.assertTrue(
                    {"cliche-specificity", "syntax-semantic-coherence", "motif-budget"}.issubset(guard_ids)
                )
                self.assertIn(expected_guard, guard_ids)
                self.assertTrue(contract["composition_recipe"])
                self.assertTrue(contract["hard_fail_if"])

    def test_public_jobs_hide_system_mapping_and_limit_evidence(self):
        retrieval = {
            "generation_jobs": [
                {
                    "brief_id": "slam-01",
                    "genre": "slam",
                    "brief": "Vak brief",
                    "audience": "közönség",
                    "constraints": ["rövid"],
                    "blind_mapping": {"A": "legacy", "B": "v2"},
                    "A": {"sources": [{"id": str(i), "title": f"Title {i}", "retrieval_channel": "legacy", "evidence": [{"text": f"Evidence {i}"}], "technique_tags": ["spoken"]} for i in range(7)]},
                    "B": {"sources": [{"id": str(i), "title": f"Title {i}", "retrieval_channel": "content" if i < 3 else "style", "evidence": [{"text": f"Evidence {i}"}], "technique_tags": ["spoken"]} for i in range(7)]},
                }
            ]
        }
        sheets = {"sheets": {"slam": {"genre": "slam", "confidence": "supported", "caricature_guards": ["guard"]}}}

        public_jobs, blind_key = prepare.build_generation_pack(retrieval, sheets)
        serialized = json.dumps(public_jobs)

        self.assertEqual(len(public_jobs), 2)
        self.assertNotIn("legacy", serialized)
        self.assertNotIn('"v2"', serialized)
        self.assertLessEqual(max(len(job["evidence_sources"]) for job in public_jobs), 4)
        self.assertEqual(blind_key["slam-01"]["A"], "legacy")
        self.assertEqual(public_jobs[0]["author_writing_sheet"]["confidence"], "supported")
        self.assertEqual(public_jobs[0]["genre_quality_contract"]["genre"], "slam")
        self.assertIn(
            "spoken-orality",
            {item["id"] for item in public_jobs[0]["genre_quality_contract"]["release_checks"]},
        )

    def test_private_manifest_preserves_candidate_run_and_source_ids(self):
        retrieval = {
            "generation_jobs": [
                {
                    "brief_id": "vers-01",
                    "genre": "vers",
                    "blind_mapping": {"A": "v2", "B": "legacy"},
                    "A": {"run_id": "run-v2", "sources": [{"id": "source-v2-a"}, {"id": "source-v2-b"}]},
                    "B": {"run_id": "run-v1", "sources": [{"id": "source-v1"}]},
                }
            ]
        }

        manifest = prepare.build_private_generation_manifest(retrieval)

        self.assertEqual(manifest["jobs"]["vers-01-A"]["system"], "v2")
        self.assertEqual(manifest["jobs"]["vers-01-A"]["retrieval_run_id"], "run-v2")
        self.assertEqual(manifest["jobs"]["vers-01-A"]["source_ids"], ["source-v2-a", "source-v2-b"])
        self.assertEqual(manifest["jobs"]["vers-01-B"]["system"], "legacy")

    def test_private_manifest_derives_stable_portfolio_id_when_run_id_is_missing(self):
        retrieval = {
            "generation_jobs": [
                {
                    "brief_id": "cikk-01",
                    "genre": "cikk",
                    "blind_mapping": {"A": "legacy", "B": "v2"},
                    "A": {"sources": [{"id": "alpha"}, {"id": "beta"}]},
                    "B": {"sources": [{"id": "gamma"}]},
                }
            ]
        }

        first = prepare.build_private_generation_manifest(retrieval)
        second = prepare.build_private_generation_manifest(retrieval)

        a = first["jobs"]["cikk-01-A"]
        b = first["jobs"]["cikk-01-B"]
        self.assertTrue(a["retrieval_run_id"].startswith("benchmark-portfolio-"))
        self.assertEqual(a["run_id_origin"], "derived-portfolio-fingerprint")
        self.assertEqual(a["retrieval_run_id"], second["jobs"]["cikk-01-A"]["retrieval_run_id"])
        self.assertNotEqual(a["retrieval_run_id"], b["retrieval_run_id"])

    def test_private_manifest_links_only_generation_evidence_to_blind_labels(self):
        sources = [
            {"id": "content-1", "retrieval_channel": "content"},
            {"id": "content-2", "retrieval_channel": "content"},
            {"id": "content-unused", "retrieval_channel": "content"},
            {"id": "style-1", "retrieval_channel": "style"},
            {"id": "style-2", "retrieval_channel": "style"},
            {"id": "style-unused", "retrieval_channel": "style"},
        ]
        retrieval = {
            "generation_jobs": [
                {
                    "brief_id": "slam-01",
                    "genre": "slam",
                    "blind_mapping": {"A": "v2", "B": "legacy"},
                    "A": {"sources": sources},
                    "B": {"sources": sources},
                }
            ]
        }

        manifest = prepare.build_private_generation_manifest(retrieval)
        candidate = manifest["jobs"]["slam-01-A"]

        self.assertEqual(candidate["source_ids"], ["content-1", "content-2", "style-1", "style-2"])
        self.assertEqual(
            candidate["source_linkage"],
            [
                {"source_label": "S1", "id": "content-1"},
                {"source_label": "S2", "id": "content-2"},
                {"source_label": "S3", "id": "style-1"},
                {"source_label": "S4", "id": "style-2"},
            ],
        )
        self.assertEqual(len(candidate["portfolio_source_ids"]), 6)


if __name__ == "__main__":
    unittest.main()
