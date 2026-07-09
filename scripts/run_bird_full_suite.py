"""Run the full BIRD Mini-Dev evaluation suite.

This script runs configured DB-RLM ablations over BIRD Mini-Dev SQLite
examples and writes a limit-specific evaluation report.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "processed" / "bird_mini_dev_questions.json"
DATABASE_DIR = PROJECT_ROOT / "data" / "databases"
RESULTS_DIR = PROJECT_ROOT / "results"
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
    suffix = str(limit)
    b2_path = RESULTS_DIR / f"bird_b2_{suffix}.json"
    basic_no_rlm_path = RESULTS_DIR / f"bird_ours_basic_no_rlm_{suffix}.json"
    basic_rlm_path = RESULTS_DIR / f"bird_ours_basic_rlm_{suffix}.json"
    metadata_no_rlm_path = RESULTS_DIR / f"bird_ours_metadata_no_rlm_{suffix}.json"
    metadata_enrichment_no_rlm_path = RESULTS_DIR / f"bird_ours_metadata_enrichment_no_rlm_{suffix}.json"
    probe_no_rlm_path = RESULTS_DIR / f"bird_ours_metadata_enrichment_probe_no_rlm_{suffix}.json"
    probe_rlm_path = RESULTS_DIR / f"bird_ours_metadata_enrichment_probe_rlm_{suffix}.json"
    ensemble_path = RESULTS_DIR / f"bird_ours_candidate_ensemble_{suffix}.json"

    runs: list[tuple[str, Path, list[str]]] = [
        (
            "baseline_1_direct_llm_schema",
            RESULTS_DIR / f"bird_b1_{suffix}.json",
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
                str(RESULTS_DIR / f"bird_b1_{suffix}.json"),
            ],
        ),
        (
            "baseline_2_direct_text_to_sql",
            b2_path,
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
                str(b2_path),
            ],
        ),
        (
            "baseline_3_non_recursive_db_agent",
            RESULTS_DIR / f"bird_b3_{suffix}.json",
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
                str(RESULTS_DIR / f"bird_b3_{suffix}.json"),
            ],
        ),
        (
            f"bird_ours_basic_no_rlm_{suffix}",
            basic_no_rlm_path,
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
                str(basic_no_rlm_path),
            ],
        ),
        (
            f"bird_ours_basic_rlm_{suffix}",
            basic_rlm_path,
            [
                sys.executable,
                "scripts/run_ours.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--use-recursion",
                "--prompt-version",
                "basic",
                "--output",
                str(basic_rlm_path),
            ],
        ),
        (
            f"bird_ours_metadata_no_rlm_{suffix}",
            metadata_no_rlm_path,
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
                str(metadata_no_rlm_path),
            ],
        ),
        (
            f"bird_ours_metadata_enrichment_no_rlm_{suffix}",
            metadata_enrichment_no_rlm_path,
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
                str(metadata_enrichment_no_rlm_path),
            ],
        ),
        (
            f"bird_ours_metadata_enrichment_probe_no_rlm_{suffix}",
            probe_no_rlm_path,
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
                str(probe_no_rlm_path),
            ],
        ),
        (
            f"bird_ours_metadata_enrichment_probe_rlm_{suffix}",
            probe_rlm_path,
            [
                sys.executable,
                "scripts/run_ours.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--use-recursion",
                "--use-metadata",
                "--use-enrichment",
                "--use-probe-queries",
                "--prompt-version",
                "basic",
                "--output",
                str(probe_rlm_path),
            ],
        ),
        (
            f"bird_ours_candidate_ensemble_{suffix}",
            ensemble_path,
            [
                sys.executable,
                "scripts/run_candidate_ensemble.py",
                "--dataset",
                str(DATASET),
                "--database-dir",
                str(DATABASE_DIR),
                "--limit",
                str(limit),
                "--candidate-files",
                str(b2_path),
                str(metadata_enrichment_no_rlm_path),
                str(probe_no_rlm_path),
                "--repair-attempts",
                "1",
                "--output",
                str(ensemble_path),
            ],
        ),
    ]

    if include_workspace:
        runs.append(
            (
                f"bird_ours_full_workspace_{suffix}",
                RESULTS_DIR / f"bird_ours_full_workspace_{suffix}.json",
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
                    str(RESULTS_DIR / f"bird_ours_full_workspace_{suffix}.json"),
                ],
            )
        )

    return runs


def build_paired_comparison(no_rlm_path: Path, rlm_path: Path) -> str:
    no_rlm_rows = json.loads(no_rlm_path.read_text(encoding="utf-8"))
    rlm_rows = json.loads(rlm_path.read_text(encoding="utf-8"))
    no_rlm_by_id = {row["id"]: row for row in no_rlm_rows}
    rlm_by_id = {row["id"]: row for row in rlm_rows}
    common_ids = no_rlm_by_id.keys() & rlm_by_id.keys()

    both_correct = sum(
        no_rlm_by_id[row_id].get("correct") is True
        and rlm_by_id[row_id].get("correct") is True
        for row_id in common_ids
    )
    no_rlm_only = sum(
        no_rlm_by_id[row_id].get("correct") is True
        and rlm_by_id[row_id].get("correct") is not True
        for row_id in common_ids
    )
    rlm_only = sum(
        no_rlm_by_id[row_id].get("correct") is not True
        and rlm_by_id[row_id].get("correct") is True
        for row_id in common_ids
    )
    both_wrong = len(common_ids) - both_correct - no_rlm_only - rlm_only
    delta = rlm_only - no_rlm_only
    delta_accuracy = delta / len(common_ids) if common_ids else 0.0

    return "\n".join(
        [
            "",
            "Paired RLM ablation",
            "-------------------",
            f"paired examples : {len(common_ids)}",
            f"both correct    : {both_correct}",
            f"no-RLM only     : {no_rlm_only}",
            f"RLM only        : {rlm_only}",
            f"both wrong      : {both_wrong}",
            f"RLM net gain    : {delta:+d} examples ({delta_accuracy:+.2%})",
        ]
    )


def evaluate(result_paths: list[Path], limit: int, rlm_ablation_only: bool) -> None:
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
    report = completed.stdout.rstrip()
    if rlm_ablation_only:
        no_rlm_path = next(path for path in result_paths if "_no_rlm_" in path.name)
        rlm_path = next(
            path
            for path in result_paths
            if "_rlm_" in path.name and "_no_rlm_" not in path.name
        )
        report += "\n" + build_paired_comparison(no_rlm_path, rlm_path)

    label = "rlm_ablation" if rlm_ablation_only else "full_evaluation"
    evaluation_table = RESULTS_DIR / f"bird_{label}_{limit}.txt"
    evaluation_table.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"Saved evaluation table to {evaluation_table.relative_to(PROJECT_ROOT)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run and evaluate full BIRD Mini-Dev.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL", "gemini-2.0-flash"),
        help="Model used by every method in this suite.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=float(os.environ.get("TEMPERATURE", "0")),
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=int(os.environ.get("MAX_TOKENS", "1024")),
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Resume existing result files instead of deleting and overwriting them.",
    )
    parser.add_argument(
        "--skip-workspace",
        action="store_true",
        help="Deprecated: workspace is skipped by default unless --include-workspace is set.",
    )
    parser.add_argument(
        "--include-workspace",
        action="store_true",
        help="Also run the slower full workspace ablation.",
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
    parser.add_argument(
        "--only-rlm-ablation",
        action="store_true",
        help=(
            "Run only the strict metadata+enrichment+probe no-RLM/RLM pair. "
            "The recursion switch is the sole configuration difference."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    os.environ["MODEL"] = args.model
    os.environ["TEMPERATURE"] = str(args.temperature)
    os.environ["MAX_TOKENS"] = str(args.max_tokens)
    print(
        f"Fixed suite config: model={args.model}, temperature={args.temperature}, "
        f"max_tokens={args.max_tokens}"
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    runs = build_runs(limit=args.limit, include_workspace=args.include_workspace and not args.skip_workspace)
    selected_modes = sum((args.only_ours, args.only_baselines, args.only_rlm_ablation))
    if selected_modes > 1:
        raise ValueError(
            "--only-ours, --only-baselines, and --only-rlm-ablation are mutually exclusive"
        )
    if args.only_ours:
        runs = [run for run in runs if run[0].startswith("bird_ours")]
    if args.only_baselines:
        runs = [run for run in runs if not run[0].startswith("bird_ours")]
    if args.only_rlm_ablation:
        strict_names = {
            f"bird_ours_metadata_enrichment_probe_no_rlm_{args.limit}",
            f"bird_ours_metadata_enrichment_probe_rlm_{args.limit}",
        }
        runs = [run for run in runs if run[0] in strict_names]
    result_paths = [path for _, path, _ in runs]

    if not args.keep_existing:
        remove_existing(result_paths)

    for index, (name, _, command) in enumerate(runs, start=1):
        print(f"\n[{index}/{len(runs)}] Running {name}")
        run_command(command)

    evaluate(result_paths, limit=args.limit, rlm_ablation_only=args.only_rlm_ablation)


if __name__ == "__main__":
    main()
