"""Small Spider2-Snow smoke test.

The default test verifies that the dataset, local DDL resources, and external
knowledge files can be loaded. Use --llm to also test the configured LLM
endpoint with a tiny prompt.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from spider2_snow_experiments import config
from spider2_snow_experiments.data import load_examples
from spider2_snow_experiments.llm import chat
from spider2_snow_experiments.schema import build_example_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Spider2-Snow setup.")
    parser.add_argument("--dataset", default=str(config.SPIDER2_SNOW_DATASET))
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--top-k-tables", type=int, default=5)
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--llm-base-url", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = config.get_settings()
    if args.model:
        settings = replace(settings, model=args.model)
    if args.llm_base_url:
        settings = replace(settings, llm_base_url=args.llm_base_url.rstrip("/"))

    examples = load_examples(args.dataset, limit=args.limit)
    print(f"Loaded examples: {len(examples)}")
    for example in examples:
        context = build_example_context(
            example,
            databases_dir=settings.databases_dir,
            documents_dir=settings.documents_dir,
            max_schema_chars=settings.schema_max_chars,
            max_document_chars=settings.document_max_chars,
            top_k_tables=args.top_k_tables,
        )
        print(
            f"- {example.instance_id}: db={example.db_id}, "
            f"tables={len(context.schema_tables)}, "
            f"schema_chars={len(context.schema_text)}, "
            f"doc_chars={len(context.document_text)}"
        )

    if args.llm:
        response = chat(
            [{"role": "user", "content": "Return SELECT 1; and nothing else."}],
            system_instruction="Return only executable SQL.",
            settings=settings,
            max_tokens=32,
        )
        print(f"LLM smoke response: {response.text.strip()}")


if __name__ == "__main__":
    main()
