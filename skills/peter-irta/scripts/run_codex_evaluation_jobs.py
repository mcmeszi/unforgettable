#!/usr/bin/env python3
"""Run independent blind evaluation jobs through one fixed Codex model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROMPT = """Izolált vak szövegértékelés. Minden szükséges adat a JOB JSON-ban van.
Ne használj toolt, ne olvass fájlt vagy skillt. A megadott bírói fókusz szerint
értékelj, de minden dimenziót pontozz. A műfaji hard guard hibát ne átlagold el.
Ne próbáld kitalálni a jelöltek mögötti rendszert. Kizárólag a kért JSON-t add.

JOB JSON:
{job}
"""

BINDING_SCHEMA = "codex-job-output-binding/v1"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["job_id", "scores", "winner", "decisive_reason", "hard_guard_failures"],
    "properties": {
        "job_id": {"type": "string"},
        "scores": {
            "type": "object",
            "additionalProperties": False,
            "required": ["candidate_1", "candidate_2"],
            "properties": {
                name: {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["brief_fidelity", "genre_naturalness", "author_style_match", "originality_anti_caricature"],
                    "properties": {dimension: {"type": "number", "minimum": 0, "maximum": 2} for dimension in ("brief_fidelity", "genre_naturalness", "author_style_match", "originality_anti_caricature")},
                }
                for name in ("candidate_1", "candidate_2")
            },
        },
        "winner": {"type": "string", "enum": ["candidate_1", "candidate_2", "tie"]},
        "decisive_reason": {"type": "string"},
        "hard_guard_failures": {
            "type": "object",
            "additionalProperties": False,
            "required": ["candidate_1", "candidate_2"],
            "properties": {name: {"type": "array", "items": {"type": "string"}} for name in ("candidate_1", "candidate_2")},
        },
    },
}


def valid(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data.get("winner") in {"candidate_1", "candidate_2", "tie"}
    except (OSError, json.JSONDecodeError):
        return False


def canonical_job_model_hash(job: dict, model: str) -> str:
    canonical = json.dumps(
        {"job": job, "model": model},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def binding_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.meta.json")


def reusable_output(output: Path, job: dict, model: str) -> bool:
    if not valid(output):
        return False
    try:
        binding = json.loads(binding_path(output).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        binding.get("schema") == BINDING_SCHEMA
        and binding.get("canonical_job_model_sha256") == canonical_job_model_hash(job, model)
        and binding.get("output_sha256") == hashlib.sha256(output.read_bytes()).hexdigest()
    )


def write_binding(output: Path, job: dict, model: str) -> None:
    binding = {
        "schema": BINDING_SCHEMA,
        "job_id": str(job["job_id"]),
        "model": model,
        "canonical_job_model_sha256": canonical_job_model_hash(job, model),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    binding_path(output).write_text(
        json.dumps(binding, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_job(job: dict, output_dir: Path, model: str, workdir: Path, schema_path: Path, stop_event: threading.Event) -> tuple[str, bool, str]:
    job_id = str(job["job_id"])
    output = output_dir / f"{job_id}.json"
    if reusable_output(output, job, model):
        return job_id, True, "skipped"
    if stop_event.is_set():
        return job_id, False, "batch-stopped-after-credit-exhaustion"
    executable = shutil.which("codex.cmd") or shutil.which("codex")
    if not executable:
        return job_id, False, "codex executable not found"
    command = [executable, "exec", "-m", model, "-c", 'model_reasoning_effort="low"', "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "-s", "read-only", "-C", str(workdir), "--output-schema", str(schema_path), "-o", str(output), "-"]
    try:
        completed = subprocess.run(command, input=PROMPT.format(job=json.dumps(job, ensure_ascii=False)), text=True, encoding="utf-8", stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError as error:
        return job_id, False, f"process start failed: {error}"
    if completed.returncode != 0 or not valid(output):
        detail = (completed.stderr or "invalid judgment")[-1000:]
        if "out of credits" in detail.casefold():
            stop_event.set()
        return job_id, False, detail
    try:
        write_binding(output, job, model)
    except OSError as error:
        return job_id, False, f"failed to persist output binding: {error}"
    return job_id, True, "generated"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    jobs = [json.loads(line) for line in args.jobs.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    stop_event = threading.Event()
    with tempfile.TemporaryDirectory(prefix="codex-blind-evaluation-") as temporary:
        workdir = Path(temporary)
        schema_path = workdir / "judgment-schema.json"
        schema_path.write_text(json.dumps(SCHEMA), encoding="utf-8")
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = [executor.submit(run_job, job, args.output_dir, args.model, workdir, schema_path, stop_event) for job in jobs]
            for index, future in enumerate(as_completed(futures), start=1):
                job_id, success, detail = future.result()
                print(json.dumps({"completed": index, "total": len(jobs), "job_id": job_id, "success": success, "detail": detail}, ensure_ascii=False), flush=True)
                if not success:
                    failures.append({"job_id": job_id, "error": detail})
    print(json.dumps({"jobs": len(jobs), "failures": failures, "model": args.model}, ensure_ascii=False), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
