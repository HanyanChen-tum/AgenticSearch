"""Build the controlled large-schema benchmark (spec_recursion_at_scale.md).

Merges all 11 BIRD mini-dev databases into one SQLite file (~75 tables), and
optionally adds renamed distractor copies of real tables (~300 tables total).
Questions and gold SQL are unchanged — the correct tables keep their original
names; only the haystack grows.

Outputs (get_db_path-compatible layout):
  data/megadb/merged/merged.sqlite          (~75 tables)
  data/megadb/merged_xl/merged_xl.sqlite    (~300 tables, distractors)
  data/processed/bird_dev_500_merged.json / _merged_xl.json  (db_id remapped)

Usage:
  python scripts/build_megadb.py [--distractors-per-table 3] [--distractor-rows 500]
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_DIR = PROJECT_ROOT / "data/raw/bird/minidev/MINIDEV/dev_databases"
OUT_DIR = PROJECT_ROOT / "data/megadb"
DATASET = PROJECT_ROOT / "data/processed/bird_dev_500.json"

SKIP_TABLES = {"sqlite_sequence"}
DISTRACTOR_SUFFIXES = ["_archive", "_backup", "_staging", "_old", "_eu", "_v2"]


def source_dbs() -> list[Path]:
    dbs = []
    for d in sorted(DB_DIR.iterdir()):
        f = d / f"{d.name}.sqlite"
        if f.exists():
            dbs.append(f)
    return dbs


def merge(out_file: Path) -> list[str]:
    """Copy every table (DDL + data) from all source DBs into out_file."""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if out_file.exists():
        out_file.unlink()
    conn = sqlite3.connect(out_file)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    tables = []
    for src in source_dbs():
        conn.execute("ATTACH DATABASE ? AS src", (str(src),))
        rows = conn.execute(
            "SELECT name, sql FROM src.sqlite_master "
            "WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
        for name, ddl in rows:
            if name in SKIP_TABLES:
                continue
            conn.execute(ddl)  # original DDL preserves columns, PKs, FKs
            conn.execute(f'INSERT INTO "{name}" SELECT * FROM src."{name}"')
            tables.append(name)
        # copy indexes for query speed (ignore failures on odd DDL)
        for (idx_sql,) in conn.execute(
            "SELECT sql FROM src.sqlite_master WHERE type='index' AND sql IS NOT NULL"
        ).fetchall():
            try:
                conn.execute(idx_sql)
            except sqlite3.Error:
                pass
        conn.commit()
        conn.execute("DETACH DATABASE src")
    conn.close()
    return tables


def add_distractors(db_file: Path, per_table: int, max_rows: int, seed: int = 42) -> int:
    """Add renamed, subsampled copies of real tables as distractors."""
    rng = random.Random(seed)
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    base = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
    ).fetchall()
    added = 0
    for name, ddl in base:
        if name in SKIP_TABLES:
            continue
        suffixes = rng.sample(DISTRACTOR_SUFFIXES, min(per_table, len(DISTRACTOR_SUFFIXES)))
        for suf in suffixes:
            new_name = f"{name}{suf}"
            # rename table in DDL (word-boundary, first occurrence after CREATE TABLE)
            new_ddl = re.sub(
                r'(CREATE TABLE\s+)(`|"|\[)?' + re.escape(name) + r'(`|"|\])?',
                lambda m: m.group(1) + f'"{new_name}"',
                ddl, count=1, flags=re.IGNORECASE,
            )
            try:
                conn.execute(new_ddl)
                conn.execute(
                    f'INSERT INTO "{new_name}" SELECT * FROM "{name}" '
                    f'ORDER BY RANDOM() LIMIT {max_rows}'
                )
                added += 1
            except sqlite3.Error:
                pass  # exotic DDL (FK to renamed table etc.) — skip quietly
        conn.commit()
    conn.close()
    return added


def write_question_file(db_id: str, out_path: Path) -> None:
    questions = json.loads(DATASET.read_text())
    for q in questions:
        q["source_db_id"] = q["db_id"]
        q["db_id"] = db_id
    out_path.write_text(json.dumps(questions, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--distractors-per-table", type=int, default=3)
    ap.add_argument("--distractor-rows", type=int, default=500)
    args = ap.parse_args()

    merged = OUT_DIR / "merged" / "merged.sqlite"
    print("Building merged DB (all 11 BIRD databases)...")
    tables = merge(merged)
    print(f"  {merged}: {len(tables)} tables, {merged.stat().st_size/1e9:.2f} GB")

    xl = OUT_DIR / "merged_xl" / "merged_xl.sqlite"
    print("Building XL version (merged + distractors)...")
    xl.parent.mkdir(parents=True, exist_ok=True)
    xl.write_bytes(merged.read_bytes())
    n = add_distractors(xl, args.distractors_per_table, args.distractor_rows)
    conn = sqlite3.connect(xl)
    total = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    conn.close()
    print(f"  {xl}: +{n} distractors → {total} tables, {xl.stat().st_size/1e9:.2f} GB")

    write_question_file("merged", PROJECT_ROOT / "data/processed/bird_dev_500_merged.json")
    write_question_file("merged_xl", PROJECT_ROOT / "data/processed/bird_dev_500_merged_xl.json")
    print("Question files written (same questions/gold, db_id remapped).")


if __name__ == "__main__":
    main()
