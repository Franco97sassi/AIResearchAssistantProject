from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

END = "__end__"


@dataclass(frozen=True)
class _ConditionalEdges:
    router: Callable[[dict[str, Any]], str]
    path_map: Mapping[str, str]


class StateGraph:
    """Minimal StateGraph runtime compatible with the LangGraph API used here.

    The project depends on the real `langgraph` package in production. This
    lightweight runtime keeps the offline test environment executable while
    preserving the same explicit node/edge graph contract used by LangGraph.
    """

    def __init__(self, state_schema: type[Any]) -> None:
        self.state_schema = state_schema
        self._nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[str, _ConditionalEdges] = {}
        self._entry_point: str | None = None

    def add_node(self, name: str, node: Callable[[dict[str, Any]], dict[str, Any] | None]) -> None:
        self._nodes[name] = node

    def set_entry_point(self, name: str) -> None:
        self._entry_point = name

    def add_edge(self, start_key: str, end_key: str) -> None:
        self._edges[start_key] = end_key

    def add_conditional_edges(
        self,
        source: str,
        path: Callable[[dict[str, Any]], str],
        path_map: Mapping[str, str],
    ) -> None:
        self._conditional_edges[source] = _ConditionalEdges(router=path, path_map=path_map)

    def compile(self) -> "CompiledStateGraph":
        if self._entry_point is None:
            raise ValueError("StateGraph requires an entry point before compile().")
        return CompiledStateGraph(
            nodes=self._nodes,
            edges=self._edges,
            conditional_edges=self._conditional_edges,
            entry_point=self._entry_point,
        )


@dataclass(frozen=True)
class CompiledStateGraph:
    nodes: Mapping[str, Callable[[dict[str, Any]], dict[str, Any] | None]]
    edges: Mapping[str, str]
    conditional_edges: Mapping[str, _ConditionalEdges]
    entry_point: str

    def invoke(self, initial_state: Mapping[str, Any]) -> dict[str, Any]:
        state = dict(initial_state)
        current = self.entry_point
        while current != END:
            node = self.nodes[current]
            updates = node(state) or {}
            state.update(updates)
            if current in self.conditional_edges:
                conditional = self.conditional_edges[current]
                route = conditional.router(state)
                current = conditional.path_map[route]
            else:
                current = self.edges.get(current, END)
        return state
