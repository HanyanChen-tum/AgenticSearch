"""Baseline 2 on BIRD 500 — LLM + schema + table/column selection, azure model.

Selects top-k relevant tables/columns by keyword overlap before generating SQL.
No exploration, no self-correction, no retries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import sqlite3
import time
from pathlib import Path

import litellm
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from shared.evaluator import is_correct
from shared.sql_executor import execute_sql

BIRD_DB_DIR  = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
BIRD_DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"

_PROMPT = """\
You are an expert Text-to-SQL assistant. Given a database schema and a question, write a single SQLite SQL query.

Relevant schema (pre-filtered):
{schema}
{evidence_block}
Question: {question}

Return ONLY the SQL query, no explanation, no markdown."""

STOPWORDS = {"a","an","and","are","as","by","for","from","in","is","of","on","or","the","to","with",
             "what","which","how","who","when","where","list","find","give","show","select","count","name"}


def get_db_path(db_id: str) -> Path:
    p = BIRD_DB_DIR / db_id / f"{db_id}.sqlite"
    return p if p.exists() else BIRD_DB_DIR / db_id / f"{db_id}.db"


def get_full_schema(db_path: Path) -> dict:
    """Returns {table: {cols: [...], fks: [...]}}"""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    schema = {}
    with sqlite3.connect(uri, uri=True) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        for table in tables:
            cols = [(c[1], c[2]) for c in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            fks  = [(fk[3], fk[2], fk[4]) for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()]
            schema[table] = {"cols": cols, "fks": fks}
    return schema


def select_tables(schema: dict, question: str, evidence: str, top_k: int = 5) -> list[str]:
    """Select top-k tables by keyword overlap with question+evidence."""
    tokens = set(re.findall(r"\b[a-z0-9_]{2,}\b", (question + " " + evidence).lower())) - STOPWORDS
    scored = []
    for table, info in schema.items():
        col_names = {c[0].lower() for c in info["cols"]}
        table_tokens = {table.lower()} | col_names
        score = len(tokens & table_tokens)
        scored.append((score, table))
    scored.sort(reverse=True)
    selected = [t for _, t in scored[:top_k]]
    # Always include tables referenced by foreign keys of selected tables
    extra = set()
    for t in selected:
        for src_col, ref_table, ref_col in schema[t]["fks"]:
            if ref_table in schema:
                extra.add(ref_table)
    return list(dict.fromkeys(selected + list(extra)))


def format_schema(schema: dict, tables: list[str]) -> str:
    lines = []
    for table in tables:
        info = schema[table]
        col_str = ", ".join(f"{c[0]} {c[1]}" for c in info["cols"])
        lines.append(f"CREATE TABLE {table} ({col_str})")
        for src, ref_t, ref_c in info["fks"]:
            lines.append(f"  -- FK: {table}.{src} -> {ref_t}.{ref_c}")
    return "\n".join(lines)


def clean_sql(text: str) -> str:
    text = re.sub(r"```sql\s*", "", text.strip())
    text = re.sub(r"```\s*", "", text)
    return text.strip().rstrip(";")


def run_one(ex: dict, model: str, api_key: str, api_base: str, top_k: int = 5) -> dict:
    db_path = get_db_path(ex["db_id"])
    started = time.perf_counter()
    predicted_sql = ""
    error_msg = None

    try:
        full_schema = get_full_schema(db_path)
        evidence = ex.get("evidence", "").strip()
        selected_tables = select_tables(full_schema, ex["question"], evidence, top_k)
        filtered_schema = format_schema(full_schema, selected_tables)
        evidence_block = f"\nHint: {evidence}\n" if evidence else ""
        prompt = _PROMPT.format(schema=filtered_schema, evidence_block=evidence_block, question=ex["question"])
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key,
            api_base=api_base,
            temperature=1,
            timeout=60,
        )
        predicted_sql = clean_sql(resp.choices[0].message.content)
    except Exception as e:
        error_msg = str(e)

    predicted_exec = (
        execute_sql(db_path, predicted_sql, read_only=True)
        if predicted_sql else {"answer": None, "error": error_msg or "No SQL"}
    )
    gold_exec = execute_sql(db_path, ex["gold_sql"], read_only=True)

    return {
        "id": ex["id"],
        "method": "bird_baseline_2_azure",
        "db_id": ex["db_id"],
        "question": ex["question"],
        "difficulty": ex.get("difficulty", "unknown"),
        "predicted_sql": predicted_sql,
        "predicted_answer": predicted_exec.get("answer"),
        "gold_sql": ex["gold_sql"],
        "gold_answer": gold_exec.get("answer"),
        "correct": (
            predicted_exec.get("error") is None
            and gold_exec.get("error") is None
            and is_correct(predicted_exec.get("answer"), gold_exec.get("answer"))
        ),
        "error": predicted_exec.get("error") or gold_exec.get("error") or error_msg,
        "latency_seconds": round(time.perf_counter() - started, 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset",  default=str(BIRD_DATASET))
    parser.add_argument("--output",   default=str(PROJECT_ROOT / "results/bird_b2_azure_500.json"))
    parser.add_argument("--model",    default="azure/seminar-gpt-5.4-mini")
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--limit",    type=int, default=None)
    parser.add_argument("--top-k",    type=int, default=5)
    args = parser.parse_args()

    api_key  = os.environ.get("LLM_API_KEY")
    api_base = args.api_base or os.environ.get("LLM_BASE_URL")

    questions = json.loads(Path(args.dataset).read_text())
    if args.limit:
        questions = questions[:args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    results, done_ids = [], set()
    if output_path.exists():
        results = json.loads(output_path.read_text())
        done_ids = {r["id"] for r in results}
        print(f"Resuming — {len(done_ids)} done")

    questions = [q for q in questions if q["id"] not in done_ids]
    print(f"Running {len(questions)} questions — Baseline 2 (table selection, no RLM loop)")

    for ex in tqdm(questions, desc="B2-Azure"):
        try:
            results.append(run_one(ex, args.model, api_key, api_base, args.top_k))
        except KeyboardInterrupt:
            output_path.write_text(json.dumps(results, indent=2))
            break
        output_path.write_text(json.dumps(results, indent=2))

    total, correct = len(results), sum(1 for r in results if r["correct"])
    print(f"\nAccuracy: {correct}/{total} = {correct/total:.2%}")
    by_diff = {}
    for r in results:
        by_diff.setdefault(r.get("difficulty", "unknown"), []).append(r["correct"])
    for d, vals in sorted(by_diff.items()):
        print(f"  {d}: {sum(vals)}/{len(vals)} = {sum(vals)/len(vals):.2%}")


if __name__ == "__main__":
    main()
