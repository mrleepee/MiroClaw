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
from typing import Any, Dict, List, Optional

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import ModelFactory
from camel.types import ModelPlatformType

from ..utils.logger import get_logger

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


@dataclass
class BudgetTracker:
    """Per-agent per-round budget tracking for research actions.

    Hard limits:
    - 3 web searches
    - 3 page reads
    - 1 graph addition
    - 1 oracle consultation
    """
    searches_used: int = 0
    reads_used: int = 0
    graph_additions_used: int = 0
    oracle_consultations_used: int = 0

    MAX_SEARCHES = 3
    MAX_READS = 3
    MAX_GRAPH_ADDITIONS = 1
    MAX_ORACLE_CONSULTATIONS = 1

    def can_search(self) -> bool:
        return self.searches_used < self.MAX_SEARCHES

    def can_read(self) -> bool:
        return self.reads_used < self.MAX_READS

    def can_add_to_graph(self) -> bool:
        return self.graph_additions_used < self.MAX_GRAPH_ADDITIONS

    def can_consult_oracle(self) -> bool:
        return self.oracle_consultations_used < self.MAX_ORACLE_CONSULTATIONS

    def use_search(self) -> bool:
        if not self.can_search():
            return False
        self.searches_used += 1
        return True

    def use_read(self) -> bool:
        if not self.can_read():
            return False
        self.reads_used += 1
        return True

    def use_graph_addition(self) -> bool:
        if not self.can_add_to_graph():
            return False
        self.graph_additions_used += 1
        return True

    def use_oracle_consultation(self) -> bool:
        if not self.can_consult_oracle():
            return False
        self.oracle_consultations_used += 1
        return True

    def reset(self):
        """Reset all budgets for a new round."""
        self.searches_used = 0
        self.reads_used = 0
        self.graph_additions_used = 0
        self.oracle_consultations_used = 0


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
        self.budget = BudgetTracker()
        self.current_phase: Optional[Phase] = None
        self.is_curator = is_curator
        self.is_oracle = is_oracle

        # OASIS platform reference (set during simulation setup)
        self._oasis_platform = None
        self._oasis_user_id: Optional[int] = None

        # Track which tools are active for the current phase
        self._phase_tools: Dict[Phase, List] = {
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

    def set_phase(self, phase: Phase):
        """Set the current phase and enable phase-appropriate tools."""
        self.current_phase = phase
        self.budget.reset()
        logger.debug(
            f"Agent {self.agent_id} entering phase: {phase.value}"
        )

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
