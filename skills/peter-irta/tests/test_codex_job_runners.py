import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
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


generation = load_module("run_codex_generation_jobs")
evaluation = load_module("run_codex_evaluation_jobs")


class CodexGenerationRunnerResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output_dir = self.root / "outputs"
        self.output_dir.mkdir()
        self.workdir = self.root / "work"
        self.workdir.mkdir()
        self.job = {"job_id": "generation-1", "brief": "Eredeti brief", "genre": "slam"}

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _completed_generation(command, **_kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_text("Ez egy kellően hosszú, érvényes vak benchmark generált szöveg.", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    def _generate(self, job=None, model="model-a"):
        with mock.patch.object(generation.shutil, "which", return_value="codex"), mock.patch.object(
            generation.subprocess, "run", side_effect=self._completed_generation
        ):
            return generation.run_job(job or self.job, self.output_dir, model, self.workdir)

    def test_unchanged_job_and_model_skip_the_bound_output(self):
        self.assertEqual(self._generate(), ("generation-1", True, "generated"))
        self.assertTrue((self.output_dir / "generation-1.md.meta.json").exists())

        with mock.patch.object(generation.subprocess, "run") as run:
            result = generation.run_job(self.job, self.output_dir, "model-a", self.workdir)

        self.assertEqual(result, ("generation-1", True, "skipped"))
        run.assert_not_called()

    def test_changed_job_payload_regenerates_the_same_named_output(self):
        self._generate()
        changed_job = {**self.job, "brief": "Megváltozott brief"}

        with mock.patch.object(generation.shutil, "which", return_value="codex"), mock.patch.object(
            generation.subprocess, "run", side_effect=self._completed_generation
        ) as run:
            result = generation.run_job(changed_job, self.output_dir, "model-a", self.workdir)

        self.assertEqual(result, ("generation-1", True, "generated"))
        self.assertEqual(run.call_count, 1)

    def test_changed_model_regenerates_the_same_named_output(self):
        self._generate()

        with mock.patch.object(generation.shutil, "which", return_value="codex"), mock.patch.object(
            generation.subprocess, "run", side_effect=self._completed_generation
        ) as run:
            result = generation.run_job(self.job, self.output_dir, "model-b", self.workdir)

        self.assertEqual(result, ("generation-1", True, "generated"))
        self.assertEqual(run.call_count, 1)


class CodexEvaluationRunnerResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output_dir = self.root / "outputs"
        self.output_dir.mkdir()
        self.workdir = self.root / "work"
        self.workdir.mkdir()
        self.schema_path = self.workdir / "schema.json"
        self.schema_path.write_text("{}", encoding="utf-8")
        self.job = {"job_id": "evaluation-1", "candidate_1": "A", "candidate_2": "B"}

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _completed_evaluation(command, **_kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_text(
            json.dumps({"job_id": "evaluation-1", "winner": "tie"}),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stderr="")

    def _evaluate(self, job=None, model="model-a"):
        with mock.patch.object(evaluation.shutil, "which", return_value="codex"), mock.patch.object(
            evaluation.subprocess, "run", side_effect=self._completed_evaluation
        ):
            return evaluation.run_job(
                job or self.job,
                self.output_dir,
                model,
                self.workdir,
                self.schema_path,
                threading.Event(),
            )

    def test_unchanged_job_and_model_skip_the_bound_output(self):
        self.assertEqual(self._evaluate(), ("evaluation-1", True, "generated"))
        self.assertTrue((self.output_dir / "evaluation-1.json.meta.json").exists())

        with mock.patch.object(evaluation.subprocess, "run") as run:
            result = evaluation.run_job(
                self.job,
                self.output_dir,
                "model-a",
                self.workdir,
                self.schema_path,
                threading.Event(),
            )

        self.assertEqual(result, ("evaluation-1", True, "skipped"))
        run.assert_not_called()

    def test_changed_job_payload_regenerates_the_same_named_output(self):
        self._evaluate()
        changed_job = {**self.job, "candidate_2": "Megváltozott B"}

        with mock.patch.object(evaluation.shutil, "which", return_value="codex"), mock.patch.object(
            evaluation.subprocess, "run", side_effect=self._completed_evaluation
        ) as run:
            result = evaluation.run_job(
                changed_job,
                self.output_dir,
                "model-a",
                self.workdir,
                self.schema_path,
                threading.Event(),
            )

        self.assertEqual(result, ("evaluation-1", True, "generated"))
        self.assertEqual(run.call_count, 1)

    def test_changed_model_regenerates_the_same_named_output(self):
        self._evaluate()

        with mock.patch.object(evaluation.shutil, "which", return_value="codex"), mock.patch.object(
            evaluation.subprocess, "run", side_effect=self._completed_evaluation
        ) as run:
            result = evaluation.run_job(
                self.job,
                self.output_dir,
                "model-b",
                self.workdir,
                self.schema_path,
                threading.Event(),
            )

        self.assertEqual(result, ("evaluation-1", True, "generated"))
        self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
