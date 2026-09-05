#!/usr/bin/env python3
"""Record and summarize Peter's explicit voice feedback without storing draft text."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path


DEFAULT_LEDGER = Path(__file__).resolve().parents[1] / "state" / "voice-feedback.jsonl"


def read_entries(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def normalized_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def record(args: argparse.Namespace) -> int:
    entry = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "genre": args.genre.strip().casefold() or "all",
        "verdict": args.verdict,
        "brief": args.brief.strip(),
        "liked": normalized_list(args.like),
        "disliked": normalized_list(args.dislike),
        "directive": args.directive.strip(),
        "source_families": normalized_list(args.source_family),
    }
    if args.draft:
        entry["draft_sha256"] = hashlib.sha256(args.draft.read_bytes()).hexdigest()
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


def summarize(args: argparse.Namespace) -> int:
    entries = read_entries(args.ledger)
    relevant = [entry for entry in entries if args.genre == "all" or entry.get("genre") in {"all", args.genre}]
    recent = relevant[-max(1, args.limit) :]
    liked = Counter(item for entry in relevant for item in entry.get("liked", []))
    disliked = Counter(item for entry in relevant for item in entry.get("disliked", []))
    directives = [entry.get("directive") for entry in recent if entry.get("directive")]
    print(
        json.dumps(
            {
                "genre": args.genre,
                "entries": len(relevant),
                "liked": liked.most_common(12),
                "disliked": disliked.most_common(12),
                "recent_directives": directives,
                "recent": recent,
                "rule": "Explicit recent genre feedback outranks inferred global preference; never infer authorship from this ledger.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--genre", default="all")
    record_parser.add_argument("--verdict", choices=("approved", "rejected", "mixed"), required=True)
    record_parser.add_argument("--brief", default="")
    record_parser.add_argument("--like", action="append", default=[])
    record_parser.add_argument("--dislike", action="append", default=[])
    record_parser.add_argument("--directive", default="")
    record_parser.add_argument("--source-family", action="append", default=[])
    record_parser.add_argument("--draft", type=Path)
    record_parser.set_defaults(run=record)

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--genre", default="all")
    summary_parser.add_argument("--limit", type=int, default=8)
    summary_parser.set_defaults(run=summarize)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
