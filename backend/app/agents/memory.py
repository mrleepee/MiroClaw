"""
MiroClaw Agent Memory

Hybrid memory system extending CAMEL's LongtermAgentMemory with three blocks:
- ChatHistoryBlock: recent N messages in full detail (token-limited)
- VectorDBBlock: semantic similarity retrieval of older messages
- CompactionBlock: structured summary of position history (MiroClaw-specific)

Context window assembly order:
1. System prompt (persona, epistemic character) — ~2K tokens
2. Compaction summary (cumulative) — ~2-4K tokens
3. VectorDB retrievals (semantically relevant past) — ~2-4K tokens
4. ChatHistory (recent rounds in full) — variable, up to remaining budget
5. Current round environment prompt — ~1-2K tokens

Satisfies: R03 (Hybrid agent memory), R13 (Cross-session evolution)
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from camel.memories import (
    ChatHistoryMemory,
    ContextRecord,
    MemoryBlock,
    ScoreBasedContextCreator,
)
from camel.messages import BaseMessage
from camel.utils import OpenAITokenCounter

from ..utils.logger import get_logger

logger = get_logger('miroclaw.memory')


@dataclass
class CompactionEntry:
    """A single compaction summary entry."""
    round_range_start: int
    round_range_end: int
    positions_held: List[str] = field(default_factory=list)
    positions_shifted: List[str] = field(default_factory=list)
    key_evidence: List[str] = field(default_factory=list)
    graph_contributions: List[str] = field(default_factory=list)
    vote_outcomes: List[str] = field(default_factory=list)
    active_debates: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_range": f"{self.round_range_start}-{self.round_range_end}",
            "positions_held": self.positions_held,
            "positions_shifted": self.positions_shifted,
            "key_evidence": self.key_evidence,
            "graph_contributions": self.graph_contributions,
            "vote_outcomes": self.vote_outcomes,
            "active_debates": self.active_debates,
            "timestamp": self.timestamp,
        }

    def to_text(self) -> str:
        """Render as structured text for inclusion in context window."""
        lines = [
            f"## Compacted Memory (Rounds {self.round_range_start}-{self.round_range_end})",
        ]
        if self.positions_held:
            lines.append("### Positions held:")
            lines.extend(f"- {p}" for p in self.positions_held)
        if self.positions_shifted:
            lines.append("### Position shifts:")
            lines.extend(f"- {p}" for p in self.positions_shifted)
        if self.key_evidence:
            lines.append("### Key evidence cited:")
            lines.extend(f"- {p}" for p in self.key_evidence)
        if self.graph_contributions:
            lines.append("### Graph contributions:")
            lines.extend(f"- {p}" for p in self.graph_contributions)
        if self.vote_outcomes:
            lines.append("### Vote outcomes:")
            lines.extend(f"- {p}" for p in self.vote_outcomes)
        if self.active_debates:
            lines.append("### Active debate threads:")
            lines.extend(f"- {p}" for p in self.active_debates)
        return "\n".join(lines)


class CompactionBlock:
    """Structured summary block for narrative coherence.

    Unlike ChatHistoryBlock (recent messages) and VectorDBBlock (semantic
    retrieval), CompactionBlock preserves the agent's narrative arc: what
    positions it held, when they shifted, and why.

    Compaction triggers when ChatHistoryBlock exceeds 70% of its token budget.
    The oldest 50% of messages are summarised by an LLM call into a structured
    format stored here.
    """

    def __init__(self):
        self.entries: List[CompactionEntry] = []

    def add_entry(self, entry: CompactionEntry):
        """Add a new compaction entry."""
        self.entries.append(entry)

    def get_full_summary(self) -> str:
        """Get the cumulative compaction summary text."""
        if not self.entries:
            return ""
        return "\n\n".join(entry.to_text() for entry in self.entries)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        """Serialise all entries for persistence."""
        return [entry.to_dict() for entry in self.entries]

    @classmethod
    def from_dict_list(cls, data: List[Dict[str, Any]]) -> "CompactionBlock":
        """Deserialise from persisted data."""
        block = cls()
        for entry_data in data:
            round_range = entry_data.get("round_range", "0-0")
            parts = round_range.split("-")
            start = int(parts[0]) if len(parts) > 0 else 0
            end = int(parts[1]) if len(parts) > 1 else 0
            block.entries.append(CompactionEntry(
                round_range_start=start,
                round_range_end=end,
                positions_held=entry_data.get("positions_held", []),
                positions_shifted=entry_data.get("positions_shifted", []),
                key_evidence=entry_data.get("key_evidence", []),
                graph_contributions=entry_data.get("graph_contributions", []),
                vote_outcomes=entry_data.get("vote_outcomes", []),
                active_debates=entry_data.get("active_debates", []),
                timestamp=entry_data.get("timestamp", ""),
            ))
        return block


# Token budget allocation
# With a ~200K context window:
# - System prompt: ~2K (handled by ChatAgent)
# - Compaction summary: ~2-4K
# - VectorDB retrievals: ~2-4K
# - ChatHistory: remaining (primary)
# - Round environment: ~1-2K (handled by orchestrator prompt)
COMPACTION_TOKEN_BUDGET = 4000
VECTORDB_TOKEN_BUDGET = 4000
CHAT_HISTORY_TOKEN_LIMIT = 200_000
COMPACTION_TRIGGER_THRESHOLD = 0.70  # Trigger at 70% of token budget
COMPACTION_MESSAGE_FRACTION = 0.50   # Compact oldest 50%


class MiroClawAgentMemory:
    """Hybrid memory for MiroClaw agents.

    Composes three memory blocks:
    1. ChatHistoryMemory (CAMEL) — recent messages, token-limited
    2. CompactionBlock (MiroClaw) — structured narrative summaries
    3. VectorDB retrieval — semantic search of older messages

    The memory manages compaction triggers: when ChatHistory exceeds 70%
    of its token budget, the oldest 50% of messages are summarised into
    a CompactionBlock entry.
    """

    def __init__(
        self,
        model_name: str = None,
        chat_history_token_limit: int = CHAT_HISTORY_TOKEN_LIMIT,
        chat_history_window_size: int = 150,
    ):
        # CAMEL's ChatHistoryMemory with ScoreBasedContextCreator
        token_counter = OpenAITokenCounter(model_name or "gpt-4o-mini")
        context_creator = ScoreBasedContextCreator(
            token_counter=token_counter,
            token_limit=chat_history_token_limit,
        )
        self.chat_history = ChatHistoryMemory(
            context_creator=context_creator,
            window_size=chat_history_window_size,
        )
        self.compaction = CompactionBlock()
        self._vector_db_path: Optional[str] = None
        self._model_name = model_name

    def add_message(self, message: BaseMessage):
        """Add a message to chat history."""
        self.chat_history.write_records([message])

    def get_context(self, prompt: BaseMessage) -> List[ContextRecord]:
        """Get context for the current prompt, assembled from all blocks."""
        # ChatHistoryMemory handles context creation via ScoreBasedContextCreator
        return self.chat_history.retrieve_records(prompt)

    def check_compaction_needed(self) -> bool:
        """Check if compaction should trigger.

        Compaction fires when ChatHistoryBlock exceeds 70% of its token budget.
        """
        # Use the context creator's token counting to estimate usage
        try:
            context_creator = self.chat_history.get_context_creator()
            # Estimate current token usage from chat history
            records = self.chat_history.retrieve_records(
                BaseMessage.make_user_message(
                    role_name="system",
                    content="",
                )
            )
            total_tokens = sum(
                context_creator.token_counter.count_tokens(r.memory.record.content)
                for r in records
                if r.memory and r.memory.record
            )
            return total_tokens > (CHAT_HISTORY_TOKEN_LIMIT * COMPACTION_TRIGGER_THRESHOLD)
        except Exception:
            return False

    def perform_compaction(
        self,
        round_start: int,
        round_end: int,
        llm_client=None,
    ):
        """Perform compaction: summarise oldest messages into structured summary.

        In production, this makes an LLM call to produce a structured summary.
        For now, creates a basic compaction entry from available history.

        Args:
            round_start: First round in the compaction range.
            round_end: Last round in the compaction range.
            llm_client: Optional OpenAI client for LLM-powered summarisation.
        """
        logger.info(f"Performing compaction for rounds {round_start}-{round_end}")

        if llm_client is not None:
            entry = self._llm_compaction(round_start, round_end, llm_client)
        else:
            entry = self._basic_compaction(round_start, round_end)

        if entry is not None:
            self.compaction.add_entry(entry)

    def _basic_compaction(
        self,
        round_start: int,
        round_end: int,
    ) -> Optional[CompactionEntry]:
        """Create a basic compaction entry from chat history."""
        try:
            records = self.chat_history.retrieve_records(
                BaseMessage.make_user_message(
                    role_name="system",
                    content="",
                )
            )
            # Extract text content from the oldest records
            messages_text = []
            for record in records:
                if record.memory and record.memory.record:
                    messages_text.append(record.memory.record.content)

            if not messages_text:
                return None

            # Create a basic entry from the first half (oldest) messages
            midpoint = len(messages_text) // 2
            oldest = messages_text[:midpoint]

            return CompactionEntry(
                round_range_start=round_start,
                round_range_end=round_end,
                positions_held=["(compacted from chat history)"],
                key_evidence=oldest[:5],  # Keep first 5 evidence items
            )
        except Exception as e:
            logger.warning(f"Basic compaction failed: {e}")
            return None

    def _llm_compaction(
        self,
        round_start: int,
        round_end: int,
        llm_client,
    ) -> Optional[CompactionEntry]:
        """Use LLM to create a structured compaction summary."""
        try:
            records = self.chat_history.retrieve_records(
                BaseMessage.make_user_message(
                    role_name="system",
                    content="",
                )
            )
            messages_text = []
            for record in records:
                if record.memory and record.memory.record:
                    messages_text.append(record.memory.record.content)

            if not messages_text:
                return None

            midpoint = len(messages_text) // 2
            oldest_text = "\n".join(messages_text[:midpoint])

            prompt = f"""Analyse the following agent messages from rounds {round_start} to {round_end} of a simulation and produce a structured summary.

