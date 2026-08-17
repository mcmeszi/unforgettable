#!/usr/bin/env python3
"""Write the public human blind-test pack and its private answer key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from human_blind_test import build_pack


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jobs(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        return list(data.get("jobs") or data) if isinstance(data, dict) else list(data)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--drafts-dir", type=Path, required=True)
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"refusing non-empty output directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    public, private, manifest = build_pack(
        load_json(args.results), load_jobs(args.jobs), args.drafts_dir, load_json(args.blind_key), args.seed
    )
    write_json(args.output_dir / "public-test.json", public)
    write_json(args.output_dir / "private-human-key.json", private)
    write_json(args.output_dir / "human-test-manifest.json", manifest)
    print(json.dumps({"items": len(public["items"]), "output_dir": str(args.output_dir), "public_sha256": manifest["public_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
