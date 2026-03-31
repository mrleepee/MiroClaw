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
import json
import re
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
    # Triples added this round (populated during contribute, used during vote)
    round_triples: List[Dict[str, Any]] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "phase_results": self.phase_results,
            "triples_added": self.triples_added,
            "votes_cast": self.votes_cast,
            "curator_actions": self.curator_actions,
            "oracle_forecasts": self.oracle_forecasts,
            "round_triples": self.round_triples,
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
    # Graph access for querying triples during vote/curate phases
    graph_service: Optional[Any] = None
    graph_id: Optional[str] = None
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
        # Triples added during the current round's contribute phase
        self._pending_round_triples: List[Dict[str, Any]] = []

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
        self._pending_round_triples = []  # Reset for new round

        if self.config.on_round_start:
            self.config.on_round_start(round_num)

        # Phase 1: Research (parallel, per-agent)
        await self._execute_phase(Phase.RESEARCH, round_num, result)

        # Phase 2: Contribute (parallel, per-agent)
        await self._execute_phase(Phase.CONTRIBUTE, round_num, result)
        # Copy triples added during contribute to result for vote phase
        result.round_triples = list(self._pending_round_triples)

        # Phase 3: Vote (parallel, per-agent)
        await self._execute_phase(Phase.VOTE, round_num, result)

        # Phase 4: Curate (single curator agent)
        await self._execute_phase(Phase.CURATE, round_num, result)

        # Phase 5: Oracle Forecast (every N rounds AND on the last round)
        if (
            round_num % self.config.oracle_forecast_interval == 0
            or round_num == self.config.total_rounds
        ):
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
            await self._default_phase_execution(phase, round_num, relevant_agents, result)

    def _get_agents_for_phase(self, phase: Phase) -> List[MiroClawAgent]:
        """Get the agents that participate in a given phase."""
        if phase == Phase.CURATE:
            if self.config.curator_agent:
                return [self.config.curator_agent]
            # Fallback: use the first agent as curator
            if self.agents:
                return [self.agents[0]]
            return []
        elif phase == Phase.ORACLE:
            if self.config.oracle_agents:
                return self.config.oracle_agents
            # Fallback: all non-curator agents participate as oracles
            return [
                a for a in self.agents
                if not a.is_curator
            ]
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
        result: Optional[RoundResult] = None,
    ):
        """Default phase execution with text-based action parsing.

        Since MiniMax-M2.7 doesn't support OpenAI-style function/tool calling,
        we ask the LLM to output structured JSON actions, then parse and
        execute them directly against the tool instances.
        """
        # Build phase prompt — inject triple list for vote phase
        if phase == Phase.VOTE:
            phase_prompt = self._build_vote_prompt(round_num, result)
        else:
            phase_prompt = self._build_action_prompt(phase, round_num)

        phase_triples = 0
        phase_votes = 0
        phase_curator_actions = 0
        phase_oracle_forecasts = 0
        oracle_forecast_records: List[Dict[str, Any]] = []

        async def agent_step(agent: MiroClawAgent):
            nonlocal phase_triples, phase_votes
            nonlocal phase_curator_actions, phase_oracle_forecasts, oracle_forecast_records
            try:
                # Swap the agent's active tools for this phase
                agent._swap_active_tools(phase)

                msg = BaseMessage.make_user_message(
                    role_name="system",
                    content=phase_prompt,
                )
                logger.info(
                    f"Agent {agent.agent_id} starting {phase.value} phase "
                    f"(round {round_num}, tools={len(agent.tool_list)})"
                )
                response = agent.step(msg)

                # Parse and execute text actions from the response
                if response and hasattr(response, 'msgs') and response.msgs:
                    content = str(response.msgs[0].content) if response.msgs else ""
                    executed, oracle_records = self._parse_and_execute_actions(
                        agent, phase, round_num, content
                    )
                    if executed:
                        logger.info(
                            f"Agent {agent.agent_id} executed {executed} action(s) "
                            f"in {phase.value} phase (round {round_num})"
                        )
                        # Track results
                        if phase == Phase.CONTRIBUTE:
                            phase_triples += executed
                        elif phase == Phase.VOTE:
                            phase_votes += executed
                        elif phase == Phase.CURATE:
                            phase_curator_actions += executed
                        elif phase == Phase.ORACLE:
                            phase_oracle_forecasts += executed
                            oracle_forecast_records.extend(oracle_records)

                logger.info(
                    f"Agent {agent.agent_id} completed {phase.value} phase "
                    f"(round {round_num})"
                )
                return response
            except Exception as e:
                logger.warning(
                    f"Agent {agent.agent_id} failed in {phase.value}: {e}",
                    exc_info=True,
                )
                return None

        # Execute all agents in parallel for this phase
        await asyncio.gather(*[agent_step(a) for a in agents])

        # Update result counters
        if result:
            if phase == Phase.CONTRIBUTE:
                result.triples_added += phase_triples
            elif phase == Phase.VOTE:
                result.votes_cast += phase_votes
            elif phase == Phase.CURATE:
                result.curator_actions += phase_curator_actions
            elif phase == Phase.ORACLE:
                result.oracle_forecasts += phase_oracle_forecasts
                # Store oracle forecast records for persistence
                if oracle_forecast_records:
                    result.phase_results["oracle"] = oracle_forecast_records

    def _parse_and_execute_actions(
        self,
        agent: MiroClawAgent,
        phase: Phase,
        round_num: int,
        content: str,
    ) -> tuple[int, List[Dict[str, Any]]]:
        """Parse JSON actions from LLM text response and execute them.

        Returns a tuple of (number of actions successfully executed, oracle forecast records).
        """
        actions = self._extract_json_actions(content)
        executed = 0
        oracle_forecasts: List[Dict[str, Any]] = []

        for action in actions:
            tool_name = action.get("tool", action.get("action", ""))
            tool_name_lower = tool_name.lower().replace("-", "_").replace(" ", "_")
            params = action.get("params", action.get("parameters", {}))

            try:
                result = self._execute_action(
                    agent, phase, round_num, tool_name, params
                )
                if result:
                    executed += 1
                    logger.debug(
                        f"Agent {agent.agent_id} action '{tool_name}' result: "
                        f"{str(result)[:100]}"
                    )
                    # Capture oracle forecast records
                    if phase == Phase.ORACLE and tool_name_lower in ("forecast", "oracle_forecast"):
                        oracle_forecasts.append(result)
            except Exception as e:
                logger.warning(
                    f"Agent {agent.agent_id} action '{tool_name}' failed: {e}"
                )

        return executed, oracle_forecasts

    @staticmethod
    def _extract_json_actions(text: str) -> List[Dict[str, Any]]:
        """Extract JSON action blocks from LLM text response.

        Supports formats:
        - ```json ... ```
        - {"tool": "add_triple", "params": {...}}
        - [{"tool": "search", "params": {...}}, ...]
        """
        actions: List[Dict[str, Any]] = []

        # Try to find JSON blocks (code fences or raw)
        json_patterns = [
            r'```json\s*\n(.*?)\n\s*```',  # fenced
            r'```\s*\n(.*?)\n\s*```',       # generic fence
        ]

        json_str = None
        for pattern in json_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
                break

        # If no fenced block, try to find raw JSON
        if not json_str:
            # Look for array or object starting with { or [
            match = re.search(r'(\[[\s\S]*?\]|\{[\s\S]*?"(?:tool|action)"[\s\S]*?\})', text)
            if match:
                json_str = match.group(1).strip()

        if not json_str:
            return actions

        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                actions.extend(parsed)
            elif isinstance(parsed, dict):
                actions.append(parsed)
        except json.JSONDecodeError:
            # Try individual objects
            for match in re.finditer(r'\{[^{}]*"(?:tool|action)"[^{}]*\}', text):
                try:
                    actions.append(json.loads(match.group(0)))
                except json.JSONDecodeError:
                    continue

        return actions

    def _execute_action(
        self,
        agent: MiroClawAgent,
        phase: Phase,
        round_num: int,
        tool_name: str,
        params: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Execute a single parsed action using the agent's tool instances."""
        tool_name_lower = tool_name.lower().replace("-", "_").replace(" ", "_")

        # Research phase tools
        if phase == Phase.RESEARCH:
            if tool_name_lower in ("search", "web_search"):
                if agent._research_tool:
                    return agent._research_tool.search(
                        query=params.get("query", "")
                    )
            elif tool_name_lower in ("extract", "read_page"):
                if agent._research_tool:
                    return agent._research_tool.extract(
                        url=params.get("url", "")
                    )
            elif tool_name_lower in ("get_graph_state", "read_graph"):
                if agent._research_tool and agent._graph_service:
                    return agent._research_tool.get_graph_state(
                        agent._graph_service, params.get("query", "")
                    )

        # Contribute phase tools
        elif phase == Phase.CONTRIBUTE:
            if tool_name_lower in ("add_triple", "contribute_triple"):
                if agent._graph_write_tool:
                    result = agent._graph_write_tool.add_triple(
                        subject=params.get("subject", ""),
                        subject_type=params.get("subject_type", ""),
                        relationship=params.get("relationship", ""),
                        object=params.get("object", ""),
                        object_type=params.get("object_type", ""),
                        source_url=params.get("source_url", ""),
                        added_by_agent=agent.agent_id,
                        added_round=round_num,
                    )
                    # Track the triple for the vote phase
                    if result and result.get("success") and result.get("triple_uuid"):
                        self._pending_round_triples.append({
                            "uuid": result["triple_uuid"],
                            "subject": result.get("subject", ""),
                            "relationship": result.get("relationship", ""),
                            "object": result.get("object", ""),
                            "added_by_agent": agent.agent_id,
                        })
                    return result

        # Vote phase tools
        elif phase == Phase.VOTE:
            if tool_name_lower == "upvote":
                if agent._voting_tool:
                    result = agent._voting_tool.upvote(
                        agent_id=agent.agent_id,
                        triple_uuid=params.get("triple_uuid", ""),
                        round_num=round_num,
                    )
                    # Trigger epistemic flexibility check on vote
                    if result and result.get("success"):
                        triple_uuid = params.get("triple_uuid", "")
                        # Rolling for "supportive" direction when upvoting
                        agent.roll_epistemic_flexibility(
                            contradicting_evidence=f"Upvoted triple {triple_uuid}",
                            round_num=round_num,
                            direction="supportive",
                        )
                    return result
            elif tool_name_lower == "downvote":
                if agent._voting_tool:
                    result = agent._voting_tool.downvote(
                        agent_id=agent.agent_id,
                        triple_uuid=params.get("triple_uuid", ""),
                        round_num=round_num,
                    )
                    # Trigger epistemic flexibility check on vote
                    if result and result.get("success"):
                        triple_uuid = params.get("triple_uuid", "")
                        # Rolling for "opposing" direction when downvoting
                        agent.roll_epistemic_flexibility(
                            contradicting_evidence=f"Downvoted triple {triple_uuid}",
                            round_num=round_num,
                            direction="opposing",
                        )
                    return result

        # Curate phase tools
        elif phase == Phase.CURATE:
            if tool_name_lower in ("merge_triple", "merge"):
                return self._curate_merge(
                    agent, round_num,
                    source_uuid=params.get("source_uuid", ""),
                    target_uuid=params.get("target_uuid", ""),
                )
            elif tool_name_lower in ("prune_triple", "prune"):
                return self._curate_prune(
                    agent, round_num,
                    triple_uuid=params.get("triple_uuid", ""),
                )
            elif tool_name_lower in ("flag_contested", "flag"):
                return self._curate_flag(
                    agent, round_num,
                    triple_uuid=params.get("triple_uuid", ""),
                )

        # Oracle phase tools
        elif phase == Phase.ORACLE:
            if tool_name_lower in ("forecast", "oracle_forecast"):
                return self._oracle_forecast(
                    agent, round_num,
                    question=params.get("question", ""),
                    probability=params.get("probability", 0.5),
                    reasoning=params.get("reasoning", ""),
                )

        return None

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

    def _build_action_prompt(self, phase: Phase, round_num: int) -> str:
        """Build phase prompt with JSON action instructions.

        Since the LLM may not support native function/tool calling, we ask
        agents to respond with structured JSON actions that we parse and
        execute server-side.
        """
        base_prompt = self._build_phase_prompt(phase, round_num)

        action_instructions = {
            Phase.RESEARCH: (
                '\n\n## Response Format\n\n'
                'Respond with your reasoning, then output ONE JSON action block:\n'
                '```json\n'
                '{"tool": "search", "params": {"query": "your search query"}}\n'
                '```\n\n'
                'Available tools:\n'
                '- `search` — params: {"query": string}\n'
                '- `extract` — params: {"url": string}\n'
                '- `get_graph_state` — params: {"query": string} (optional filter)\n'
            ),
            Phase.CONTRIBUTE: (
                '\n\n## Response Format\n\n'
                'Based on your research and persona, output ONE JSON action block to add a triple:\n'
                '```json\n'
                '{"tool": "add_triple", "params": {\n'
                '  "subject": "Entity Name",\n'
                '  "subject_type": "Person|Organization|...",\n'
                '  "relationship": "RELATIONSHIP_TYPE",\n'
                '  "object": "Entity Name",\n'
                '  "object_type": "Person|Organization|Policy|...",\n'
                '  "source_url": ""\n'
                '}}\n'
                '```\n\n'
                'You MUST output exactly one add_triple action. The source_url can be empty string '
                'if you have no URL. Use entity types from: Person, Organization, Group, Policy, '
                'Event, CreativeWork, Place.\n'
            ),
            Phase.VOTE: (
                '\n\n## Response Format\n\n'
                'Respond with your reasoning, then output JSON action(s):\n'
                '```json\n'
                '[{"tool": "upvote", "params": {"triple_uuid": "..."}},\n'
                ' {"tool": "downvote", "params": {"triple_uuid": "..."}}]\n'
                '```\n\n'
                'Available tools:\n'
                '- `upvote` — params: {"triple_uuid": string}\n'
                '- `downvote` — params: {"triple_uuid": string}\n'
            ),
            Phase.CURATE: (
                '\n\n## Response Format\n\n'
                'Review the triples and output your curation decisions as JSON:\n'
                '```json\n'
                '[{"tool": "prune", "params": {"triple_uuid": "..."}},\n'
                ' {"tool": "merge", "params": {"source_uuid": "...", "target_uuid": "..."}},\n'
                ' {"tool": "flag", "params": {"triple_uuid": "..."}}]\n'
                '```\n\n'
                'Available tools:\n'
                '- `merge` — params: {"source_uuid": string, "target_uuid": string}\n'
                '- `prune` — params: {"triple_uuid": string}\n'
                '- `flag` — params: {"triple_uuid": string} (flag as contested)\n'
            ),
            Phase.ORACLE: (
                '\n\n## Response Format\n\n'
                'Output your calibrated forecasts as JSON:\n'
                '```json\n'
                '[{"tool": "oracle_forecast", "params": {\n'
                '  "question": "Will X happen by Y?",\n'
                '  "probability": 0.65,\n'
                '  "reasoning": "Based on evidence..."\n'
                '}}]\n'
                '```\n\n'
                'You MUST output at least one forecast. Probability must be between 0.0 and 1.0.\n'
            ),
        }

        return base_prompt + action_instructions.get(phase, "")

    def _build_vote_prompt(
        self,
        round_num: int,
        result: Optional[RoundResult] = None,
    ) -> str:
        """Build the vote phase prompt with the list of votable triples.

        Includes triple UUIDs so agents can reference them in upvote/downvote
        actions.
        """
        base = (
            f"Round {round_num} — VOTE PHASE\n\n"
            "You are now in the Vote phase. Review the new triples added by "
            "agents this round and vote on them.\n\n"
            "Vote based on whether the evidence supports or contradicts "
            "your explanatory framework. Each triple can receive one vote "
            "from you per round.\n\n"
            "**Do NOT vote on your own triples.**\n\n"
        )

        # List the triples from this round
        triples = self._pending_round_triples
        if triples:
            base += "## New Triples This Round\n\n"
            for i, t in enumerate(triples, 1):
                base += (
                    f"{i}. `UUID: {t['uuid']}`\n"
                    f"   ({t['subject']}) —[{t['relationship']}]-> ({t['object']})\n"
                    f"   Added by: {t['added_by_agent']}\n\n"
                )
        else:
            base += (
                "## No new triples this round\n\n"
                "No triples were added during the contribute phase. "
                "Output an empty vote action or skip voting.\n"
            )

        base += (
            '\n## Response Format\n\n'
            'Respond with your reasoning about each triple, then output JSON action(s):\n'
            '```json\n'
            '[{"tool": "upvote", "params": {"triple_uuid": "UUID_HERE"}},\n'
            ' {"tool": "downvote", "params": {"triple_uuid": "UUID_HERE"}}]\n'
            '```\n\n'
            'Available tools:\n'
            '- `upvote` — params: {"triple_uuid": string}\n'
            '- `downvote` — params: {"triple_uuid": string}\n'
        )

        return base

    # ── Curate helpers ────────────────────────────────────────────

    def _curate_merge(
        self,
        agent: MiroClawAgent,
        round_num: int,
        source_uuid: str,
        target_uuid: str,
    ) -> Dict[str, Any]:
        """Merge two similar triples."""
        if not self.config.graph_service:
            return {"success": False, "reason": "No graph service configured"}

        from ..services.local_graph.graph_service import MiroClawGraphWriteAPI
        api = MiroClawGraphWriteAPI(self.config.graph_service)

        source = api.get_triple(source_uuid)
        target = api.get_triple(target_uuid)
        if not source or not target:
            return {"success": False, "reason": "Triple not found"}

        # Merge: update target's upvotes (sum), mark source as merged
        api.update_triple_properties(source_uuid, {"status": "merged"})
        total_upvotes = (source.get("upvotes") or 0) + (target.get("upvotes") or 0)
        total_downvotes = (source.get("downvotes") or 0) + (target.get("downvotes") or 0)
        api.update_triple_properties(target_uuid, {
            "upvotes": total_upvotes,
            "downvotes": total_downvotes,
        })

        logger.info(
            f"Curator merged {source_uuid} into {target_uuid} (round {round_num})"
        )
        return {"success": True, "action": "merge"}

    def _curate_prune(
        self,
        agent: MiroClawAgent,
        round_num: int,
        triple_uuid: str,
    ) -> Dict[str, Any]:
        """Prune a low-engagement triple."""
        if not self.config.graph_service:
            return {"success": False, "reason": "No graph service configured"}

        from ..services.local_graph.graph_service import MiroClawGraphWriteAPI
        api = MiroClawGraphWriteAPI(self.config.graph_service)

        triple = api.get_triple(triple_uuid)
        if not triple:
            return {"success": False, "reason": "Triple not found"}

        # Don't prune contested triples
        if triple.get("status") == "contested":
            return {"success": False, "reason": "Contested triple is protected"}

        api.update_triple_status(triple_uuid, "pruned")
        logger.info(f"Curator pruned {triple_uuid} (round {round_num})")
        return {"success": True, "action": "prune"}

    def _curate_flag(
        self,
        agent: MiroClawAgent,
        round_num: int,
        triple_uuid: str,
    ) -> Dict[str, Any]:
        """Flag a triple as contested."""
        if not self.config.graph_service:
            return {"success": False, "reason": "No graph service configured"}

        from ..services.local_graph.graph_service import MiroClawGraphWriteAPI
        api = MiroClawGraphWriteAPI(self.config.graph_service)
        api.update_triple_status(triple_uuid, "contested")
        logger.info(f"Curator flagged {triple_uuid} as contested (round {round_num})")
        return {"success": True, "action": "flag_contested"}

    # ── Oracle helpers ────────────────────────────────────────────

    def _oracle_forecast(
        self,
        agent: MiroClawAgent,
        round_num: int,
        question: str,
        probability: float,
        reasoning: str,
    ) -> Dict[str, Any]:
        """Record an oracle forecast from an agent."""
        logger.info(
            f"Oracle forecast from {agent.agent_id} (round {round_num}): "
            f"P={probability:.2f} for '{question[:80]}...'"
        )
        return {
            "success": True,
            "action": "oracle_forecast",
            "agent_id": agent.agent_id,
            "round": round_num,
            "question": question,
            "probability": probability,
            "reasoning": reasoning,
        }