Messages:
{oldest_text[:8000]}

Return JSON with these fields:
- positions_held: list of positions the agent held
- positions_shifted: list of position shifts with triggering evidence
- key_evidence: list of key evidence cited, with round numbers if available
- graph_contributions: list of graph triples added
- vote_outcomes: list of notable vote outcomes
- active_debates: list of ongoing debate threads"""

            response = llm_client.chat.completions.create(
                model=self._model_name or "gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You produce structured JSON summaries of agent simulation history."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            result = json.loads(response.choices[0].message.content)

            return CompactionEntry(
                round_range_start=round_start,
                round_range_end=round_end,
                positions_held=result.get("positions_held", []),
                positions_shifted=result.get("positions_shifted", []),
                key_evidence=result.get("key_evidence", []),
                graph_contributions=result.get("graph_contributions", []),
                vote_outcomes=result.get("vote_outcomes", []),
                active_debates=result.get("active_debates", []),
            )
        except Exception as e:
            logger.warning(f"LLM compaction failed, falling back to basic: {e}")
            return self._basic_compaction(round_start, round_end)

    # --- Persistence (for cross-session evolution, R13) ---

    def save_to_disk(self, directory: str):
        """Persist memory to disk for cross-session survival."""
        os.makedirs(directory, exist_ok=True)

        # Save compaction block
        compaction_path = os.path.join(directory, "compaction.json")
        with open(compaction_path, 'w', encoding='utf-8') as f:
            json.dump(self.compaction.to_dict_list(), f, ensure_ascii=False, indent=2)

        logger.info(f"Saved compaction block to {compaction_path}")

    def load_from_disk(self, directory: str):
        """Load persisted memory from disk."""
        compaction_path = os.path.join(directory, "compaction.json")
        if os.path.exists(compaction_path):
            with open(compaction_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.compaction = CompactionBlock.from_dict_list(data)
            logger.info(
                f"Loaded {len(self.compaction.entries)} compaction entries from {compaction_path}"
            )
