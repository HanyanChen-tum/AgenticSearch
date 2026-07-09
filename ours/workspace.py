"""Restricted workspace exposed to DB-RLM ablations."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.rlm.repl import REPLExecutor, REPLError


READABLE_EXTENSIONS = {".json", ".txt", ".md", ".sql", ".csv", ".tsv", ".py"}
BLOCKED_FILENAMES = {".env", ".env.local", ".env.example"}


class EvidenceWorkspace:
    """Append-only evidence memory plus restricted artifact storage.

    The model may read non-sensitive project text files, but writes are limited
    to a per-run artifact directory under results/model_workspace.
    """

    def __init__(
        self,
        max_items: int = 20,
        project_root: str | Path | None = None,
        artifact_dir: str | Path | None = None,
        schema_text: str = "",
    ):
        self.max_items = max_items
        self._items: list[dict[str, Any]] = []
        self.project_root = Path(project_root or Path.cwd()).resolve()
        default_artifact_dir = (
            self.project_root
            / "results"
            / "model_workspace"
            / time.strftime("%Y%m%d_%H%M%S")
        )
        self.artifact_dir = Path(artifact_dir or default_artifact_dir).resolve()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._schema_text = schema_text
        self._runtime_env: dict[str, Any] = {}

    def add(self, note: str, data: Any = None) -> dict[str, Any]:
        item = {"note": str(note), "data": data}
        self._items.append(item)
        if len(self._items) > self.max_items:
            self._items = self._items[-self.max_items :]
        return {"stored": True, "count": len(self._items)}

    def read(self) -> list[dict[str, Any]]:
        return list(self._items)

    def save_result(self, name: str, data: Any) -> dict[str, Any]:
        path = self._artifact_path(f"{self._safe_name(name)}.json")
        path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
        self.add(f"saved result {name}", {"path": str(path), "data": data})
        return {"saved": True, "path": str(path)}

    def load_result(self, name: str) -> dict[str, Any]:
        path = self._artifact_path(f"{self._safe_name(name)}.json")
        if not path.exists():
            return {"error": f"Result not found: {name}"}
        return {
            "name": name,
            "path": str(path),
            "data": json.loads(path.read_text(encoding="utf-8")),
            "error": None,
        }

    def list_files(self, relative_dir: str = "", limit: int = 50) -> dict[str, Any]:
        directory = self._read_path(relative_dir or ".")
        if directory is None:
            return {"files": [], "error": "Path is outside readable project root"}
        if not directory.exists() or not directory.is_dir():
            return {"files": [], "error": f"Directory not found: {relative_dir}"}

        files = []
        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue
            rel = path.relative_to(self.project_root)
            files.append({"path": str(rel), "type": "dir" if path.is_dir() else "file"})
            if len(files) >= max(1, min(limit, 200)):
                break
        return {"files": files, "error": None}

    def read_file(self, relative_path: str, max_chars: int = 4000) -> dict[str, Any]:
        path = self._read_path(relative_path)
        if path is None:
            return {"content": "", "error": "Path is outside readable project root"}
        if path.name in BLOCKED_FILENAMES or path.name.startswith("."):
            return {"content": "", "error": f"Reading {path.name} is blocked"}
        if path.suffix.lower() not in READABLE_EXTENSIONS:
            return {"content": "", "error": f"Unsupported file type: {path.suffix}"}
        if not path.exists() or not path.is_file():
            return {"content": "", "error": f"File not found: {relative_path}"}

        text = path.read_text(encoding="utf-8", errors="replace")
        max_chars = max(1, min(max_chars, 12000))
        truncated = len(text) > max_chars
        return {
            "path": str(path.relative_to(self.project_root)),
            "content": text[:max_chars],
            "truncated": truncated,
            "error": None,
        }

    def read_schema_file(self, max_chars: int = 6000) -> dict[str, Any]:
        max_chars = max(1, min(max_chars, 12000))
        return {
            "content": self._schema_text[:max_chars],
            "truncated": len(self._schema_text) > max_chars,
            "error": None,
        }

    def write_note_file(self, name: str, content: str) -> dict[str, Any]:
        path = self._artifact_path(f"{self._safe_name(name)}.txt")
        path.write_text(str(content), encoding="utf-8")
        self.add(f"wrote note file {name}", {"path": str(path)})
        return {"written": True, "path": str(path)}

    def write_python_script(self, name: str, code: str) -> dict[str, Any]:
        path = self._artifact_path(f"{self._safe_name(name)}.py")
        path.write_text(str(code), encoding="utf-8")
        self.add(f"wrote python script {name}", {"path": str(path)})
        return {"written": True, "path": str(path)}

    def run_python_script(self, name: str) -> dict[str, Any]:
        path = self._artifact_path(f"{self._safe_name(name)}.py")
        if not path.exists():
            return {"output": "", "error": f"Script not found: {name}"}
        return self.run_python(path.read_text(encoding="utf-8"))

    def run_python(self, code: str) -> dict[str, Any]:
        executor = REPLExecutor(max_output_chars=4000)
        env = dict(self._runtime_env)
        env["workspace"] = self
        try:
            output = executor.execute(str(code), env)
            self.add("python execution", {"code": str(code)[:500], "output": output})
            return {"output": output, "error": None}
        except REPLError as error:
            message = str(error)
            self.add("python execution error", {"code": str(code)[:500], "error": message})
            return {"output": "", "error": message}

    def set_runtime_env(self, env: dict[str, Any]) -> None:
        self._runtime_env = {
            key: value
            for key, value in env.items()
            if key not in {"workspace", "_print"}
        }

    def summary(self) -> str:
        if not self._items:
            return "(workspace empty)"
        lines = []
        for index, item in enumerate(self._items, start=1):
            lines.append(f"{index}. {item['note']}: {item['data']}")
        return "\n".join(lines)

    def _read_path(self, relative_path: str) -> Path | None:
        try:
            path = (self.project_root / str(relative_path)).resolve()
            path.relative_to(self.project_root)
            return path
        except (OSError, ValueError):
            return None

    def _artifact_path(self, relative_path: str) -> Path:
        path = (self.artifact_dir / str(relative_path)).resolve()
        path.relative_to(self.artifact_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _safe_name(name: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
        return safe[:80] or "artifact"
