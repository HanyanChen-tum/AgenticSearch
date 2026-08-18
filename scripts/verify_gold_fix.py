"""Execute a corrected gold SQL and ask: would the model's answer now be judged correct?

Three outcomes per question:
  PASS  修正gold后模型判对  -> gold 判定成立，且该题可修
  FAIL  修正gold后模型仍错  -> 责任判偏了（gold虽有缺陷，但不是模型失分的原因）
  ERR   修正gold本身跑不通
"""
import json, sqlite3, glob, sys
from pathlib import Path

ROOT = Path(r"c:\Users\Irene\AgenticSearch")
sys.path.insert(0, str(ROOT))
from shared.evaluator import is_correct

rows = {r["id"]: r for r in json.loads((ROOT / "results/e3_c_conv_rules_dev500_run1.json").read_text(encoding="utf-8"))}
orig = {}
with (ROOT / "trace/e3_c_conv_rules_dev500_run1/transcripts.jsonl").open(encoding="utf-8") as h:
    for line in h:
        rec = json.loads(line)
        tr = rec.get("_trace") or rec
        rw = tr.get("sql_convention_rewrite") or {}
        if rw.get("changed") and rw.get("original_sql"):
            orig[rec["id"]] = rw["original_sql"]


def run(db_id, sql):
    p = glob.glob(rf"{ROOT}\data\raw\bird\**\{db_id}\{db_id}.sqlite", recursive=True)[0]
    con = sqlite3.connect(p)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        return [list(x) for x in con.execute(sql).fetchall()], None
    except Exception as e:
        return None, str(e)
    finally:
        con.close()


def verify(fixes: dict) -> list:
    out = []
    for qid, fix in fixes.items():
        r = rows[qid]
        if fix is None:                      # 判定为不可修
            out.append((qid, "UNFIXABLE", "", ""))
            continue
        newgold, err = run(r["db_id"], fix)
        if err:
            out.append((qid, "ERR", err[:70], ""))
            continue
        # 模型侧：改写前原始SQL优先（harness改写不该算模型的账）
        msql = orig.get(qid, r.get("predicted_sql"))
        mans, merr = run(r["db_id"], msql)
        if merr:
            out.append((qid, "MODEL_ERR", merr[:70], ""))
            continue
        ok = is_correct(mans, newgold)
        out.append((qid, "PASS" if ok else "FAIL",
                    f"newgold={len(newgold)}行", f"model={len(mans)}行"))
    return out


if __name__ == "__main__":
    fixes = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    res = verify(fixes)
    for qid, st, a, b in res:
        print(f"{qid:<12}{st:<11}{a:<28}{b}")
    from collections import Counter
    print("\n", dict(Counter(s for _, s, _, _ in res)))
