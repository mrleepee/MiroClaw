"""
Research Tools

search, navigate, and extract FunctionTools for MiroClaw agents
to perform web research during the Research phase.

When camofox-browser is available, uses its REST API for real web
search and page extraction. Falls back to empty results when the
browser server is not running.

Satisfies: R10 (Browser integration), R07 (Research budget)
"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from ...utils.logger import get_logger

if TYPE_CHECKING:
    from .camofox_client import CamofoxBrowserClient

logger = get_logger('miroclaw.research')


class ResearchTool:
    """MiroClaw research tool for web search and page extraction.

    Wraps camofox-browser REST API for:
    - Web search with results (titles, URLs, snippets)
    - Page extraction via accessibility tree
    - Budget enforcement (hard limits per round)
    """

    def __init__(
        self,
        agent_id: str,
        budget_tracker=None,
        browser_profile: Optional[str] = None,
        browser_client: Optional["CamofoxBrowserClient"] = None,
    ):
        self.agent_id = agent_id
        self.budget = budget_tracker
        self.browser_profile = browser_profile or f"miroclaw_{agent_id}"
        self.browser_client = browser_client

    def search(self, query: str) -> Dict[str, Any]:
        """Perform a web search via the agent's browser profile.

        Returns search results (titles, URLs, snippets).
        Counts against the agent's per-round search budget.
        """
        if self.budget and not self.budget.can_search():
            return {
                "success": False,
                "error": "Search budget exhausted (3 searches per round)",
                "results": [],
            }

        # Use budget
        if self.budget:
            self.budget.use_search()

        try:
            logger.info(f"Agent {self.agent_id} searching: {query[:100]}")

            # Use camofox-browser if available
            if self.browser_client:
                result = self.browser_client.search(self.agent_id, query)
                if result.get("success"):
                    logger.info(
                        f"Agent {self.agent_id} got {len(result.get('results', []))} results"
                    )
                return result

            # Fallback: no browser connected
            return {
                "success": True,
                "query": query,
                "results": [],
                "note": "Browser not connected (camofox-browser not running)",
            }
        except Exception as e:
            logger.error(f"Search failed for agent {self.agent_id}: {e}")
            return {"success": False, "error": str(e), "results": []}

    def extract(self, url: str) -> Dict[str, Any]:
        """Extract text content from a URL via accessibility tree.

        Counts against the agent's per-round page read budget.
        """
        if self.budget and not self.budget.can_read():
            return {
                "success": False,
                "error": "Page read budget exhausted (3 reads per round)",
                "content": "",
            }

        if self.budget:
            self.budget.use_read()

        try:
            logger.info(f"Agent {self.agent_id} extracting: {url[:100]}")

            # Use camofox-browser if available
            if self.browser_client:
                result = self.browser_client.extract(self.agent_id, url)
                if result.get("success"):
                    content_len = len(result.get("content", ""))
                    logger.info(
                        f"Agent {self.agent_id} extracted {content_len} chars from {url[:80]}"
                    )
                return result

            # Fallback: no browser connected
            return {
                "success": True,
                "url": url,
                "content": "",
                "note": "Browser not connected (camofox-browser not running)",
            }
        except Exception as e:
            logger.error(f"Extract failed for agent {self.agent_id}: {e}")
            return {"success": False, "error": str(e), "content": ""}

    def get_graph_state(self, graph_service, query: str = "") -> Dict[str, Any]:
        """Read current knowledge graph state for the Research phase.

        This does not count against any budget — agents can always
        read the graph state.
        """
        try:
            if graph_service is None:
                return {"success": False, "error": "No graph service available"}

            # Get recent triples and contested triples
            recent = graph_service.get_recent_triples(limit=20)
            contested = graph_service.get_triples_by_status("contested")

            return {
                "success": True,
                "recent_triples": recent,
                "contested_triples": contested,
                "graph_stats": graph_service.get_stats(),
            }
        except Exception as e:
            logger.error(f"Graph state read failed: {e}")
            return {"success": False, "error": str(e)}
