"""
MiroClaw Agent

CAMEL-native agent replacing OASIS SocialAgent. Built directly on
CAMEL's ChatAgent with MiroClaw-specific tools, hybrid memory,
and phased round participation.

Satisfies: R01 (CAMEL-native agents), R12 (epistemic flexibility)
"""

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.toolkits import FunctionTool
from camel.types import ModelPlatformType

from ..utils.logger import get_logger
from .tools.budget import RoundBudget, BudgetManager
from .tools import (
    create_research_tools,
    create_contribute_tools,
    create_vote_tools,
    create_curate_tools,
)

if TYPE_CHECKING:
    from .tools.graph_write import GraphWriteTool
    from .tools.voting import VotingTool
    from .tools.research import ResearchTool
    from .tools.oracle import OracleConsultationTool
    from .tools.oasis_platform import OasisPlatformPlugin

logger = get_logger('miroclaw.agent')


class Stance(str, Enum):
    """Agent stance positions — gradual shifts only (one step at a time)."""
    SUPPORTIVE = "supportive"
    NEUTRAL = "neutral"
    OPPOSING = "opposing"


class Phase(str, Enum):
    """Simulation round phases — strict ordering enforced."""
    RESEARCH = "research"
    CONTRIBUTE = "contribute"
    VOTE = "vote"
    CURATE = "curate"
    ORACLE = "oracle"


@dataclass
class AgentIdentity:
    """Agent identity document with cumulative changelog (SOUL.md pattern)."""
    agent_id: str
    entity_name: str
    entity_type: str
    base_persona: str
    stance: Stance = Stance.NEUTRAL
    epistemic_flexibility: float = 0.3
    changelog: List[Dict[str, Any]] = field(default_factory=list)

    def record_stance_shift(
        self,
        round_num: int,
        old_stance: Stance,
        new_stance: Stance,
        triggering_evidence: str,
    ):
        """Record a stance shift in the identity changelog."""
        entry = {
            "round": round_num,
            "shift": f"{old_stance.value} -> {new_stance.value}",
            "evidence": triggering_evidence,
        }
        self.changelog.append(entry)
        self.stance = new_stance


