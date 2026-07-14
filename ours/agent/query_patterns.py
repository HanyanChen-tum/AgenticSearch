"""Train-only structural SQL patterns for the E3-A offline ablation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_POOL_PATH = _PROJECT_ROOT / "data" / "train_pool.json"
PATTERN_LIBRARY_VERSION = "train-static-v1"


@dataclass(frozen=True)
class PatternSpec:
    key: str
    title: str
    instruction: str
    required_regexes: tuple[str, ...]


_PATTERN_SPECS = (
    PatternSpec(
        key="aggregation_grain",
        title="Aggregate at the requested entity grain",
        instruction=(
            "For per-entity totals, averages, minima, or maxima, aggregate at the "
            "entity level first, then rank or limit the aggregated result. Do not "
            "rank individual detail rows when the question asks about an entity total."
        ),
        required_regexes=(r"\b(sum|avg|count|min|max)\s*\(", r"\bgroup\s+by\b"),
    ),
    PatternSpec(
        key="filtered_aggregation",
        title="Apply filters before aggregate comparison",
        instruction=(
            "Keep the requested filter scope explicit before calculating an aggregate; "
            "check that the numerator, denominator, and grouping use the same intended population."
        ),
        required_regexes=(r"\b(sum|avg|count|min|max)\s*\(", r"\bwhere\b"),
    ),
    PatternSpec(
        key="top_k",
        title="Top or bottom result",
        instruction=(
            "For highest, lowest, earliest, latest, or top-k questions, verify the "
            "ORDER BY direction and apply LIMIT only after the requested grouping or filtering."
        ),
        required_regexes=(r"\border\s+by\b", r"\blimit\b"),
    ),
    PatternSpec(
        key="output_contract",
        title="Requested output columns",
        instruction=(
            "Return every requested field and only those fields, in the requested order. "
            "A multi-part question can require multiple SELECT expressions."
        ),
        required_regexes=(r"\bselect\b", r","),
    ),
    PatternSpec(
        key="conditional_answer",
        title="Conditional scalar answer",
        instruction=(
            "For a literal yes/no question, return one conditional scalar value. "
            "For a request for rows or values, return those rows or values instead of a yes/no surrogate."
        ),
        required_regexes=(r"\b(iif|case)\b",),
    ),
    PatternSpec(
        key="distinct_list",
        title="List without duplicates",
        instruction=(
            "When a question asks for a list of entities across a one-to-many join, "
            "consider whether DISTINCT is required to preserve the requested output contract."
        ),
        required_regexes=(r"\bdistinct\b",),
    ),
    PatternSpec(
        key="join_path",
        title="Join path",
        instruction=(
            "When a question spans tables, verify each JOIN condition and select output "
            "columns from the table that owns the requested attribute."
        ),
        required_regexes=(r"\bjoin\b",),
    ),
    PatternSpec(
        key="window_rank",
        title="Explicit ranking",
        instruction=(
            "If the question asks for a rank number rather than sorted rows alone, "
            "use a window ranking expression and include the ranked metric when requested."
        ),
        required_regexes=(r"\bover\s*\(",),
    ),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TrainQueryPatternLibrary:
    """Summarize SQL structures from the official train pool without examples."""

    def __init__(self, pool_path: Path = _DEFAULT_POOL_PATH) -> None:
        self.pool_path = Path(pool_path).resolve()
        if not self.pool_path.is_file():
            raise FileNotFoundError(
                f"BIRD train pool not found: {self.pool_path}. "
                "Expected data/train_pool.json for E3-A."
            )
        raw = json.loads(self.pool_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"BIRD train pool must be a JSON list: {self.pool_path}")
        self.example_count = sum(
            1 for item in raw if isinstance(item, dict) and isinstance(item.get("SQL"), str)
        )
        if not self.example_count:
            raise ValueError(f"BIRD train pool contains no SQL examples: {self.pool_path}")
        self.pool_sha256 = _sha256(self.pool_path)
        sqls = [str(item["SQL"]).casefold() for item in raw if item.get("SQL")]
        self.pattern_support = {
            spec.key: sum(
                all(re.search(pattern, sql, flags=re.DOTALL) for pattern in spec.required_regexes)
                for sql in sqls
            )
            for spec in _PATTERN_SPECS
        }

    def render(self) -> str:
        active = [
            spec for spec in _PATTERN_SPECS
            if self.pattern_support[spec.key] > 0
        ]
        lines = [
            "",
            "TRAIN-ONLY SQL PATTERN LIBRARY:",
            "Use these structural patterns as checks. They contain no evaluation schemas, values, or answers.",
        ]
        for spec in active:
            lines.append(f"- {spec.title}: {spec.instruction}")
        return "\n".join(lines) + "\n"

    def manifest(self) -> dict[str, Any]:
        payload = {
            "version": PATTERN_LIBRARY_VERSION,
            "source_split": "bird-train",
            "pool_path": str(self.pool_path),
            "pool_sha256": self.pool_sha256,
            "example_count": self.example_count,
            "pattern_support": self.pattern_support,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return {
            **payload,
            "artifact_sha256": hashlib.sha256(encoded).hexdigest(),
        }


def get_train_query_patterns() -> TrainQueryPatternLibrary:
    return TrainQueryPatternLibrary()


def get_train_query_pattern_manifest() -> dict[str, Any]:
    """Describe the exact train-only pattern artifact without rendering a prompt."""
    return get_train_query_patterns().manifest()
