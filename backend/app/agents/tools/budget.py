"""
Budget Tracker

Per-agent per-round budget enforcement for research actions.

Hard limits (not advisory):
- 3 web searches per round
- 3 page reads per round
- 1 graph addition per round
- 1 oracle consultation per round

Satisfies: R07 (Research budget)
"""

from dataclasses import dataclass
from typing import Dict

from ...utils.logger import get_logger

logger = get_logger('miroclaw.budget')


# Default budget limits
DEFAULT_MAX_SEARCHES = 3
DEFAULT_MAX_READS = 3
DEFAULT_MAX_GRAPH_ADDITIONS = 1
DEFAULT_MAX_ORACLE_CONSULTATIONS = 1


@dataclass
class RoundBudget:
    """Budget for a single agent for a single round."""
    agent_id: str
    round_num: int
    max_searches: int = DEFAULT_MAX_SEARCHES
    max_reads: int = DEFAULT_MAX_READS
    max_graph_additions: int = DEFAULT_MAX_GRAPH_ADDITIONS
    max_oracle_consultations: int = DEFAULT_MAX_ORACLE_CONSULTATIONS

    searches_used: int = 0
    reads_used: int = 0
    graph_additions_used: int = 0
    oracle_consultations_used: int = 0

    def can_search(self) -> bool:
        return self.searches_used < self.max_searches

    def can_read(self) -> bool:
        return self.reads_used < self.max_reads

    def can_add_to_graph(self) -> bool:
        return self.graph_additions_used < self.max_graph_additions

    def can_consult_oracle(self) -> bool:
        return self.oracle_consultations_used < self.max_oracle_consultations

    def use_search(self) -> bool:
        if not self.can_search():
            logger.warning(
                f"Agent {self.agent_id} search budget exhausted "
                f"(round {self.round_num})"
            )
            return False
        self.searches_used += 1
        return True

    def use_read(self) -> bool:
        if not self.can_read():
            logger.warning(
                f"Agent {self.agent_id} read budget exhausted "
                f"(round {self.round_num})"
            )
            return False
        self.reads_used += 1
        return True

    def use_graph_addition(self) -> bool:
        if not self.can_add_to_graph():
            logger.warning(
                f"Agent {self.agent_id} graph addition budget exhausted "
                f"(round {self.round_num})"
            )
            return False
        self.graph_additions_used += 1
        return True

    def use_oracle_consultation(self) -> bool:
        if not self.can_consult_oracle():
            logger.warning(
                f"Agent {self.agent_id} oracle consultation budget exhausted "
                f"(round {self.round_num})"
            )
            return False
        self.oracle_consultations_used += 1
        return True

    def get_summary(self) -> Dict[str, int]:
        """Get budget usage summary."""
        return {
            "agent_id": self.agent_id,
            "round_num": self.round_num,
            "searches": f"{self.searches_used}/{self.max_searches}",
            "reads": f"{self.reads_used}/{self.max_reads}",
            "graph_additions": f"{self.graph_additions_used}/{self.max_graph_additions}",
            "oracle_consultations": f"{self.oracle_consultations_used}/{self.max_oracle_consultations}",
        }


class BudgetManager:
    """Manages per-agent per-round budgets across all agents.

    Creates and resets budgets at round boundaries.
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._budgets: Dict[str, RoundBudget] = {}  # key: agent_id

    def create_budget(self, agent_id: str, round_num: int) -> RoundBudget:
        """Create a new budget for an agent for the current round."""
        budget = RoundBudget(
            agent_id=agent_id,
            round_num=round_num,
            max_searches=self.config.get("max_searches", DEFAULT_MAX_SEARCHES),
            max_reads=self.config.get("max_reads", DEFAULT_MAX_READS),
            max_graph_additions=self.config.get(
                "max_graph_additions", DEFAULT_MAX_GRAPH_ADDITIONS
            ),
            max_oracle_consultations=self.config.get(
                "max_oracle_consultations", DEFAULT_MAX_ORACLE_CONSULTATIONS
            ),
        )
        self._budgets[agent_id] = budget
        return budget

    def get_budget(self, agent_id: str) -> RoundBudget:
        """Get the current budget for an agent."""
        return self._budgets.get(agent_id)

    def reset_round(self, round_num: int):
        """Reset all budgets for a new round."""
        for agent_id in self._budgets:
            self.create_budget(agent_id, round_num)

    def get_all_summaries(self) -> Dict[str, Dict]:
        """Get budget summaries for all agents."""
        return {
            agent_id: budget.get_summary()
            for agent_id, budget in self._budgets.items()
        }
