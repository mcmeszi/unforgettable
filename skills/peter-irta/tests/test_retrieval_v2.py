import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "vault_query.py"
SPEC = importlib.util.spec_from_file_location("vault_query", MODULE_PATH)
vault_query = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(vault_query)


def document(**overrides):
    base = {
        "id": "doc-1",
        "title": "Általános szöveg",
        "genre": "slam",
        "decision": "include-core",
        "authority": "drive-original",
        "content_level": "full",
        "word_count": 800,
        "topics": [],
        "top_terms": [],
        "snippet": "",
        "chunk_ids": ["chunk-1"],
    }
    base.update(overrides)
    return base


def profile(axis=0.5, tags=None):
    return {
        "range_axes": {
            "compressed_to_narrative": axis,
            "image_to_conceptual": axis,
            "page_to_performed": axis,
            "intimate_to_public": axis,
        },
        "technique_tags": list(tags or ["spoken-cadence"]),
        "feature_tokens": set(tags or ["spoken-cadence"]),
    }


class RagRootResolutionTests(unittest.TestCase):
    def test_environment_root_is_used_without_a_hard_coded_user_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("documents.json", "chunks.json", "connections.json"):
                (root / name).write_text("{}", encoding="utf-8")

            with patch.dict("os.environ", {"MIND_VAULT_RAG_ROOT": str(root)}, clear=False):
                self.assertEqual(vault_query.resolve_rag_root(None), root.resolve())


class RetrievalScoringTests(unittest.TestCase):
    def test_content_relevance_rewards_brief_match(self):
        matching = document(
            id="match",
            title="Apa és technológia",
            topics=["gyász", "technológia"],
            snippet="egy apa digitális emlékezete",
        )
        unrelated = document(id="other", title="Nyári kert", topics=["természet"])

        match_score = vault_query.content_relevance(
            matching, ("slam",), ("apa", "technologia"), ()
        )
        other_score = vault_query.content_relevance(
            unrelated, ("slam",), ("apa", "technologia"), ()
        )

        self.assertGreater(match_score, other_score + 5.0)

    def test_style_relevance_rewards_target_axis_proximity(self):
        near = vault_query.style_relevance(
            profile(axis=0.85), ("slam",), "slam", {"page_to_performed": 0.9}
        )
        far = vault_query.style_relevance(
            profile(axis=0.1), ("slam",), "slam", {"page_to_performed": 0.9}
        )

        self.assertGreater(near, far + 3.0)

    def test_reciprocal_rank_fusion_rewards_cross_channel_support(self):
        fused = vault_query.reciprocal_rank_fusion(
            [["content-only", "both"], ["style-only", "both"]], constant=10
        )

        self.assertGreater(fused["both"], fused["content-only"])
        self.assertGreater(fused["both"], fused["style-only"])

    def test_chunk_selection_uses_contextual_prefix_and_returns_context(self):
        doc = document(chunk_ids=[0, 1])
        chunks = [
            {"id": 0, "position": 0, "text": "csendes ajtó", "contextual_prefix": "Cím: Másik | Szerep: nyitás"},
            {"id": 1, "position": 1, "text": "hangos ablak", "contextual_prefix": "Cím: Kvantum | Szerep: zárlat"},
        ]

        chosen = vault_query.choose_chunks(doc, chunks, ("kvantum",), 1)

        self.assertEqual(chosen[0]["position"], 1)
        self.assertEqual(chosen[0]["context"], "Cím: Kvantum | Szerep: zárlat")

    def test_style_supplement_prefers_new_mode_when_fit_is_close(self):
        base_doc = document(id="base", title="Borostyán")
        base_profile = profile(tags=["spoken-cadence"])
        same_doc = document(id="same", title="Cédrus")
        same_profile = profile(tags=["spoken-cadence"])
        varied_doc = document(id="varied", title="Diófa")
        varied_profile = profile(tags=["narrative-turn", "image-driven"])

        chosen = vault_query.select_style_supplements(
            [(10.0, same_doc, same_profile), (9.2, varied_doc, varied_profile)],
            [(12.0, base_doc, base_profile, 1.0)],
            limit=1,
        )

        self.assertEqual(chosen[0][1]["id"], "varied")


