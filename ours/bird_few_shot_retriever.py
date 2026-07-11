"""In-domain few-shot retriever built from BIRD correct examples.

Uses questions we already answered correctly (from bird_ours_v4_500.json)
as the retrieval pool. Same 11 databases = perfect schema alignment, no bloat.

Key difference from few_shot_retriever.py (Spider-based):
- In-domain: same databases as eval set
- Uses gold_sql (ground truth), not predicted_sql
- Retrieves by db_id first (same DB preferred), then semantic similarity
"""

from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from functools import lru_cache

_POOL_PATH = Path(__file__).resolve().parents[1] / "results/bird_ours_v4_500.json"
_MODEL_NAME = "all-MiniLM-L6-v2"


class BIRDFewShotRetriever:
    """Retrieve similar BIRD examples for a given question.

    Prioritizes examples from the same database, falls back to cross-DB
    semantic similarity. Always uses gold_sql (not predicted) to avoid
    teaching the model our own mistakes.
    """

    def __init__(self, pool_path: Path = _POOL_PATH, model_name: str = _MODEL_NAME):
        from sentence_transformers import SentenceTransformer

        print(f"[bird-few-shot] Loading embedding model {model_name}...")
        self.model = SentenceTransformer(model_name)

        raw = json.loads(Path(pool_path).read_text())
        # Only use correctly answered examples with gold SQL
        self.examples = [
            {
                "question": x["question"],
                "gold_sql": x["gold_sql"],
                "db_id": x["db_id"],
                "difficulty": x.get("difficulty", ""),
                "evidence": x.get("evidence", ""),
            }
            for x in raw
            if x.get("correct") and x.get("gold_sql")
        ]

        print(f"[bird-few-shot] Embedding {len(self.examples)} correct BIRD examples...")
        self.questions = [e["question"] for e in self.examples]
        self.embeddings = self.model.encode(
            self.questions, batch_size=256, show_progress_bar=False, normalize_embeddings=True
        )
        print(f"[bird-few-shot] Ready. Pool: {len(self.examples)} examples across {len(set(e['db_id'] for e in self.examples))} databases.")

    def retrieve(self, question: str, db_id: str = "", k: int = 1) -> list[dict]:
        """Return top-k examples, prioritizing same database.

        Excludes the query question itself (the pool comes from the same dev
        set, so without this the model is shown its own gold SQL — leakage).
        """
        q_emb = self.model.encode([question], normalize_embeddings=True)
        scores = (self.embeddings @ q_emb.T).squeeze()

        q_norm = " ".join(question.lower().split())
        boosted = scores.copy()
        for i, ex in enumerate(self.examples):
            # Self-exclusion: exact text match or near-duplicate embedding
            if scores[i] > 0.98 or " ".join(ex["question"].lower().split()) == q_norm:
                boosted[i] = -1.0
            elif db_id and ex["db_id"] == db_id:
                boosted[i] += 0.3  # strong same-db preference

        top_k = np.argsort(boosted)[::-1][:k]
        return [self.examples[i] for i in top_k if boosted[i] > -1.0]

    def format_examples(self, question: str, db_id: str = "", k: int = 1) -> str:
        """Return formatted examples ready to inject into prompt."""
        examples = self.retrieve(question, db_id=db_id, k=k)
        lines = ["SIMILAR EXAMPLE (use this SQL pattern as reference):"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"\n  Q: {ex['question']}")
            if ex.get("evidence"):
                lines.append(f"  Hint: {ex['evidence']}")
            lines.append(f"  SQL: {ex['gold_sql']}")
        return "\n".join(lines)


@lru_cache(maxsize=1)
def get_bird_retriever() -> BIRDFewShotRetriever:
    """Singleton — loaded once, reused across all questions."""
    return BIRDFewShotRetriever()
