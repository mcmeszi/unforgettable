#!/usr/bin/env python3
"""Run blind generation jobs through one fixed Codex model, resumably."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROMPT = """Izolált vak benchmark-generálás. Minden szükséges adat az alábbi JOB JSON-ban van.
Ne használj toolt, ne olvass fájlt vagy skillt, ne adj státuszt vagy elemzést.
Kövesd a briefet és a contractokat. Ne másolj felismerhető evidence-mondatot.
A végső válasz kizárólag a kész szöveg legyen; ne említs forrást, rendszert,
benchmarkot vagy S-jelölést.

JOB JSON:
{job}
"""

BINDING_SCHEMA = "codex-job-output-binding/v1"


def load_jobs(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def valid_draft(path: Path) -> bool:
    return path.exists() and len(path.read_text(encoding="utf-8-sig").strip()) >= 40


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
    if not valid_draft(output):
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


def run_job(job: dict, output_dir: Path, model: str, workdir: Path) -> tuple[str, bool, str]:
    job_id = str(job["job_id"])
    output = output_dir / f"{job_id}.md"
    if reusable_output(output, job, model):
        return job_id, True, "skipped"
    executable = shutil.which("codex.cmd") or shutil.which("codex")
    if not executable:
        return job_id, False, "codex executable not found"
    command = [
        executable, "exec",
        "-m", model,
        "-c", 'model_reasoning_effort="low"',
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "-s", "read-only",
        "-C", str(workdir),
        "-o", str(output),
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            input=PROMPT.format(job=json.dumps(job, ensure_ascii=False)),
            text=True,
            encoding="utf-8",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        return job_id, False, f"process start failed: {error}"
    if completed.returncode != 0 or not valid_draft(output):
        error = (completed.stderr or "missing or empty draft")[-1000:]
        return job_id, False, error
    try:
        write_binding(output, job, model)
    except OSError as error:
        return job_id, False, f"failed to persist output binding: {error}"
    return job_id, True, "generated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--workers", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs = load_jobs(args.jobs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    with tempfile.TemporaryDirectory(prefix="codex-blind-generation-") as temporary:
        workdir = Path(temporary)
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(run_job, job, args.output_dir, args.model, workdir): job for job in jobs}
            completed_count = 0
            for future in as_completed(futures):
                job_id, success, detail = future.result()
                completed_count += 1
                print(json.dumps({"completed": completed_count, "total": len(jobs), "job_id": job_id, "success": success, "detail": detail}, ensure_ascii=False), flush=True)
                if not success:
                    failures.append({"job_id": job_id, "error": detail})
    summary = {"jobs": len(jobs), "failures": failures, "output_dir": str(args.output_dir), "model": args.model}
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
