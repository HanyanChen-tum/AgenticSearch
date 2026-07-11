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
from functools import lru_cache
from pathlib import Path

import numpy as np

_POOL_PATH = Path(__file__).resolve().parents[1] / "data/raw/bird/train.json"
_MODEL_NAME = "all-MiniLM-L6-v2"


class TrainFewShotRetriever:
    def __init__(self, pool_path: Path = _POOL_PATH, model_name: str = _MODEL_NAME):
        from sentence_transformers import SentenceTransformer

        print(f"[train-few-shot] Loading embedding model {model_name}...")
        self.model = SentenceTransformer(model_name)

        raw = json.loads(Path(pool_path).read_text())
        self.examples = [
            {"question": x["question"], "gold_sql": x["SQL"],
             "db_id": x["db_id"], "evidence": x.get("evidence", "")}
            for x in raw if x.get("SQL")
        ]
        print(f"[train-few-shot] Embedding {len(self.examples)} train examples...")
        self.embeddings = self.model.encode(
            [e["question"] for e in self.examples],
            batch_size=256, show_progress_bar=False, normalize_embeddings=True,
        )
        print(f"[train-few-shot] Ready.")

    def retrieve(self, question: str, db_id: str = "", k: int = 3) -> list[dict]:
        q_emb = self.model.encode([question], normalize_embeddings=True)
        scores = (self.embeddings @ q_emb.T).squeeze()
        top_k = np.argsort(scores)[::-1][:k]
        return [self.examples[i] for i in top_k]

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
