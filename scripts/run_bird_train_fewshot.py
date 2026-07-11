"""DB-RLM with few-shot retrieval from the BIRD TRAIN split (k=3, gold SQL).

Same agent as run_bird_indomain_fewshot; only the retrieval pool changes:
official train examples instead of our own correctly-answered dev questions.
Teaches gold SQL conventions (IIF yes/no answers, output-column choices,
multi-part SELECTs) without dev-set leakage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from scripts.run_bird_indomain_fewshot import InDomainFewShotDBRLM, run_one
from ours.train_few_shot_retriever import get_train_retriever

BIRD_DB_DIR  = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
BIRD_DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",        default=str(BIRD_DATASET))
    parser.add_argument("--database-dir",   default=str(BIRD_DB_DIR))
    parser.add_argument("--output",         default=str(PROJECT_ROOT / "results/bird_train_fewshot.json"))
    parser.add_argument("--model",          default="azure/seminar-gpt-5.4-mini")
    parser.add_argument("--limit",          type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--k",              type=int, default=3)
    parser.add_argument("--temperature",    type=float, default=0)
    parser.add_argument("--reasoning-effort", default=None)
    args = parser.parse_args()

    questions = json.loads(Path(args.dataset).read_text())
    if args.limit:
        questions = questions[:args.limit]

    api_key = os.environ.get("LLM_API_KEY")
    api_base = os.environ.get("LLM_BASE_URL")

    extra = {}
    if args.reasoning_effort:
        extra["reasoning_effort"] = args.reasoning_effort

    agent = InDomainFewShotDBRLM(
        model=args.model,
        api_key=api_key,
        api_base=api_base,
        max_iterations=args.max_iterations,
        temperature=args.temperature,
        retriever=get_train_retriever(),
        k=args.k,
        **extra,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    results = []
    done_ids = set()
    if output_path.exists():
        results = json.loads(output_path.read_text())
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} already done")

    questions = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(questions)} questions with k={args.k} TRAIN examples")

    for ex in tqdm(questions, desc="BIRD-TrainFewShot"):
        agent._llm_calls = 0
        agent._iterations = 0
        try:
            results.append(run_one(ex, Path(args.database_dir), agent))
        except KeyboardInterrupt:
            print(f"\nInterrupted — {len(results)} saved")
            output_path.write_text(json.dumps(results, indent=2))
            break
        output_path.write_text(json.dumps(results, indent=2))

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")


if __name__ == "__main__":
    main()