class MiroClawAgent(ChatAgent):
    """MiroClaw agent built on CAMEL's ChatAgent.

    Extends ChatAgent with:
    - MiroClaw-specific tools (research, graph write, vote, etc.)
    - Hybrid memory (ChatHistoryBlock + VectorDBBlock + CompactionBlock)
    - Phase-aware tool availability
    - Epistemic flexibility for stance shifts
    - Budget tracking per round
    - OASIS social platform as a posting plugin

    Unlike OASIS's SocialAgent, this agent participates in phased rounds
    (Research -> Contribute -> Vote -> Curate -> Oracle) coordinated by
    the RoundOrchestrator, not a flat round-robin loop.
    """

    def __init__(
        self,
        agent_id: str,
        entity_name: str,
        entity_type: str,
        persona: str,
        model: Any = None,
        api_key: str = None,
        base_url: str = None,
        model_name: str = None,
        epistemic_flexibility: float = None,
        stance: Stance = Stance.NEUTRAL,
        memory: Any = None,
        is_curator: bool = False,
        is_oracle: bool = False,
    ):
        # Build system message from persona and identity
        system_msg = BaseMessage.make_assistant_message(
            role_name=entity_name,
            content=persona,
        )

        # Initialise ChatAgent
        if model is not None:
            super().__init__(system_message=system_msg, model=model, memory=memory)
        elif api_key and base_url and model_name:
            # Set env vars for CAMEL's ModelFactory
            import os
            os.environ["OPENAI_API_KEY"] = api_key
            os.environ["OPENAI_API_BASE_URL"] = base_url
            _model = ModelFactory.create(
                model_platform=ModelPlatformType.OPENAI,
                model_type=model_name,
            )
            super().__init__(system_message=system_msg, model=_model, memory=memory)
        else:
            super().__init__(system_message=system_msg, memory=memory)

        # MiroClaw-specific fields
        self.agent_id = agent_id
        self.identity = AgentIdentity(
            agent_id=agent_id,
            entity_name=entity_name,
            entity_type=entity_type,
            base_persona=persona,
            stance=stance,
            epistemic_flexibility=(
                epistemic_flexibility
                if epistemic_flexibility is not None
                else self._default_flexibility()
            ),
        )
        self.current_phase: Optional[Phase] = None
        self.current_round: int = 0
        self.is_curator = is_curator
        self.is_oracle = is_oracle

        # Budget tracking (using shared RoundBudget from budget.py)
        self._budget_manager = BudgetManager()
        self.budget: Optional[RoundBudget] = None

        # Tool instances (set during simulation setup via register_tools)
        self._research_tool: Optional["ResearchTool"] = None
        self._graph_write_tool: Optional["GraphWriteTool"] = None
        self._voting_tool: Optional["VotingTool"] = None
        self._oracle_tool: Optional["OracleConsultationTool"] = None
        self._oasis_plugin: Optional["OasisPlatformPlugin"] = None
        self._graph_service = None

        # OASIS platform reference (set during simulation setup)
        self._oasis_platform = None
        self._oasis_user_id: Optional[int] = None

        # Phase -> FunctionTool mapping (populated by register_tools)
        self._phase_tools: Dict[Phase, List[FunctionTool]] = {
            Phase.RESEARCH: [],
            Phase.CONTRIBUTE: [],
            Phase.VOTE: [],
            Phase.CURATE: [],
            Phase.ORACLE: [],
        }

    @staticmethod
    def _default_flexibility() -> float:
        """Sample from the epistemic flexibility population distribution.

        Distribution:
        - ~20% entrenched (0.0-0.2)
        - ~50% resistant but persuadable (0.3-0.5)
        - ~25% open (0.6-0.8)
        - ~5% hyper-flexible (0.9-1.0)
        """
        roll = random.random()
        if roll < 0.20:
            return random.uniform(0.0, 0.2)
        elif roll < 0.70:
            return random.uniform(0.3, 0.5)
        elif roll < 0.95:
            return random.uniform(0.6, 0.8)
        else:
            return random.uniform(0.9, 1.0)

    def set_phase(self, phase: Phase, round_num: int = 0):
        """Set the current phase and swap active tools on the ChatAgent.

        Removes all phase tools then adds only the tools for the current phase.
        Also resets the per-round budget.
        """
        self.current_phase = phase
        if round_num > 0:
            self.current_round = round_num

        # Reset budget for new round
        self.budget = self._budget_manager.create_budget(
            self.agent_id, self.current_round
        )

        # Swap tools: remove all phase tools, then add current phase's tools
        self._swap_active_tools(phase)

        logger.debug(
            f"Agent {self.agent_id} entering phase: {phase.value} "
            f"(round {self.current_round}, "
            f"tools: {len(self._phase_tools.get(phase, []))})"
        )

    def register_tools(
        self,
        research_tool: Optional["ResearchTool"] = None,
        graph_write_tool: Optional["GraphWriteTool"] = None,
        voting_tool: Optional["VotingTool"] = None,
        oracle_tool: Optional["OracleConsultationTool"] = None,
        oasis_plugin: Optional["OasisPlatformPlugin"] = None,
        graph_service: Optional[Any] = None,
    ):
        """Register tool instances and create phase-appropriate FunctionTools.

        Call this during simulation setup after tool instances are created.
        Populates self._phase_tools with FunctionTool lists per phase.
        """
        self._research_tool = research_tool
        self._graph_write_tool = graph_write_tool
        self._voting_tool = voting_tool
        self._oracle_tool = oracle_tool
        self._oasis_plugin = oasis_plugin
        self._graph_service = graph_service

        # Research phase: search, extract, get_graph_state, consult_oracle
        if research_tool:
            self._phase_tools[Phase.RESEARCH] = create_research_tools(
                research_tool=research_tool,
                agent_id=self.agent_id,
                round_num=self.current_round,
                oracle_tool=oracle_tool,
                graph_service=graph_service,
            )

        # Contribute phase: add_triple, create_post
        if graph_write_tool:
            self._phase_tools[Phase.CONTRIBUTE] = create_contribute_tools(
                graph_write_tool=graph_write_tool,
                agent_id=self.agent_id,
                round_num=self.current_round,
                oasis_plugin=oasis_plugin,
                oasis_agent_id=self._oasis_user_id or 0,
            )

        # Vote phase: upvote, downvote
        if voting_tool:
            self._phase_tools[Phase.VOTE] = create_vote_tools(
                voting_tool=voting_tool,
                agent_id=self.agent_id,
                round_num=self.current_round,
            )

        # Curate phase: merge, prune, flag, ceiling (only for curator agents)
        # Non-curator agents get empty curate tools — curator runs separately
        if hasattr(self, '_is_curator') and self._is_curator:
            self._phase_tools[Phase.CURATE] = create_curate_tools(
                curator_agent=self,
                round_num=self.current_round,
            )

        # Oracle phase: consult_oracle (reuse research oracle tool)
        if oracle_tool and hasattr(self, '_is_oracle') and self._is_oracle:
            self._phase_tools[Phase.ORACLE] = create_research_tools(
                research_tool=research_tool,
                agent_id=self.agent_id,
                round_num=self.current_round,
                oracle_tool=oracle_tool,
                graph_service=graph_service,
            )

        logger.info(
            f"Agent {self.agent_id} tools registered: "
            f"research={len(self._phase_tools[Phase.RESEARCH])}, "
            f"contribute={len(self._phase_tools[Phase.CONTRIBUTE])}, "
            f"vote={len(self._phase_tools[Phase.VOTE])}, "
            f"curate={len(self._phase_tools[Phase.CURATE])}, "
            f"oracle={len(self._phase_tools[Phase.ORACLE])}"
        )

    def _swap_active_tools(self, phase: Phase):
        """Replace the ChatAgent's tool list with the tools for the given phase.

        CAMEL ChatAgent stores tools in self.tool_list. We rebuild the list
        for the current phase only.
        """
        phase_tools = self._phase_tools.get(phase, [])
        self.tool_list = list(phase_tools)

    def roll_epistemic_flexibility(
        self,
        contradicting_evidence: str,
        round_num: int,
    ) -> bool:
        """Roll against epistemic flexibility when encountering contradicting evidence.

        If successful, agent's stance shifts one step in the direction of the evidence.
        If failed, agent acknowledges evidence internally but maintains public stance.

        Returns True if stance shifted.
        """
        roll = random.random()
        if roll < self.identity.epistemic_flexibility:
            old_stance = self.identity.stance
            new_stance = self._shift_stance_one_step(old_stance)
            if new_stance != old_stance:
                self.identity.record_stance_shift(
                    round_num=round_num,
                    old_stance=old_stance,
                    new_stance=new_stance,
                    triggering_evidence=contradicting_evidence,
                )
                logger.info(
                    f"Agent {self.agent_id} shifted stance: "
                    f"{old_stance.value} -> {new_stance.value} "
                    f"(round {round_num}, flexibility={self.identity.epistemic_flexibility:.2f})"
                )
                return True
        return False

    @staticmethod
    def _shift_stance_one_step(current: Stance) -> Stance:
        """Shift stance one step. Gradual, never jumps (e.g., supportive -> opposing)."""
        if current == Stance.SUPPORTIVE:
            return Stance.NEUTRAL
        elif current == Stance.OPPOSING:
            return Stance.NEUTRAL
        else:  # NEUTRAL — no further shift possible without evidence direction
            return Stance.NEUTRAL

    def set_oasis_platform(self, platform, user_id: int):
        """Set the OASIS social platform reference for posting."""
        self._oasis_platform = platform
        self._oasis_user_id = user_id

    def create_social_post(self, content: str) -> bool:
        """Create a post on the OASIS social platform.

        This is the integration point with OASIS's Twitter/Reddit databases.
        The simulation loop is CAMEL-native; OASIS is used as a plugin for
        the social media interaction surface only.
        """
        if self._oasis_platform is None:
            logger.warning(f"Agent {self.agent_id}: no OASIS platform configured")
            return False
        # OASIS platform integration handled by the create_post tool
        return True

    def get_persona_with_identity(self) -> str:
        """Return the full persona including identity changelog for system prompt."""
        parts = [self.identity.base_persona]
        if self.identity.changelog:
            parts.append("\n### Position History")
            for entry in self.identity.changelog:
                parts.append(
                    f"- Round {entry['round']}: {entry['shift']} "
                    f"(evidence: {entry['evidence'][:100]}...)"
                )
        parts.append(f"\nCurrent stance: {self.identity.stance.value}")
        return "\n".join(parts)
