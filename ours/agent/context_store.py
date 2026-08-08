"""Externalized context store for E5 (RLM context environment).

E5-A only externalizes: the same knowledge sections that `KnowledgeAssembler`
would have concatenated into the prompt become addressable sections the model
reads on demand. It deliberately provides no search, slicing, or composition —
those are E5-B's variables. Keeping E5-A to "same information, different access
path" is what makes the information-equivalence check meaningful.

Every read is recorded so a trace can show which sections the model actually
looked at, and which it never opened.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable


# Canonical order; also the order sections are listed to the model.
SECTION_ORDER = (
    "hint",
    "database_notes",
    "few_shot",
    "query_patterns",
    "offline_metadata",
    "schema",
)

EventSink = Callable[[str, dict[str, Any], dict[str, Any]], None]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ContextStore:
    """Read-only, addressable store of the knowledge sections for one question."""

    def __init__(
        self,
        blocks: dict[str, str],
        *,
        event_sink: EventSink | None = None,
    ) -> None:
        # Preserve byte-exact content; only drop sections that are entirely empty,
        # matching the prompt path where an empty block contributes nothing.
        self._sections: dict[str, str] = {
            name: blocks[name]
            for name in SECTION_ORDER
            if blocks.get(name)
        }
        unknown = set(blocks) - set(SECTION_ORDER)
        if unknown:
            raise ValueError(f"Unknown context sections: {sorted(unknown)}")
        self._event_sink = event_sink
        self._reads: list[str] = []

    # ---------------------------------------------------------------
    # Model-facing API
    # ---------------------------------------------------------------

    def list(self) -> list[dict[str, Any]]:
        """Section directory: names and sizes, not content."""
        listing = [
            {"section": name, "chars": len(content)}
            for name, content in self._sections.items()
        ]
        self._emit("context.list", {}, {"sections": [row["section"] for row in listing]})
        return listing

    def read(self, section: str) -> dict[str, Any]:
        """Full content of one section. No slicing in E5-A."""
        name = str(section).strip()
        if name not in self._sections:
            result = {
                "section": name,
                "content": None,
                "error": f"unknown section; available: {sorted(self._sections)}",
            }
            self._emit("context.read", {"section": name}, result)
            return result
        self._reads.append(name)
        result = {"section": name, "content": self._sections[name], "error": None}
        self._emit(
            "context.read",
            {"section": name},
            {"section": name, "chars": len(result["content"]), "error": None},
        )
        return result

    # ---------------------------------------------------------------
    # Verification / provenance API (not exposed to the model)
    # ---------------------------------------------------------------

    def section_names(self) -> list[str]:
        return list(self._sections)

    def content(self, section: str) -> str:
        return self._sections[section]

    def manifest(self) -> dict[str, Any]:
        sections = [
            {
                "section": name,
                "chars": len(content),
                "sha256": _sha256(content),
            }
            for name, content in self._sections.items()
        ]
        return {
            "section_count": len(sections),
            "sections": sections,
            "combined_sha256": _sha256(
                "".join(f"{name}\0{content}\0" for name, content in self._sections.items())
            ),
        }

    def read_log(self) -> dict[str, Any]:
        opened = set(self._reads)
        return {
            "read_count": len(self._reads),
            "read_order": list(self._reads),
            "sections_opened": sorted(opened),
            "sections_never_opened": [
                name for name in self._sections if name not in opened
            ],
        }

    def _emit(self, tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(tool, arguments, result)


class GatedContextStore:
    """Model-facing view: only `list` and `read`.

    The full ContextStore also carries verification helpers (`content`,
    `manifest`, `read_log`). Exposing those to the model would let it fetch
    section text without going through `read`, which would silently corrupt the
    read-log measurement E5-A depends on. Same gating pattern as
    GatedDBEnvironment.
    """

    __slots__ = ("__store", "__event_sink")

    def __init__(self, store: ContextStore, event_sink: EventSink | None = None) -> None:
        self.__store = store
        self.__event_sink = event_sink

    def list(self) -> list[dict[str, Any]]:
        return self.__store.list()

    def read(self, section: str) -> dict[str, Any]:
        return self.__store.read(section)

    def __getattr__(self, name: str) -> Any:
        if self.__event_sink is not None:
            self.__event_sink(
                "capability.denied",
                {"capability": f"ctx.{name}"},
                {"allowed": False, "error": "capability is not enabled for this variant"},
            )
        raise AttributeError(f"ctx.{name} is not available in this experiment variant")


def verify_information_equivalence(
    blocks: dict[str, str],
    store: ContextStore,
) -> dict[str, Any]:
    """Strict check that externalization preserved every knowledge section.

    Compares byte-for-byte at section granularity against the blocks that the
    direct-prompt path would have used. Returns a structured report rather than
    raising, so callers can log the full diff.
    """
    prompt_sections = {name: text for name, text in blocks.items() if text}
    store_sections = {name: store.content(name) for name in store.section_names()}

    missing = sorted(set(prompt_sections) - set(store_sections))
    extra = sorted(set(store_sections) - set(prompt_sections))
    mismatched = sorted(
        name
        for name in set(prompt_sections) & set(store_sections)
        if prompt_sections[name] != store_sections[name]
    )
    return {
        "equivalent": not (missing or extra or mismatched),
        "prompt_section_count": len(prompt_sections),
        "store_section_count": len(store_sections),
        "missing_from_store": missing,
        "extra_in_store": extra,
        "content_mismatch": mismatched,
        "section_sha256": {
            name: _sha256(text) for name, text in sorted(prompt_sections.items())
        },
    }
