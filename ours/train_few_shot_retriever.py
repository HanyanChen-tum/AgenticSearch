"""Few-shot retriever over the BIRD TRAIN set (9,428 gold question/SQL pairs).

Unlike bird_few_shot_retriever (pool = dev questions we answered correctly,
which excludes exactly the gold conventions the model gets wrong), this pool
is the official train split: no dev leakage, and it covers gold SQL idioms
like IIF(cond,'YES','NO') answers, id-vs-name output columns, and multi-part
SELECT lists. Train databases differ from dev, so retrieval is pure semantic
similarity — the examples teach conventions, not schemas.
"""

from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_POOL_PATH = _PROJECT_ROOT / "data/train_pool.json"
_MODEL_NAME = "all-MiniLM-L6-v2"


def _model_config_dict(model) -> dict:
    """Return a stable, JSON-serializable config across ST releases."""
    get_config_dict = getattr(model, "get_config_dict", None)
    if callable(get_config_dict):
        return get_config_dict()

    config = getattr(model, "config", {})
    to_dict = getattr(config, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(config, dict):
        return config
    return vars(config) if hasattr(config, "__dict__") else {"config": str(config)}


def _load_examples(pool_path: Path) -> list[dict]:
    pool_path = Path(pool_path)
    if not pool_path.is_file():
        raise FileNotFoundError(
            f"BIRD train pool not found: {pool_path}. "
            "Expected the processed 9,428-example pool at data/train_pool.json."
        )

    raw = json.loads(pool_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"BIRD train pool must be a JSON list: {pool_path}")

    examples = [
        {
            "train_index": index,
            "example_id": f"train-{index}",
            "question": item["question"],
            "gold_sql": item["SQL"],
            "db_id": item["db_id"],
            "evidence": item.get("evidence", ""),
        }
        for index, item in enumerate(raw)
        if item.get("SQL")
    ]
    if not examples:
        raise ValueError(f"BIRD train pool contains no usable SQL examples: {pool_path}")
    return examples


def get_train_retriever_manifest(
    pool_path: Path = _POOL_PATH,
    model_name: str = _MODEL_NAME,
) -> dict:
    """Describe the retrieval pool without loading the embedding model."""
    resolved = Path(pool_path).resolve()
    examples = _load_examples(resolved)
    return {
        "class": "TrainFewShotRetriever",
        "source_split": "bird-train",
        "pool_path": str(resolved),
        "pool_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "example_count": len(examples),
        "embedding_model": model_name,
        "runtime_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


class TrainFewShotRetriever:
    def __init__(self, pool_path: Path = _POOL_PATH, model_name: str = _MODEL_NAME):
        self.pool_path = Path(pool_path).resolve()
        self.model_name = model_name
        self.pool_sha256 = hashlib.sha256(self.pool_path.read_bytes()).hexdigest()
        self.examples = _load_examples(self.pool_path)

        from sentence_transformers import SentenceTransformer

        print(f"[train-few-shot] Loading embedding model {model_name}...")
        self.model = SentenceTransformer(model_name)
        config = _model_config_dict(self.model)
        self.model_config_sha256 = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        print(f"[train-few-shot] Embedding {len(self.examples)} train examples...")
        self.embeddings = self.model.encode(
            [e["question"] for e in self.examples],
            batch_size=256, show_progress_bar=False, normalize_embeddings=True,
        )
        print(f"[train-few-shot] Ready.")

    def manifest(self) -> dict:
        return {
            "class": type(self).__name__,
            "source_split": "bird-train",
            "pool_path": str(self.pool_path),
            "pool_sha256": self.pool_sha256,
            "example_count": len(self.examples),
            "embedding_model": self.model_name,
            "embedding_model_config_sha256": self.model_config_sha256,
            "runtime_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        }

    def retrieve(self, question: str, db_id: str = "", k: int = 3) -> list[dict]:
        q_emb = self.model.encode([question], normalize_embeddings=True)
        scores = (self.embeddings @ q_emb.T).squeeze()
        indices = np.arange(len(scores))
        top_k = np.lexsort((indices, -scores))[:k]
        return [
            {
                **self.examples[int(index)],
                "retrieval_rank": rank,
                "similarity_score": round(float(scores[int(index)]), 8),
            }
            for rank, index in enumerate(top_k, 1)
        ]

    def selection_diagnostics(self, question: str, db_id: str = "", k: int = 3) -> dict:
        selected = self.retrieve(question, db_id=db_id, k=k)
        return {
            "mode": "train-question-embedding-retrieval",
            "requested_k": k,
            "selected_example_ids": [item["example_id"] for item in selected],
            "selected_examples": [
                {
                    "example_id": item["example_id"],
                    "train_index": item["train_index"],
                    "rank": item["retrieval_rank"],
                    "similarity_score": item["similarity_score"],
                    "db_id": item["db_id"],
                    "question": item["question"],
                }
                for item in selected
            ],
        }

    def format_examples(self, question: str, db_id: str = "", k: int = 3) -> str:
        examples = self.retrieve(question, db_id=db_id, k=k)
        lines = ["SIMILAR SOLVED EXAMPLES (different databases — copy the SQL *style* and output-column conventions, not the table names):"]
        for ex in examples:
            lines.append(f"\n  Q: {ex['question']}")
            if ex.get("evidence"):
                lines.append(f"  Hint: {ex['evidence']}")
            lines.append(f"  SQL: {ex['gold_sql']}")
        return "\n".join(lines)


@lru_cache(maxsize=1)
def get_train_retriever() -> TrainFewShotRetriever:
    return TrainFewShotRetriever()
