"""
Analytics FunctionTools for Report Agent

Wraps MiroClawAnalytics for the ReACT report agent to query:
- Disputed triples (contested knowledge)
- Agent provenance trails
- Oracle forecast history
- Position stance history

Satisfies: R14 (Post-simulation analytics), R16 (Retain report agent)
"""

from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger

logger = get_logger('miroclaw.analytics_tools')


class AnalyticsTools:
    """Analytics tools for the Report Agent.

    Registered alongside existing GraphSearchService and SimulationDBTools
    to give the report agent access to MiroClaw-specific analytics data.
    """

    def __init__(
        self,
        graph_service=None,
        simulation_runner=None,
        simulation_id: str = None,
    ):
        self.graph_service = graph_service
        self.simulation_runner = simulation_runner
        self.simulation_id = simulation_id

    def query_disputed(self, query: str = "") -> Dict[str, Any]:
        """Query contested/disputed triples from the knowledge graph.

        Returns triples where agents genuinely disagreed about reality,
        with agent-type breakdown and source URLs from both sides.

        Args:
            query: Optional filter query for specific topics.

        Returns:
            Dict with success status and disputed triples data.
        """
        try:
            from ...services.miroclaw_analytics import MiroClawAnalytics
            analytics = MiroClawAnalytics(graph_service=self.graph_service)
            result = analytics.generate_dispute_map()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"query_disputed failed: {e}")
            return {"success": False, "error": str(e)}

    def query_provenance(self, agent_id: str) -> Dict[str, Any]:
        """Query per-agent provenance trail.

        Shows per-round: searches, reads, graph additions, votes,
        oracle consultations, and stance shifts.

        Args:
            agent_id: Agent identifier to query.

        Returns:
            Dict with success status and per-round provenance data.
        """
        try:
            from ...services.miroclaw_analytics import MiroClawAnalytics
            analytics = MiroClawAnalytics(
                graph_service=self.graph_service,
                simulation_runner=self.simulation_runner,
                simulation_id=self.simulation_id,
            )
            result = analytics.generate_provenance_trail(
                agent_id=agent_id,
                simulation_id=self.simulation_id,
            )
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"query_provenance failed: {e}")
            return {"success": False, "error": str(e)}

    def query_oracle_forecasts(self, question: str = "") -> Dict[str, Any]:
        """Query oracle forecast history as time series.

        Shows probability estimates over rounds for each oracle question.

        Args:
            question: Optional filter for specific forecast question.

        Returns:
            Dict with success status and oracle time series data.
        """
        try:
            from ...services.miroclaw_analytics import MiroClawAnalytics
            analytics = MiroClawAnalytics()
            result = analytics.generate_oracle_time_series(oracle_agents=[])
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"query_oracle_forecasts failed: {e}")
            return {"success": False, "error": str(e)}

    def query_stance_history(self, agent_type: str = "") -> Dict[str, Any]:
        """Query position drift data across agents.

        Shows per-agent stance over time with triggering evidence
        at shift points.

        Args:
            agent_type: Optional filter by agent entity type.

        Returns:
            Dict with success status and stance history data.
        """
        try:
            from ...services.miroclaw_analytics import MiroClawAnalytics
            analytics = MiroClawAnalytics()
            result = analytics.generate_position_drift(agents=[])
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"query_stance_history failed: {e}")
            return {"success": False, "error": str(e)}

    def get_tool_definitions(self) -> Dict[str, Dict[str, Any]]:
        """Get tool definitions for ReportAgent registration.

        Returns dict matching the pattern used by ReportAgent._define_tools().
        """
        return {
            "query_disputed": {
                "name": "query_disputed",
                "description": (
                    "Query contested/disputed triples from the knowledge graph. "
                    "Returns triples where agents genuinely disagreed about reality, "
                    "with agent-type breakdown and source URLs from both sides. "
                    "Use this to identify the most analytically valuable disputes."
                ),
                "parameters": {
                    "query": "Optional topic filter for disputed triples",
                },
            },
            "query_provenance": {
                "name": "query_provenance",
                "description": (
                    "Query per-agent provenance trail. Shows per-round activity: "
                    "searches performed, pages read, graph additions, votes cast, "
                    "oracle consultations, and stance shifts. Use this to trace "
                    "how an agent arrived at its contributions."
                ),
                "parameters": {
                    "agent_id": "Agent identifier to query provenance for",
                },
            },
            "query_oracle_forecasts": {
                "name": "query_oracle_forecasts",
                "description": (
                    "Query oracle forecast history as time series. Shows probability "
                    "estimates over rounds for each oracle question. Use this to "
                    "track how oracle confidence shifted as evidence accumulated."
                ),
                "parameters": {
                    "question": "Optional filter for specific forecast question",
                },
            },
            "query_stance_history": {
                "name": "query_stance_history",
                "description": (
                    "Query agent position drift over the simulation. Shows per-agent "
                    "stance (supportive/neutral/opposing) over time with annotated "
                    "shift points and triggering evidence."
                ),
                "parameters": {
                    "agent_type": "Optional filter by agent entity type",
                },
            },
        }
