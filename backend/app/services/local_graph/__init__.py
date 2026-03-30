from .graph_service import LocalGraphService
from .models import (
    GraphNode,
    GraphEdge,
    Episode,
    SearchResults,
    EpisodeData,
)


def get_shared_graph_service():
    """Get the singleton LocalGraphService instance.

    Convenience wrapper around graph_builder.get_graph_service()
    for modules that import from local_graph.
    """
    from ..graph_builder import get_graph_service
    return get_graph_service()


__all__ = [
    "LocalGraphService",
    "GraphNode",
    "GraphEdge",
    "Episode",
    "SearchResults",
    "EpisodeData",
    "get_shared_graph_service",
]