class ConfidenceAndUtilityTests(unittest.TestCase):
    def test_confidence_abstains_when_style_evidence_is_thin(self):
        sources = [
            {
                "id": "one",
                "genre": "email",
                "content_score": 10.0,
                "style_score": 2.0,
                "retrieval_channel": "content",
                "authority": "drive-original",
            }
        ]

        result = vault_query.retrieval_confidence(sources, ("email",), requested_limit=5)

        self.assertEqual(result["level"], "low")
        self.assertTrue(result["abstain_from_voice_claim"])
        self.assertIn("insufficient_portfolio", result["reasons"])

    def test_utility_requires_three_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "utility.jsonl"
            rows = [
                {"genre": "slam", "utility": 1, "source_ids": ["stable"]},
                {"genre": "slam", "utility": 1, "source_ids": ["stable"]},
                {"genre": "slam", "utility": -1, "source_ids": ["thin"]},
            ]
            ledger.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            before = vault_query.utility_weights("slam", ledger_path=ledger)
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write('\n{"genre":"slam","utility":1,"source_ids":["stable"]}')
            after = vault_query.utility_weights("slam", ledger_path=ledger)

        self.assertNotIn("stable", before)
        self.assertNotIn("thin", before)
        self.assertGreater(after["stable"], 0.0)
        self.assertLessEqual(after["stable"], 0.5)


class RetrievalCliTests(unittest.TestCase):
    def test_cli_exposes_dual_channel_fusion_and_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            rag_root = Path(directory)
            documents = []
            chunks = []
            names = ["Borostyán", "Cédrus", "Diófa", "Eperfa", "Fenyő", "Gesztenye", "Hárs", "Ibolya"]
            for index in range(8):
                is_content = index < 4
                text = (
                    "Apa technológia emlékezet színpad kérdés? Te figyelj rám!\n" * (index + 2)
                    if is_content
                    else "Test közönség hang ritmus kérdés? Te figyelj, aztán végül.\n" * (index + 3)
                )
                chunks.append({"id": str(index), "document_id": f"doc-{index}", "text": text})
                documents.append(
                    document(
                        id=f"doc-{index}",
                        title=names[index],
                        topics=["apa", "technológia"] if is_content else ["előadás", "ritmus"],
                        top_terms=["apa", "technológia"] if is_content else ["közönség", "hang"],
                        snippet=text[:120],
                        chunk_ids=[index],
                        word_count=len(text.split()),
                    )
                )
            (rag_root / "documents.json").write_text(
                json.dumps({"documents": documents}, ensure_ascii=False), encoding="utf-8"
            )
            (rag_root / "chunks.json").write_text(
                json.dumps({"chunks": chunks}, ensure_ascii=False), encoding="utf-8"
            )
            (rag_root / "connections.json").write_text(
                json.dumps({"connections": []}), encoding="utf-8"
            )
            sheet_path = rag_root / "author-writing-sheets.json"
            sheet_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "sheets": {
                            "slam": {
                                "genre": "slam",
                                "confidence": "supported",
                                "fallback_required": False,
                                "evidence_family_count": 8,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(MODULE_PATH),
                    "--rag-root",
                    str(rag_root),
                    "--genre",
                    "slam",
                    "--query",
                    "apa technológia",
                    "--limit",
                    "6",
                    "--target-axis",
                    "page_to_performed=0.9",
                    "--writing-sheets",
                    str(sheet_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            result = json.loads(completed.stdout)

        channels = {source["retrieval_channel"] for source in result["sources"]}
        self.assertEqual(channels, {"content", "style"})
        self.assertTrue(all("fused_score" in source for source in result["sources"]))
        self.assertIn(result["retrieval_confidence"]["level"], {"high", "medium", "low"})
        self.assertEqual(result["selection_policy"]["fusion"], "reciprocal-rank-fusion")
        self.assertEqual(result["author_writing_sheet"]["genre"], "slam")


if __name__ == "__main__":
    unittest.main()
