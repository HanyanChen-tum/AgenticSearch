"""Drop result records that a harness crash produced, so a resume re-runs them.

A question killed by `UnicodeEncodeError` (see `shared/console.py`) is still a
completed record: empty SQL, `correct: false`. The runner's resume skips
anything already in the results file, so fixing the crash is not enough -- the
bad records have to leave before the question will be attempted again.

Only the results JSON is touched. The transcript JSONL keeps its line: the
runner's resume requires `done_ids` to be a subset of the traced IDs, which
still holds after records are removed, and `trace_io.by_id` keeps the last
record per ID once the question is re-run.

Dry run by default. Pass --apply to write.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from shared.trace_io import write_json

# Crashes in our own code, not model outcomes. MaxIterationsError and the API
# errors are deliberately absent: those are results, however unwelcome.
HARNESS_CRASHES = ("UnicodeEncodeError",)


def purge(results_path: Path, terminations: set[str], apply: bool) -> dict:
    records = json.loads(results_path.read_text(encoding="utf-8"))
    doomed = [r for r in records if r.get("termination") in terminations]
    kept = [r for r in records if r.get("termination") not in terminations]

    summary = {
        "file": str(results_path),
        "before": len(records),
        "purged": len(doomed),
        "after": len(kept),
        "ids": [r["id"] for r in doomed],
        "other_terminations": collections.Counter(
            r["termination"] for r in kept if r.get("termination") != "final"
        ),
    }
    if not doomed or not apply:
        return summary

    # Any purged record that was somehow scored correct would mean the crash was
    # not fatal after all, and dropping it would throw away a real result.
    salvageable = [r["id"] for r in doomed if r.get("correct")]
    if salvageable:
        raise ValueError(
            f"{results_path}: refusing to purge scored-correct records {salvageable}"
        )

    write_json(results_path, kept)
    manifest_path = PROJECT_ROOT / "trace" / results_path.stem / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["completed_questions"] = len(kept)
        manifest["status"] = "running"
        write_json(manifest_path, manifest)
        summary["manifest"] = str(manifest_path)
    return summary


def main() -> None:
    force_utf8_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="+", help="result JSON files to clean")
    parser.add_argument(
        "--termination",
        action="append",
        default=None,
        help=f"termination value to purge (repeatable; default {HARNESS_CRASHES})",
    )
    parser.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = parser.parse_args()

    terminations = set(args.termination or HARNESS_CRASHES)
    total = 0
    for raw in args.results:
        path = Path(raw)
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        summary = purge(path, terminations, args.apply)
        total += summary["purged"]
        verb = "purged" if args.apply else "would purge"
        print(
            f"{path.name}: {summary['before']} -> {summary['after']} "
            f"({verb} {summary['purged']})"
        )
        if summary["ids"]:
            print(f"    {', '.join(summary['ids'])}")
        if summary["other_terminations"]:
            print(f"    left in place: {dict(summary['other_terminations'])}")
    print(f"\n{'purged' if args.apply else 'would purge'} {total} records")
    if not args.apply:
        print("dry run -- pass --apply to write")


if __name__ == "__main__":
    main()
