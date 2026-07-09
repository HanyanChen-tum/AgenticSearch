"""Run focused bounded-schema no-RLM/RLM pilot experiments."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "data" / "processed" / "bird_mini_dev_questions.json"
DATABASE_DIR = PROJECT_ROOT / "data" / "databases"
RESULTS_DIR = PROJECT_ROOT / "results"


def run(command: list[str]) -> None:
    print("\n" + "=" * 80)
    print(" ".join(command))
    print("=" * 80)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def result_path(limit: int, top_k: int, depth: int) -> Path:
    mode = "no_rlm" if depth == 0 else f"rlm_depth{depth}"
    return RESULTS_DIR / (
        f"bird_schema_memory_top{top_k}_{mode}_{limit}.json"
    )


def build_command(
    *,
    limit: int,
    top_k: int,
    depth: int,
    model: str,
    max_iterations: int,
) -> tuple[Path, list[str]]:
    output = result_path(limit, top_k, depth)
    command = [
        sys.executable,
        "scripts/run_ours.py",
        "--dataset",
        str(DATASET),
        "--database-dir",
        str(DATABASE_DIR),
        "--limit",
        str(limit),
        "--model",
        model,
        "--max-iterations",
        str(max_iterations),
        "--max-depth",
        str(depth),
        "--use-schema-memory",
        "--initial-top-k",
        str(top_k),
        "--prompt-version",
        "schema",
        "--output",
        str(output),
    ]
    command.append("--no-recursion" if depth == 0 else "--use-recursion")
    return output, command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded-schema RLM pilot comparisons."
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--top-k", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--depths", type=int, nargs="+", default=[0, 1, 2])
    parser.add_argument(
        "--model",
        default=os.environ.get("MODEL", "gemini-2.0-flash"),
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
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Resume only when the result manifest fingerprint matches.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise ValueError("--limit must be at least 1")
    if any(value < 1 for value in args.top_k):
        raise ValueError("--top-k values must be at least 1")
    if any(value < 0 for value in args.depths):
        raise ValueError("--depths values must be non-negative")

    os.environ["MODEL"] = args.model
    os.environ["TEMPERATURE"] = str(args.temperature)
    os.environ["MAX_TOKENS"] = str(args.max_tokens)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for top_k in args.top_k:
        for depth in args.depths:
            output, command = build_command(
                limit=args.limit,
                top_k=top_k,
                depth=depth,
                model=args.model,
                max_iterations=args.max_iterations,
            )
            paths.append(output)
            if output.exists() and not args.keep_existing:
                raise FileExistsError(
                    f"Refusing to overwrite existing result: {output}. "
                    "Choose another configuration/output or use --keep-existing "
                    "for a manifest-validated resume."
                )
            run(command)

    run(
        [
            sys.executable,
            "scripts/evaluate_results.py",
            "--result-files",
            *[str(path) for path in paths],
            "--output",
            str(RESULTS_DIR / f"bird_schema_memory_pilot_{args.limit}_summary.json"),
        ]
    )


if __name__ == "__main__":
    main()
