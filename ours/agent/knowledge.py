"""Prompt knowledge assembly with explicit provenance controls."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ours.db_hints import get_db_hint


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class KnowledgeAssembler:
    def __init__(
        self,
        *,
        retriever: Any = None,
        k: int = 0,
        use_db_hints: bool = False,
        query_pattern_mode: str = "none",
        offline_metadata_mode: str = "none",
    ) -> None:
        self.retriever = retriever
        self.k = k
        self.use_db_hints = use_db_hints
        self.query_pattern_mode = query_pattern_mode
        self.offline_metadata_mode = offline_metadata_mode
        self.offline_metadata = None
        if offline_metadata_mode in {"e3-c-metadata-v1", "e3-c-metadata-v2", "e3-f-schema-v3", "e3-f-schema-v4"}:
            from .offline_metadata import get_offline_metadata

            version = (
                "e3-c-metadata-v2"
                if offline_metadata_mode == "e3-c-metadata-v1"
                else offline_metadata_mode
            )
            self.offline_metadata = get_offline_metadata(version)
        elif offline_metadata_mode != "none":
            raise ValueError(f"Unknown offline metadata mode: {offline_metadata_mode!r}")
        if query_pattern_mode == "none":
            self.query_patterns = None
        elif query_pattern_mode == "train-static-v1":
            from .query_patterns import get_train_query_patterns

            self.query_patterns = get_train_query_patterns()
        elif query_pattern_mode in {"train-mined-v1", "train-mined-v2"}:
            from .query_mining import get_mined_query_patterns

            self.query_patterns = get_mined_query_patterns()
        else:
            raise ValueError(f"Unknown query pattern mode: {query_pattern_mode!r}")

    def blocks(self, question: str, db_id: str, evidence: str) -> dict[str, str]:
        hint = (
            "\nHINT (use these definitions exactly):\n"
            + "\n".join(f"  {line}" for line in evidence.splitlines())
            + "\n"
            if evidence
            else ""
        )
        db_hint = get_db_hint(db_id) if self.use_db_hints else ""
        database_notes = (
            "\nDATABASE NOTES:\n"
            + "\n".join(f"  {line}" for line in db_hint.splitlines())
            + "\n"
            if db_hint
            else ""
        )
        few_shot = ""
        if self.retriever is not None and self.k > 0:
            few_shot = (
                "\n"
                + self.retriever.format_examples(question, db_id=db_id, k=self.k)
                + "\n"
            )
        query_patterns = ""
        if self.query_patterns is not None:
            if self.query_pattern_mode in {"train-mined-v1", "train-mined-v2"}:
                query_patterns = self.query_patterns.render(question, evidence)
            else:
                query_patterns = self.query_patterns.render()
        offline_metadata = (
            self.offline_metadata.render(db_id, question=question, evidence=evidence)
            if self.offline_metadata is not None else ""
        )
        return {
            "hint": hint,
            "database_notes": database_notes,
            "few_shot": few_shot,
            "query_patterns": query_patterns,
            "offline_metadata": offline_metadata,
        }

    def manifest(self) -> dict[str, Any]:
        retriever_manifest: dict[str, Any] | None = None
        if self.retriever is not None:
            value = getattr(self.retriever, "manifest", None)
            retriever_manifest = value() if callable(value) else value
            if retriever_manifest is None:
                retriever_manifest = {
                    "class": type(self.retriever).__name__,
                    "source": "unregistered",
                }
        manifest = {
            "runtime_sha256": _sha256(Path(__file__)),
            "use_db_hints": self.use_db_hints,
            "few_shot_k": self.k,
            "retriever": retriever_manifest,
            "query_pattern_mode": self.query_pattern_mode,
            "offline_metadata_mode": self.offline_metadata_mode,
            "query_patterns": (
                self.query_patterns.manifest()
                if self.query_patterns is not None else None
            ),
        }
        if self.offline_metadata is not None:
            manifest["offline_metadata"] = self.offline_metadata.manifest()
        if self.use_db_hints:
            path = Path(__file__).resolve().parents[1] / "db_hints.py"
            manifest["db_hints"] = {
                "source": "legacy-eval-tuned-unaudited",
                "path": str(path),
                "sha256": _sha256(path),
            }
        return manifest

    def selection_manifest(self, question: str, db_id: str, evidence: str) -> dict[str, Any]:
        selected: dict[str, Any] = {}
        if self.retriever is not None and self.k > 0:
            diagnostics = getattr(self.retriever, "selection_diagnostics", None)
            if callable(diagnostics):
                selected["few_shot"] = diagnostics(question, db_id=db_id, k=self.k)
        if self.query_patterns is not None and self.query_pattern_mode in {"train-mined-v1", "train-mined-v2"}:
            selected["query_patterns"] = self.query_patterns.retrieval_diagnostics(
                question, evidence
            )
        if self.offline_metadata is not None:
            selected["offline_schema"] = self.offline_metadata.selection_manifest(
                db_id, question=question, evidence=evidence
            )
        return selected
