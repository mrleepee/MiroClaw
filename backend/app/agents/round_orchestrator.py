"""
MiroClaw Round Orchestrator

Workforce-based phased round execution replacing OASIS's flat round_robin() loop.

Each simulation round progresses through exactly 5 phases in order:
1. Research — agents read graph state, perform web searches, read pages,
   consult oracle (parallel, per-agent)
2. Contribute — agents write 1 triple to graph and compose social media post
   (parallel, per-agent)
3. Vote — agents upvote/downvote new triples from other agents this round
   (parallel, per-agent)
4. Curate — curator agent merges, prunes, and flags triples (single agent)
5. Oracle Forecast — oracle agents produce calibrated forecasts on core
   questions (every N rounds, oracle agents only)

Phase enforcement: agents cannot execute actions from a later phase during
an earlier phase. Round orchestration uses CAMEL Workforce task channels.

Satisfies: R02 (Phased round orchestration)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from camel.messages import BaseMessage

from .miroclaw_agent import MiroClawAgent, Phase
from .memory import MiroClawAgentMemory
from ..utils.logger import get_logger

logger = get_logger('miroclaw.orchestrator')


@dataclass
class RoundResult:
    """Result of a single simulation round."""
    round_num: int
    phase_results: Dict[str, Any] = field(default_factory=dict)
    triples_added: int = 0
    votes_cast: int = 0
    curator_actions: int = 0
    oracle_forecasts: int = 0
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "triples_added": self.triples_added,
            "votes_cast": self.votes_cast,
            "curator_actions": self.curator_actions,
            "oracle_forecasts": self.oracle_forecasts,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass
class SimulationConfig:
    """Configuration for a MiroClaw simulation."""
    total_rounds: int = 10
    oracle_forecast_interval: int = 5  # Oracle forecasts every N rounds
    curator_agent: Optional[MiroClawAgent] = None
    oracle_agents: List[MiroClawAgent] = field(default_factory=list)
    # Callbacks for phase-specific logic
    on_research: Optional[Callable] = None
    on_contribute: Optional[Callable] = None
    on_vote: Optional[Callable] = None
    on_curate: Optional[Callable] = None
    on_oracle: Optional[Callable] = None
    on_round_start: Optional[Callable] = None
    on_round_end: Optional[Callable] = None


class RoundOrchestrator:
    """Orchestrates MiroClaw simulation rounds with phased execution.

    Replaces OASIS's flat round_robin() with structured 5-phase rounds
    using CAMEL Workforce-style task coordination.

    Usage:
        orchestrator = RoundOrchestrator(agents, config)
        await orchestrator.run()
    """

    def __init__(
        self,
        agents: List[MiroClawAgent],
        config: SimulationConfig,
    ):
        self.agents = agents
        self.config = config
        self.current_round = 0
        self.current_phase: Optional[Phase] = None
        self.results: List[RoundResult] = []

    async def run(self) -> List[RoundResult]:
        """Run the full simulation through all rounds."""
        logger.info(
            f"Starting MiroClaw simulation: "
            f"{len(self.agents)} agents, {self.config.total_rounds} rounds"
        )

        for round_num in range(1, self.config.total_rounds + 1):
            result = await self.run_round(round_num)
            self.results.append(result)

            if round_num % 5 == 0 or round_num == self.config.total_rounds:
                logger.info(
                    f"Round {round_num}/{self.config.total_rounds} complete: "
                    f"{result.triples_added} triples, {result.votes_cast} votes"
                )

        logger.info(
            f"Simulation complete: {len(self.results)} rounds, "
            f"{sum(r.triples_added for r in self.results)} total triples"
        )
        return self.results

    async def run_round(self, round_num: int) -> RoundResult:
        """Execute a single round through all 5 phases in strict order."""
        self.current_round = round_num
        result = RoundResult(round_num=round_num)

        if self.config.on_round_start:
            self.config.on_round_start(round_num)

        # Phase 1: Research (parallel, per-agent)
        await self._execute_phase(Phase.RESEARCH, round_num, result)

        # Phase 2: Contribute (parallel, per-agent)
        await self._execute_phase(Phase.CONTRIBUTE, round_num, result)

        # Phase 3: Vote (parallel, per-agent)
        await self._execute_phase(Phase.VOTE, round_num, result)

        # Phase 4: Curate (single curator agent)
        await self._execute_phase(Phase.CURATE, round_num, result)

        # Phase 5: Oracle Forecast (every N rounds, oracle agents only)
        if round_num % self.config.oracle_forecast_interval == 0:
            await self._execute_phase(Phase.ORACLE, round_num, result)

        # Check memory compaction for all agents
        for agent in self.agents:
            if isinstance(agent.memory, MiroClawAgentMemory):
                if agent.memory.check_compaction_needed():
                    agent.memory.perform_compaction(
                        round_start=max(1, round_num - 50),
                        round_end=round_num,
                    )

        result.end_time = datetime.now().isoformat()

        if self.config.on_round_end:
            self.config.on_round_end(round_num, result)

        return result

    async def _execute_phase(
        self,
        phase: Phase,
        round_num: int,
        result: RoundResult,
    ):
        """Execute a single phase of a round."""
        self.current_phase = phase
        logger.debug(f"Round {round_num}: entering {phase.value} phase")

        # Set phase on all relevant agents (swaps FunctionTools)
        relevant_agents = self._get_agents_for_phase(phase)
        for agent in relevant_agents:
            agent.set_phase(phase, round_num=round_num)

        # Execute phase-specific logic
        if phase == Phase.RESEARCH and self.config.on_research:
            phase_result = await self.config.on_research(
                round_num, relevant_agents
            )
            result.phase_results["research"] = phase_result

        elif phase == Phase.CONTRIBUTE and self.config.on_contribute:
            phase_result = await self.config.on_contribute(
                round_num, relevant_agents
            )
            result.triples_added = phase_result.get("triples_added", 0) if isinstance(phase_result, dict) else 0
            result.phase_results["contribute"] = phase_result

        elif phase == Phase.VOTE and self.config.on_vote:
            phase_result = await self.config.on_vote(
                round_num, relevant_agents
            )
            result.votes_cast = phase_result.get("votes_cast", 0) if isinstance(phase_result, dict) else 0
            result.phase_results["vote"] = phase_result

        elif phase == Phase.CURATE and self.config.on_curate:
            phase_result = await self.config.on_curate(
                round_num, self.config.curator_agent
            )
            result.curator_actions = phase_result.get("actions_count", 0) if isinstance(phase_result, dict) else 0
            result.phase_results["curate"] = phase_result

        elif phase == Phase.ORACLE and self.config.on_oracle:
            phase_result = await self.config.on_oracle(
                round_num, self.config.oracle_agents
            )
            result.oracle_forecasts = phase_result.get("forecasts_count", 0) if isinstance(phase_result, dict) else 0
            result.phase_results["oracle"] = phase_result

        else:
            # Default: run each agent's step for this phase
            await self._default_phase_execution(phase, round_num, relevant_agents)

    def _get_agents_for_phase(self, phase: Phase) -> List[MiroClawAgent]:
        """Get the agents that participate in a given phase."""
        if phase == Phase.CURATE:
            return [self.config.curator_agent] if self.config.curator_agent else []
        elif phase == Phase.ORACLE:
            return self.config.oracle_agents
        else:
            # All non-special agents participate in Research, Contribute, Vote
            return [
                a for a in self.agents
                if not a.is_curator and not a.is_oracle
            ]

    async def _default_phase_execution(
        self,
        phase: Phase,
        round_num: int,
        agents: List[MiroClawAgent],
    ):
        """Default phase execution: each agent receives a phase prompt.

        In production, this would invoke CAMEL Workforce task channels
        to distribute work. For now, it sends a phase-appropriate prompt
        to each agent.
        """
        phase_prompt = self._build_phase_prompt(phase, round_num)

        async def agent_step(agent: MiroClawAgent):
            try:
                msg = BaseMessage.make_user_message(
                    role_name="system",
                    content=phase_prompt,
                )
                response = agent.step(msg)
                return response
            except Exception as e:
                logger.warning(
                    f"Agent {agent.agent_id} failed in {phase.value}: {e}"
                )
                return None

        # Execute all agents in parallel for this phase
        await asyncio.gather(*[agent_step(a) for a in agents])

    @staticmethod
    def _build_phase_prompt(phase: Phase, round_num: int) -> str:
        """Build the environment prompt for a phase."""
        prompts = {
            Phase.RESEARCH: (
                f"Round {round_num} — RESEARCH PHASE\n\n"
                "You are now in the Research phase. You may:\n"
                "- Read the current state of the knowledge graph\n"
                "- Perform up to 3 web searches\n"
                "- Read up to 3 web pages\n"
                "- Consult the oracle (1 consultation)\n\n"
                "Gather evidence relevant to your position and the simulation's "
                "core questions. Select your single most important finding to "
                "add to the graph in the next phase."
            ),
            Phase.CONTRIBUTE: (
                f"Round {round_num} — CONTRIBUTE PHASE\n\n"
                "You are now in the Contribute phase. You may:\n"
                "- Add 1 structured triple to the knowledge graph\n"
                "- Compose a social media post\n\n"
                "Express your most important finding as a structured triple:\n"
                "(Subject Entity) —[RELATIONSHIP]-> (Object Entity)\n"
                "  {{ source_url, added_by_agent, added_round }}\n\n"
                "You may also compose a social media post referencing your "
                "research or the oracle's advice."
            ),
            Phase.VOTE: (
                f"Round {round_num} — VOTE PHASE\n\n"
                "You are now in the Vote phase. You may:\n"
                "- Upvote or downvote new triples added by other agents this round\n\n"
                "Vote based on whether the evidence supports or contradicts "
                "your explanatory framework. Each triple can receive one vote "
                "from you per round."
            ),
            Phase.CURATE: (
                f"Round {round_num} — CURATE PHASE\n\n"
                "You are the Curator agent. Your tasks:\n"
                "- Merge near-duplicate triples (cosine similarity > threshold)\n"
                "- Flag contested triples (high upvotes AND high downvotes)\n"
                "- Prune low-engagement triples below the vote threshold\n"
                "- Enforce graph size ceiling\n\n"
                "Remember: you evaluate engagement and redundancy, NEVER factual accuracy. "
                "Contested triples are protected from pruning."
            ),
            Phase.ORACLE: (
                f"Round {round_num} — ORACLE FORECAST PHASE\n\n"
                "You are an Oracle agent. Produce calibrated probability "
                "estimates on the simulation's core questions.\n\n"
                "For each question, provide:\n"
                "- Probability estimate (0.0-1.0)\n"
                "- Reasoning\n"
                "- Confidence level\n\n"
                "Your forecasts should be calibrated — when you say 70%, "
                "it should mean 70%."
            ),
        }
        return prompts.get(phase, f"Round {round_num} — {phase.value.upper()} PHASE")
