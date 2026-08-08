"""E5-A pass condition: does externalizing knowledge into the context store
preserve every section byte-for-byte?

This is the formal information-equivalence check from experiment-plan §9.1
("信息集合和哈希一致"). It runs entirely offline over the real knowledge
assembly path — no LLM calls — so it can cover the full fixed question set
cheaply. Whether the model then *chooses* to read the sections is E5-A's smoke
question, and whether that helps accuracy is E5-B's; neither is decided here.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ours.agent.config import get_agent_config
from ours.agent.context_store import ContextStore, verify_information_equivalence
from ours.agent.knowledge import KnowledgeAssembler
from ours.train_few_shot_retriever import TrainFewShotRetriever


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/processed/bird_dev_500.json")
    parser.add_argument("--ids-file", default="data/processed/bird_cleancore_ids.json")
    parser.add_argument("--parent-profile", default="e3-c")
    parser.add_argument("--store-profile", default="e5-a")
    parser.add_argument("--k", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", default="docs/analysis/analysisDetail/e5_a_information_equivalence.json")
    args = parser.parse_args()

    dataset = json.loads((PROJECT_ROOT / args.dataset).read_text(encoding="utf-8"))
    groups = json.loads((PROJECT_ROOT / args.ids_file).read_text(encoding="utf-8"))
    selected = {i for ids in groups.values() for i in ids}
    rows = [row for row in dataset if row["id"] in selected]
    if args.limit:
        rows = rows[: args.limit]

    parent = get_agent_config(args.parent_profile)
    store_config = get_agent_config(args.store_profile)

    # Both profiles must assemble knowledge identically; that is the premise of
    # the comparison, so assert it rather than assume it.
    for field in ("few_shot_mode", "query_pattern_mode", "offline_metadata_mode",
                  "schema_context_mode", "use_db_hints"):
        if getattr(parent, field) != getattr(store_config, field):
            raise SystemExit(
                f"{args.store_profile} differs from {args.parent_profile} in {field}; "
                "information equivalence would be meaningless"
            )

    retriever = TrainFewShotRetriever() if args.k > 0 else None
    assembler = KnowledgeAssembler(
        retriever=retriever,
        k=args.k,
        use_db_hints=parent.use_db_hints,
        query_pattern_mode=parent.query_pattern_mode,
        offline_metadata_mode=parent.offline_metadata_mode,
    )

    per_question = []
    failures = []
    section_presence = Counter()
    for row in rows:
        blocks = assembler.blocks(row["question"], row["db_id"], row.get("evidence", ""))
        # schema_context_mode is offline-retrieval for both profiles, so there is
        # no runtime-full schema block to externalize.
        store = ContextStore(blocks)
        report = verify_information_equivalence(blocks, store)
        for name in store.section_names():
            section_presence[name] += 1
        record = {
            "id": row["id"],
            "db_id": row["db_id"],
            "equivalent": report["equivalent"],
            "section_count": report["store_section_count"],
            "sections": store.section_names(),
            "missing_from_store": report["missing_from_store"],
            "extra_in_store": report["extra_in_store"],
            "content_mismatch": report["content_mismatch"],
            "section_sha256": report["section_sha256"],
        }
        per_question.append(record)
        if not report["equivalent"]:
            failures.append(record)

    payload = {
        "parent_profile": args.parent_profile,
        "store_profile": args.store_profile,
        "question_count": len(per_question),
        "equivalent_count": sum(1 for r in per_question if r["equivalent"]),
        "failure_count": len(failures),
        "passed": not failures,
        "section_presence": dict(section_presence.most_common()),
        "failures": failures,
        "per_question": per_question,
    }
    out = PROJECT_ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"questions            : {payload['question_count']}")
    print(f"information-equivalent: {payload['equivalent_count']}")
    print(f"failures             : {payload['failure_count']}")
    print(f"section presence     : {payload['section_presence']}")
    print(f"PASSED               : {payload['passed']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
