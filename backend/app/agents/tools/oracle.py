"""
Oracle Tools

consult_oracle FunctionTool for agents to consult specialist Oracle agents
during the Research phase. Returns calibrated probability estimates.

Satisfies: R11 (Oracle agents), R07 (Oracle consultation budget)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger

logger = get_logger('miroclaw.oracle')


class OracleConsultationTool:
    """Tool for agents to consult Oracle agents.

    Budget: 1 consultation per agent per round.
    Oracle receives: question + relevant context from knowledge graph.
    Oracle returns: calibrated probability estimate with reasoning.
    """

    def __init__(
        self,
        oracle_agents=None,
        budget_tracker=None,
        graph_service=None,
    ):
        self.oracle_agents = oracle_agents or []
        self.budget = budget_tracker
        self.graph_service = graph_service
        self._consultation_log: List[Dict[str, Any]] = []

    def consult(
        self,
        agent_id: str,
        question: str,
        round_num: int,
    ) -> Dict[str, Any]:
        """Consult an oracle agent with a question.

        Args:
            agent_id: The consulting agent's identifier.
            question: The question to ask the oracle.
            round_num: Current round number.

        Returns:
            Dict with probability estimate and reasoning.
        """
        # Check budget
        if self.budget and not self.budget.can_consult_oracle():
            return {
                "success": False,
                "error": "Oracle consultation budget exhausted (1 per round)",
            }

        if not self.oracle_agents:
            return {
                "success": False,
                "error": "No oracle agents available",
            }

        # Use budget
        if self.budget:
            self.budget.use_oracle_consultation()

        try:
            # Select an oracle (round-robin or random)
            oracle = self.oracle_agents[round_num % len(self.oracle_agents)]

            # Gather relevant context from knowledge graph
            context = ""
            if self.graph_service:
                context = self._gather_context(question)

            # Consult oracle
            result = oracle.forecast(question, context)

            # Log consultation
            entry = {
                "consulting_agent": agent_id,
                "oracle_id": oracle.agent_id,
                "question": question,
                "round": round_num,
                "probability": result.get("probability"),
                "reasoning": result.get("reasoning", ""),
                "timestamp": datetime.now().isoformat(),
            }
            self._consultation_log.append(entry)

            logger.info(
                f"Oracle consultation: agent={agent_id}, oracle={oracle.agent_id}, "
                f"question={question[:80]}..., probability={result.get('probability')}"
            )

            return {
                "success": True,
                "probability": result.get("probability"),
                "reasoning": result.get("reasoning"),
                "confidence": result.get("confidence"),
            }

        except Exception as e:
            logger.error(f"Oracle consultation failed: {e}")
            return {"success": False, "error": str(e)}

    def _gather_context(self, question: str) -> str:
        """Gather relevant context from the knowledge graph for the oracle."""
        try:
            results = self.graph_service.search(
                query=question,
                limit=10,
                scope="edges",
            )
            if results and hasattr(results, 'edges') and results.edges:
                return "\n".join(
                    edge.fact for edge in results.edges[:5]
                    if hasattr(edge, 'fact') and edge.fact
                )
            return ""
        except Exception:
            return ""

    def get_consultation_log(
        self,
        agent_id: Optional[str] = None,
        round_num: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get consultation history."""
        log = self._consultation_log
        if agent_id:
            log = [e for e in log if e["consulting_agent"] == agent_id]
        if round_num is not None:
            log = [e for e in log if e["round"] == round_num]
        return log
