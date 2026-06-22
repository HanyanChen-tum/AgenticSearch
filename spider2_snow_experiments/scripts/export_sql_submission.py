"""Export generated SQL JSON results to Spider2-Snow official submission format."""

from __future__ import annotations

import argparse
from pathlib import Path

from spider2_snow_experiments import config
from spider2_snow_experiments.result_utils import extract_sql_from_text, postprocess_sql, read_json
from spider2_snow_experiments.schema import load_schema_tables


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Spider2-Snow SQL submissions.")
    parser.add_argument("--result-json", required=True)
    parser.add_argument("--submission-dir", required=True)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing .sql files in the submission directory.",
    )
    parser.add_argument(
        "--no-postprocess",
        action="store_true",
        help="Disable SQL table-name post-processing before writing .sql files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result_path = Path(args.result_json)
    submission_dir = Path(args.submission_dir).resolve()
    rows = read_json(result_path)
    if not isinstance(rows, list):
        raise ValueError(f"Expected a list of result rows: {result_path}")

    submission_dir.mkdir(parents=True, exist_ok=True)
    if args.overwrite:
        for existing_sql in submission_dir.glob("*.sql"):
            existing_sql.unlink()
    written = 0
    skipped = 0
    for row in rows:
        instance_id = row.get("instance_id")
        sql = (row.get("predicted_sql") or "").strip()
        if not sql and row.get("raw_response"):
            sql = extract_sql_from_text(str(row["raw_response"]))
        if not instance_id or not sql:
            skipped += 1
            continue
        if not args.no_postprocess and row.get("db_id"):
            try:
                schema_tables = load_schema_tables(str(row["db_id"]))
                sql, _ = postprocess_sql(sql, schema_tables)
            except Exception as error:
                print(f"Warning: could not post-process {instance_id}: {error}")
        output_path = submission_dir / f"{instance_id}.sql"
        if output_path.exists() and not args.overwrite:
            skipped += 1
            continue
        output_path.write_text(sql + "\n", encoding="utf-8")
        written += 1

    print(f"Wrote {written} SQL files to {submission_dir}")
    if skipped:
        print(f"Skipped {skipped} rows")
    print(
        "Official evaluation example:\n"
        f"cd {config.SPIDER2_SNOW_DIR / 'evaluation_suite'}\n"
        f"python evaluate.py --mode sql --result_dir {submission_dir}"
    )


if __name__ == "__main__":
    main()
