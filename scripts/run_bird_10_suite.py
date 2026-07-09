"""Run the BIRD mini 10-question evaluation suite.

This script overwrites the standard BIRD-10 result files, runs the configured
baselines and DB-RLM variants, then refreshes results/bird_10_evaluation.txt.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "processed" / "bird_mini_dev_questions.json"
DATABASE_DIR = PROJECT_ROOT / "data" / "databases"
RESULTS_DIR = PROJECT_ROOT / "results"
EVALUATION_TABLE = RESULTS_DIR / "bird_10_evaluation.txt"


def run_command(args: list[str]) -> None:
    print("\n" + "=" * 80)
    print(" ".join(args))
    print("=" * 80)
    subprocess.run(args, cwd=PROJECT_ROOT, check=True)


def remove_existing(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()
            print(f"Removed {path.relative_to(PROJECT_ROOT)}")


def build_runs(limit: int, include_workspace: bool) -> list[tuple[str, Path, list[str]]]:
    runs: list[tuple[str, Path, list[str]]] = [
        (
            "baseline_1_direct_llm_schema",
            RESULTS_DIR / "bird_b1_10.json",
            [
                sys.executable,
                "baselines/baseline_1_direct_llm_schema.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--output",
                str(RESULTS_DIR / "bird_b1_10.json"),
            ],
        ),
        (
            "baseline_2_direct_text_to_sql",
            RESULTS_DIR / "bird_b2_10.json",
            [
                sys.executable,
                "baselines/baseline_2_direct_text_to_sql.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--output",
                str(RESULTS_DIR / "bird_b2_10.json"),
            ],
        ),
        (
            "baseline_3_non_recursive_db_agent",
            RESULTS_DIR / "bird_b3_10.json",
            [
                sys.executable,
                "baselines/baseline_3_non_recursive_db_agent.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--output",
                str(RESULTS_DIR / "bird_b3_10.json"),
            ],
        ),
        (
            "bird_ours_basic_10",
            RESULTS_DIR / "bird_ours_basic_10.json",
            [
                sys.executable,
                "scripts/run_ours.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--no-recursion",
                "--prompt-version",
                "basic",
                "--output",
                str(RESULTS_DIR / "bird_ours_basic_10.json"),
            ],
        ),
        (
            "bird_ours_metadata_10",
            RESULTS_DIR / "bird_ours_metadata_10.json",
            [
                sys.executable,
                "scripts/run_ours.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--no-recursion",
                "--use-metadata",
                "--prompt-version",
                "basic",
                "--output",
                str(RESULTS_DIR / "bird_ours_metadata_10.json"),
            ],
        ),
        (
            "bird_ours_metadata_enrichment_10",
            RESULTS_DIR / "bird_ours_metadata_enrichment_10.json",
            [
                sys.executable,
                "scripts/run_ours.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--no-recursion",
                "--use-metadata",
                "--use-enrichment",
                "--prompt-version",
                "basic",
                "--output",
                str(RESULTS_DIR / "bird_ours_metadata_enrichment_10.json"),
            ],
        ),
        (
            "bird_ours_metadata_enrichment_probe_10",
            RESULTS_DIR / "bird_ours_metadata_enrichment_probe_10.json",
            [
                sys.executable,
                "scripts/run_ours.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--no-recursion",
                "--use-metadata",
                "--use-enrichment",
                "--use-probe-queries",
                "--prompt-version",
                "basic",
                "--output",
                str(RESULTS_DIR / "bird_ours_metadata_enrichment_probe_10.json"),
            ],
        ),
    ]

    if include_workspace:
        runs.append(
            (
                "bird_ours_full_workspace_10",
                RESULTS_DIR / "bird_ours_full_workspace_10.json",
                [
                    sys.executable,
                    "scripts/run_ours.py",
                    "--dataset",
                    str(DATASET),
                    "--database-dir",
                    str(DATABASE_DIR),
                    "--limit",
                    str(limit),
                    "--use-metadata",
                    "--use-enrichment",
                    "--use-probe-queries",
                    "--use-workspace",
                    "--prompt-version",
                    "workspace",
                    "--output",
                    str(RESULTS_DIR / "bird_ours_full_workspace_10.json"),
                ],
            )
        )

    return runs


def evaluate(result_paths: list[Path]) -> None:
    args = [
        sys.executable,
        "scripts/evaluate_results.py",
        "--result-files",
        *[str(path) for path in result_paths],
    ]
    print("\n" + "=" * 80)
    print(" ".join(args))
    print("=" * 80)
    completed = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    EVALUATION_TABLE.write_text(completed.stdout, encoding="utf-8")
    print(completed.stdout)
    print(f"Saved evaluation table to {EVALUATION_TABLE.relative_to(PROJECT_ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and evaluate the BIRD-10 suite.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Resume existing result files instead of deleting and overwriting them.",
    )
    parser.add_argument(
        "--skip-workspace",
        action="store_true",
        help="Skip the full workspace variant, which is slower and less stable.",
    )
    parser.add_argument(
        "--only-ours",
        action="store_true",
        help="Skip the three baselines and run only DB-RLM variants.",
    )
    parser.add_argument(
        "--only-baselines",
        action="store_true",
        help="Run only the three baselines and skip DB-RLM variants.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    runs = build_runs(limit=args.limit, include_workspace=not args.skip_workspace)
    if args.only_ours and args.only_baselines:
        raise ValueError("--only-ours and --only-baselines are mutually exclusive")
    if args.only_ours:
        runs = [run for run in runs if run[0].startswith("bird_ours")]
    if args.only_baselines:
        runs = [run for run in runs if not run[0].startswith("bird_ours")]

    result_paths = [path for _, path, _ in runs]
    if not args.keep_existing:
        remove_existing(result_paths)

    for index, (name, _, command) in enumerate(runs, start=1):
        print(f"\n[{index}/{len(runs)}] Running {name}")
        run_command(command)

    evaluate(result_paths)


if __name__ == "__main__":
    main()
