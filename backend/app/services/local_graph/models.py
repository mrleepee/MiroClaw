"""Data models matching Zep SDK attribute names for drop-in compatibility."""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


def _new_uuid() -> str:
    return str(_uuid.uuid4())


def _now() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class GraphNode:
    """Matches Zep SDK node object attribute names.

    Zep code accesses both ``uuid_`` and ``uuid`` via getattr fallback.
    We expose both for compatibility.
    """

    uuid_: str = field(default_factory=_new_uuid)
    name: str = ""
    labels: List[str] = field(default_factory=lambda: ["Entity"])
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = field(default_factory=_now)
    embedding: Optional[List[float]] = field(default=None, repr=False)
    graph_id: str = ""
    entity_category: str = "actor"  # "actor" or "context"

    @property
    def uuid(self) -> str:
        return self.uuid_


@dataclass
class GraphEdge:
    """Matches Zep SDK edge object attribute names."""

    uuid_: str = field(default_factory=_new_uuid)
    name: str = ""
    fact: str = ""
    source_node_uuid: str = ""
    target_node_uuid: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = field(default_factory=_now)
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    embedding: Optional[List[float]] = field(default=None, repr=False)
    graph_id: str = ""

    @property
    def uuid(self) -> str:
        return self.uuid_


@dataclass
class Episode:
    """Matches Zep SDK episode object."""

    uuid_: str = field(default_factory=_new_uuid)
    data: str = ""
    type: str = "text"
    processed: bool = False
    graph_id: str = ""
    created_at: Optional[str] = field(default_factory=_now)

    @property
    def uuid(self) -> str:
        return self.uuid_


@dataclass
class EpisodeData:
    """Input data for creating an episode (matches Zep EpisodeData)."""

    data: str = ""
    type: str = "text"


@dataclass
class SearchResults:
    """Matches Zep search result object with .edges and .nodes."""

    edges: List[GraphEdge] = field(default_factory=list)
    nodes: List[GraphNode] = field(default_factory=list)


@dataclass
class OntologyDefinition:
    """Stores ontology entity and edge type definitions."""

    entity_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edge_types: Dict[str, Dict[str, Any]] = field(default_factory=dict)
