"""
Agent Identity Module

Manages agent identity documents with cumulative changelogs
for cross-session evolution. Follows the SOUL.md pattern from
OpenClaw: persistent identity that evolves across simulation runs.

Satisfies: R12 (Epistemic flexibility), R13 (Cross-session evolution)
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .miroclaw_agent import AgentIdentity, Stance
from ..utils.logger import get_logger

logger = get_logger('miroclaw.identity')


class IdentityDocument:
    """Persistent identity document for an agent.

    Contains:
    - Base persona (from graph entity)
    - Current stance
    - Cumulative changelog across sessions
    - Epistemic flexibility value

    Can be saved/loaded for cross-session evolution.
    """

    def __init__(self, identity: AgentIdentity):
        self.identity = identity

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for persistence."""
        return {
            "agent_id": self.identity.agent_id,
            "entity_name": self.identity.entity_name,
            "entity_type": self.identity.entity_type,
            "stance": self.identity.stance.value,
            "epistemic_flexibility": self.identity.epistemic_flexibility,
            "base_persona": self.identity.base_persona,
            "changelog": self.identity.changelog,
        }

    def save(self, directory: str):
        """Save identity document to disk."""
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{self.identity.agent_id}_identity.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved identity for {self.identity.agent_id} to {path}")

    @classmethod
    def load(cls, agent_id: str, directory: str) -> Optional["IdentityDocument"]:
        """Load identity document from disk."""
        path = os.path.join(directory, f"{agent_id}_identity.json")
        if not os.path.exists(path):
            return None

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        identity = AgentIdentity(
            agent_id=data["agent_id"],
            entity_name=data["entity_name"],
            entity_type=data["entity_type"],
            base_persona=data["base_persona"],
            stance=Stance(data.get("stance", "neutral")),
            epistemic_flexibility=data.get("epistemic_flexibility", 0.3),
            changelog=data.get("changelog", []),
        )
        return cls(identity)

    @classmethod
    def load_or_create(
        cls,
        agent_id: str,
        entity_name: str,
        entity_type: str,
        persona: str,
        directory: str,
        epistemic_flexibility: float = None,
        stance: Stance = Stance.NEUTRAL,
    ) -> "IdentityDocument":
        """Load existing identity or create new one."""
        existing = cls.load(agent_id, directory)
        if existing is not None:
            logger.info(f"Loaded existing identity for {agent_id} ({len(existing.identity.changelog)} changelog entries)")
            return existing

        identity = AgentIdentity(
            agent_id=agent_id,
            entity_name=entity_name,
            entity_type=entity_type,
            base_persona=persona,
            stance=stance,
            epistemic_flexibility=epistemic_flexibility if epistemic_flexibility is not None else 0.3,
        )
        return cls(identity)
