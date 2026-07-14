"""Runtime capability gate for experiment variants."""

from __future__ import annotations

from typing import Any, Callable

from ours.db_environment import DBEnvironment


EventSink = Callable[[str, dict[str, Any], dict[str, Any]], None]


class CapabilityDeniedError(PermissionError):
    pass


class GatedDBEnvironment:
    """Expose only DB methods declared by the experiment manifest."""

    __slots__ = ("__environment", "__allowed", "__event_sink")

    def __init__(
        self,
        environment: DBEnvironment,
        allowed_methods: tuple[str, ...],
        event_sink: EventSink,
    ) -> None:
        self.__environment = environment
        self.__allowed = frozenset(allowed_methods)
        self.__event_sink = event_sink

    def execute(self, sql: str) -> dict[str, Any]:
        self._require("execute", {"sql": sql})
        return self.__environment.execute(sql)

    def sample_values(
        self,
        table: str,
        column: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        arguments = {"table": table, "column": column, "limit": limit}
        self._require("sample_values", arguments)
        return self.__environment.sample_values(table, column, limit)

    def _require(self, method: str, arguments: dict[str, Any]) -> None:
        if method in self.__allowed:
            return
        self.__event_sink(
            "capability.denied",
            {"capability": f"db.{method}", **arguments},
            {"allowed": False, "error": "capability is not enabled for this variant"},
        )
        raise CapabilityDeniedError(
            f"db.{method} is not enabled for this experiment variant"
        )

    def __getattr__(self, name: str) -> Any:
        self.__event_sink(
            "capability.denied",
            {"capability": f"db.{name}"},
            {"allowed": False, "error": "capability is not enabled for this variant"},
        )
        raise CapabilityDeniedError(
            f"db.{name} is not enabled for this experiment variant"
        )
