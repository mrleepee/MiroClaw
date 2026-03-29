"""
MiroClaw Agent Module

CAMEL-native agents replacing OASIS SocialAgent with ChatAgent-based
phased round simulation, hybrid memory, and research capabilities.
"""

from .miroclaw_agent import MiroClawAgent
from .round_orchestrator import RoundOrchestrator, Phase
from .memory import MiroClawAgentMemory

__all__ = [
    "MiroClawAgent",
    "RoundOrchestrator",
    "Phase",
    "MiroClawAgentMemory",
]
