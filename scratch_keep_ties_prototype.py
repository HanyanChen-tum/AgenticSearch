# -*- coding: utf-8 -*-
"""Rewrite ORDER BY <x> LIMIT 1 into a keep-all-ties form, with the two guards
the first version lacked: resolve a projection alias used as the sort key, and
fall back to the original query when the extremum is NULL (all-NULL keys make
`x = (SELECT MAX(x))` match nothing, while LIMIT 1 still returns a row)."""
import sqlglot
from sqlglot import exp

def build(pred: str):
    t = sqlglot.parse_one(pred, dialect="sqlite")
    order = t.args.get("order")
    if not order or len(order.expressions) != 1:
        return None, "ORDER BY 非单键"
    o = order.expressions[0]
    key = o.this
    agg = "MAX" if o.args.get("desc") else "MIN"

    # --- guard 1: the sort key may be a projection alias, not a real column ---
    if isinstance(key, exp.Column) and not key.table:
        name = key.name
        for p in t.args.get("expressions", []):
            if isinstance(p, exp.Alias) and p.alias == name:
                key = p.this.copy()
                break

    grouped = t.args.get("group") is not None
    is_agg = bool(list(key.find_all(exp.AggFunc)))
    inner = t.copy(); inner.set("order", None); inner.set("limit", None)
    inner.set("expressions", [exp.alias_(key.copy(), "k")])
    cond = f"({key.sql(dialect='sqlite')}) = (SELECT {agg}(k) FROM ({inner.sql(dialect='sqlite')}))"
    out = t.copy(); out.set("limit", None); out.set("order", None)
    out = out.having(cond) if (grouped or is_agg) else out.where(cond)
    return out.sql(dialect="sqlite"), None
