"""Execute every located claim's check_sql against its database and report
whether the claim is true or false.

locate_first_wrong_sentence.py's own design principle: a claim that turns out
false means the location is wrong, not that the sentence was interesting. This
script is the verification step that principle depends on -- without running
it, a "located" file is just an unverified LLM guess with a plausible-looking
JSON shape.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.console import force_utf8_console
from scripts.compare_gold_versions import execute


def main() -> None:
    force_utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--located", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    located = json.loads(Path(args.located).read_text(encoding="utf-8"))
    dataset = {r["id"]: r for r in json.loads(Path(args.dataset).read_text(encoding="utf-8"))}

    out = []
    verified = refuted = no_claim = error = 0
    for r in located:
        rec = dict(r)
        sql = r.get("check_sql")
        db_id = dataset.get(r["id"], {}).get("db_id")
        if not sql or not db_id:
            rec["verification"] = "no_claim"
            no_claim += 1
        else:
            result = execute(db_id, sql, 30)
            if result is None:
                rec["verification"] = "execution_error"
                error += 1
            else:
                truthy = bool(result) and any(
                    v not in (None, 0, "0") for row in result for v in row
                )
                rec["check_result"] = result[:5]
                rec["verification"] = "confirmed" if truthy else "refuted"
                if truthy:
                    verified += 1
                else:
                    refuted += 1
        out.append(rec)

    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    n = len(out)
    print(f"{n} located claims checked")
    print(f"  confirmed (location trustworthy): {verified} ({verified/n*100:.0f}%)")
    print(f"  refuted (location is wrong):       {refuted} ({refuted/n*100:.0f}%)")
    print(f"  execution error:                   {error}")
    print(f"  no claim offered:                  {no_claim}")
    if refuted:
        print("\n  refuted ids:", [r["id"] for r in out if r["verification"] == "refuted"])
    print(f"\n-> {args.output}")


if __name__ == "__main__":
    main()
