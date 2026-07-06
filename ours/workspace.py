"""Small evidence workspace exposed to DB-RLM ablations."""

from __future__ import annotations

from typing import Any


class EvidenceWorkspace:
    """Append-only evidence memory for one root DB-RLM run."""

    def __init__(self, max_items: int = 20):
        self.max_items = max_items
        self._items: list[dict[str, Any]] = []

    def add(self, note: str, data: Any = None) -> dict[str, Any]:
        item = {"note": str(note), "data": data}
        self._items.append(item)
        if len(self._items) > self.max_items:
            self._items = self._items[-self.max_items :]
        return {"stored": True, "count": len(self._items)}

    def read(self) -> list[dict[str, Any]]:
        return list(self._items)

    def summary(self) -> str:
        if not self._items:
            return "(workspace empty)"
        lines = []
        for index, item in enumerate(self._items, start=1):
            lines.append(f"{index}. {item['note']}: {item['data']}")
        return "\n".join(lines)
