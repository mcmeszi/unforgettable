import importlib.util
import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "build_writing_sheets.py"
SPEC = importlib.util.spec_from_file_location("build_writing_sheets", MODULE_PATH)
writing_sheets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(writing_sheets)


def make_document(index, title, decision="include-core", genre="slam"):
    return {
        "id": f"doc-{index}",
        "title": title,
        "genre": genre,
        "decision": decision,
        "authority": "drive-original",
        "content_level": "full",
        "word_count": 300 + index,
        "topics": ["test", "közönség"],
        "top_terms": ["hang", "ritmus"],
        "chunk_ids": [index],
    }


class WritingSheetTests(unittest.TestCase):
    def test_sheet_uses_only_eligible_unique_families(self):
        documents = [
            make_document(0, "Borostyán"),
            make_document(1, "Cédrus"),
            make_document(2, "Diófa"),
            make_document(3, "Borostyán végleges"),
            make_document(4, "Tiltott", decision="reference-only"),
        ]
        chunks = [
            {"id": str(index), "document_id": doc["id"], "text": "Te figyelj! Test és közönség.\nMiért?"}
            for index, doc in enumerate(documents)
        ]

        result = writing_sheets.build_sheets(documents, chunks, target_genres=("slam",))
        sheet = result["sheets"]["slam"]
        evidence_ids = {item["id"] for item in sheet["evidence_families"]}

        self.assertEqual(sheet["evidence_family_count"], 3)
        self.assertEqual(len(evidence_ids), 3)
        self.assertNotIn("doc-4", evidence_ids)
        self.assertEqual(sheet["confidence"], "supported")

    def test_sheet_downgrades_claims_below_three_families(self):
        documents = [make_document(0, "Borostyán"), make_document(1, "Cédrus")]
        chunks = [
            {"id": str(index), "document_id": doc["id"], "text": "Rövid előadott sor."}
            for index, doc in enumerate(documents)
        ]

        result = writing_sheets.build_sheets(documents, chunks, target_genres=("slam",))
        sheet = result["sheets"]["slam"]

        self.assertEqual(sheet["confidence"], "insufficient")
        self.assertEqual(sheet["supported_claims"], [])
        self.assertTrue(sheet["fallback_required"])

    def test_email_sheet_labels_professional_sources_as_adjacent_evidence(self):
        documents = [
            make_document(index, title, genre="professional/other")
            for index, title in enumerate(("Borostyán", "Cédrus", "Diófa"))
        ]
        chunks = [
            {"id": str(index), "document_id": doc["id"], "text": "Pontos szakmai üzenet és cselekvés."}
            for index, doc in enumerate(documents)
        ]

        result = writing_sheets.build_sheets(documents, chunks, target_genres=("email",))
        sheet = result["sheets"]["email"]

        self.assertEqual(sheet["source_basis"], "adjacent")
        self.assertEqual(sheet["confidence"], "adjacent")
        self.assertFalse(sheet["fallback_required"])

    def test_direct_email_profile_replaces_adjacent_email_basis(self):
        profile = {
            "sample": {"usable": 67},
            "email_style": {"median_words": 27, "median_sentence_words": 4.3},
            "prose_transfer": {"strong_for": ["cadence", "compression"]},
            "representative_evidence": [
                {"ref": "gmail-a", "purpose": "request"},
                {"ref": "gmail-b", "purpose": "transactional"},
                {"ref": "gmail-c", "purpose": "update"},
            ],
        }

        result = writing_sheets.build_sheets([], [], target_genres=("email",), email_profile=profile)
        sheet = result["sheets"]["email"]

        self.assertEqual(sheet["source_basis"], "direct-email-corpus")
        self.assertEqual(sheet["confidence"], "supported")
        self.assertEqual(sheet["evidence_family_count"], 67)
        self.assertEqual(sheet["email_style"]["median_words"], 27)
        self.assertEqual(sheet["prose_transfer"]["strong_for"], ["cadence", "compression"])

    def test_slack_profile_is_secondary_and_genre_bounded(self):
        profile = {
            "sample": {"usable": 788},
            "dialogue_mechanics": {
                "strong_for": ["response-opening", "disagreement-softening"],
                "weak_for": ["rhyme", "image-system"],
            },
            "calibration_policy": {
                "precedence": "direct-genre-corpus > slack-dialogue-profile",
            },
            "guardrails": ["A gépelési hibákat ne utánozd."],
        }

        result = writing_sheets.build_sheets(
            [],
            [],
            target_genres=("email", "proza", "vers"),
            slack_profile=profile,
        )

        self.assertEqual(result["sheets"]["email"]["dialogue_support"]["transfer_strength"], "strong")
        self.assertEqual(result["sheets"]["proza"]["dialogue_support"]["transfer_strength"], "conditional")
        self.assertEqual(result["sheets"]["vers"]["dialogue_support"]["transfer_strength"], "dialogue-only")
        self.assertEqual(result["sheets"]["vers"]["dialogue_support"]["role"], "secondary-dialogue-evidence")
        self.assertIn("rhyme", result["sheets"]["vers"]["dialogue_support"]["weak_for"])

    def test_small_slack_sample_is_not_attached(self):
        result = writing_sheets.build_sheets(
            [],
            [],
            target_genres=("email",),
            slack_profile={"sample": {"usable": 99}},
        )

        self.assertNotIn("dialogue_support", result["sheets"]["email"])

    def test_sanitized_slack_profile_contract_contains_no_raw_identifiers_or_text(self):
        profile = {
            "raw_message_storage": False,
            "sample": {"received": 800, "usable": 788},
            "aggregates": {"response_length": "short", "directness": "high"},
        }

        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key.casefold()
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from keys(child)

        self.assertFalse(profile["raw_message_storage"])
        self.assertEqual(profile["sample"]["received"], 800)
        stored_keys = set(keys(profile))
        for forbidden_key in (
            "message_text",
            "coworker_text",
            "channel_name",
            "workspace_id",
            "user_id",
            "email_address",
            "permalink",
            "message_timestamp",
        ):
            self.assertNotIn(forbidden_key, stored_keys)


if __name__ == "__main__":
    unittest.main()
