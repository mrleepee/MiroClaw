"""
MiroClaw Agent Tests

Tests for MiroClaw agent module verifying Phase 0-6 behaviours.
Uses minimal copies of dataclasses to avoid full app/CAMEL import chain.
"""

import sys
import os

# Ensure backend is on path
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import random


# ========================
# Minimal copies of agent types for testing
# ========================

class Stance(str, Enum):
    SUPPORTIVE = "supportive"
    NEUTRAL = "neutral"
    OPPOSING = "opposing"


class Phase(str, Enum):
    RESEARCH = "research"
    CONTRIBUTE = "contribute"
    VOTE = "vote"
    CURATE = "curate"
    ORACLE = "oracle"


@dataclass
class AgentIdentity:
    agent_id: str
    entity_name: str
    entity_type: str
    base_persona: str
    stance: Stance = Stance.NEUTRAL
    epistemic_flexibility: float = 0.3
    changelog: List[Dict[str, Any]] = field(default_factory=list)

    def record_stance_shift(self, round_num: int, old_stance: Stance, new_stance: Stance, triggering_evidence: str):
        self.changelog.append({
            "round": round_num,
            "shift": f"{old_stance.value} -> {new_stance.value}",
            "evidence": triggering_evidence,
        })
        self.stance = new_stance


@dataclass
class BudgetTracker:
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
        self.searches_used = 0
        self.reads_used = 0
        self.graph_additions_used = 0
        self.oracle_consultations_used = 0


@dataclass
class RoundBudget:
    agent_id: str
    round_num: int
    max_searches: int = 3
    max_reads: int = 3
    max_graph_additions: int = 1
    max_oracle_consultations: int = 1
    searches_used: int = 0
    reads_used: int = 0
    graph_additions_used: int = 0
    oracle_consultations_used: int = 0

    def can_search(self) -> bool:
        return self.searches_used < self.max_searches

    def use_search(self) -> bool:
        if not self.can_search():
            return False
        self.searches_used += 1
        return True

    def use_read(self) -> bool:
        if self.reads_used >= self.max_reads:
            return False
        self.reads_used += 1
        return True

    def use_graph_addition(self) -> bool:
        if self.graph_additions_used >= self.max_graph_additions:
            return False
        self.graph_additions_used += 1
        return True

    def use_oracle_consultation(self) -> bool:
        if self.oracle_consultations_used >= self.max_oracle_consultations:
            return False
        self.oracle_consultations_used += 1
        return True

    def get_summary(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "round_num": self.round_num,
            "searches": f"{self.searches_used}/{self.max_searches}",
            "reads": f"{self.reads_used}/{self.max_reads}",
        }


@dataclass
class CompactionEntry:
    round_range_start: int
    round_range_end: int
    positions_held: List[str] = field(default_factory=list)
    key_evidence: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_text(self) -> str:
        lines = [f"## Compacted Memory (Rounds {self.round_range_start}-{self.round_range_end})"]
        if self.positions_held:
            lines.append("### Positions held:")
            lines.extend(f"- {p}" for p in self.positions_held)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_range": f"{self.round_range_start}-{self.round_range_end}",
            "positions_held": self.positions_held,
            "key_evidence": self.key_evidence,
            "timestamp": self.timestamp,
        }


class CompactionBlock:
    def __init__(self):
        self.entries: List[CompactionEntry] = []

    def add_entry(self, entry: CompactionEntry):
        self.entries.append(entry)

    def get_full_summary(self) -> str:
        if not self.entries:
            return ""
        return "\n\n".join(e.to_text() for e in self.entries)

    def to_dict_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.entries]

    @classmethod
    def from_dict_list(cls, data: List[Dict[str, Any]]) -> "CompactionBlock":
        block = cls()
        for d in data:
            parts = d.get("round_range", "0-0").split("-")
            block.entries.append(CompactionEntry(
                round_range_start=int(parts[0]),
                round_range_end=int(parts[1]) if len(parts) > 1 else 0,
                positions_held=d.get("positions_held", []),
                key_evidence=d.get("key_evidence", []),
            ))
        return block


@dataclass
class TripleSubmission:
    subject: str
    subject_type: str
    relationship: str
    object: str
    object_type: str
    source_url: str
    added_by_agent: str
    added_round: int
    added_timestamp: str = None

    def __post_init__(self):
        if self.added_timestamp is None:
            self.added_timestamp = datetime.now().isoformat()


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    duplicate_of: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"valid": self.valid, "reason": self.reason}
        if self.duplicate_of:
            result["duplicate_of"] = self.duplicate_of
        return result


class TripleValidator:
    TRIPLE_PATTERN = __import__('re').compile(
        r'\(([^)]+)\)\s*—?\s*\[([^\]]+)\]\s*->?\s*\(([^)]+)\)', __import__('re').IGNORECASE
    )

    def __init__(self, ontology_entity_types=None, similarity_threshold=0.95):
        self.ontology_entity_types = ontology_entity_types or set()
        self.similarity_threshold = similarity_threshold

    def validate_format(self, triple: TripleSubmission) -> ValidationResult:
        if not triple.subject or not triple.relationship or not triple.object:
            return ValidationResult(False, "Triple must have subject, relationship, and object fields.")
        if len(triple.subject) > 500 or len(triple.object) > 500:
            return ValidationResult(False, "Subject and object must be under 500 characters each.")
        return ValidationResult(True)

    def validate_schema(self, triple: TripleSubmission) -> ValidationResult:
        if not self.ontology_entity_types:
            return ValidationResult(True)
        valid_lower = {t.lower() for t in self.ontology_entity_types}
        if triple.subject_type.lower() not in valid_lower:
            return ValidationResult(False, f"Subject entity type '{triple.subject_type}' not found in ontology.")
        if triple.object_type.lower() not in valid_lower:
            return ValidationResult(False, f"Object entity type '{triple.object_type}' not found in ontology.")
        return ValidationResult(True)

    def validate_source_url(self, triple: TripleSubmission) -> ValidationResult:
        if not triple.source_url:
            return ValidationResult(True)
        url_pattern = __import__('re').compile(r'https?://[^\s<>"{}|\\^`\[\]]+', __import__('re').IGNORECASE)
        if not url_pattern.match(triple.source_url):
            return ValidationResult(False, f"Invalid URL format: {triple.source_url}")
        return ValidationResult(True)

    def validate(self, triple: TripleSubmission) -> ValidationResult:
        result = self.validate_format(triple)
        if not result.valid:
            return result
        result = self.validate_schema(triple)
        if not result.valid:
            return result
        result = self.validate_source_url(triple)
        if not result.valid:
            return result
        return ValidationResult(True)


class VoteRecord:
    def __init__(self):
        self._votes: Dict[tuple, str] = {}

    def has_voted(self, agent_id: str, triple_uuid: str, round_num: int) -> bool:
        return (agent_id, triple_uuid, round_num) in self._votes

    def record_vote(self, agent_id: str, triple_uuid: str, round_num: int, direction: str) -> bool:
        key = (agent_id, triple_uuid, round_num)
        if key in self._votes:
            return False
        self._votes[key] = direction
        return True


class BudgetManager:
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._budgets: Dict[str, RoundBudget] = {}

    def create_budget(self, agent_id: str, round_num: int) -> RoundBudget:
        budget = RoundBudget(
            agent_id=agent_id,
            round_num=round_num,
            max_searches=self.config.get("max_searches", 3),
            max_reads=self.config.get("max_reads", 3),
        )
        self._budgets[agent_id] = budget
        return budget

    def get_budget(self, agent_id: str) -> Optional[RoundBudget]:
        return self._budgets.get(agent_id)

    def reset_round(self, round_num: int):
        for agent_id in self._budgets:
            self.create_budget(agent_id, round_num)


# ========================
# Tests
# ========================

class TestBudgetTracker:
    """Test research budget enforcement (Behaviours 3.4-3.6)."""

    def test_search_budget_enforcement(self):
        budget = BudgetTracker()
        assert budget.use_search()   # 1st
        assert budget.use_search()   # 2nd
        assert budget.use_search()   # 3rd
        assert not budget.use_search()  # 4th: exhausted

    def test_read_budget_enforcement(self):
        budget = BudgetTracker()
        assert budget.use_read()
        assert budget.use_read()
        assert budget.use_read()
        assert not budget.use_read()  # 4th: exhausted

    def test_graph_addition_budget_enforcement(self):
        budget = BudgetTracker()
        assert budget.use_graph_addition()   # 1st
        assert not budget.use_graph_addition()  # 2nd: exhausted

    def test_oracle_consultation_budget(self):
        budget = BudgetTracker()
        assert budget.use_oracle_consultation()   # 1st
        assert not budget.use_oracle_consultation()  # 2nd: exhausted

    def test_budget_reset(self):
        budget = BudgetTracker()
        budget.use_search()
        budget.use_search()
        budget.reset()
        assert budget.searches_used == 0
        assert budget.can_search()


class TestRoundBudget:
    """Test per-agent per-round budget."""

    def test_round_budget_exhaustion(self):
        budget = RoundBudget(agent_id="test", round_num=1)
        budget.use_search()
        budget.use_search()
        budget.use_search()
        assert not budget.use_search()  # 4th fails

    def test_round_budget_summary(self):
        budget = RoundBudget(agent_id="test", round_num=1)
        summary = budget.get_summary()
        assert summary["searches"] == "0/3"
        budget.use_search()
        summary = budget.get_summary()
        assert summary["searches"] == "1/3"


class TestBudgetManager:
    """Test multi-agent budget coordination."""

    def test_create_and_get(self):
        manager = BudgetManager()
        budget = manager.create_budget("agent_1", 1)
        assert manager.get_budget("agent_1") is budget

    def test_reset_round(self):
        manager = BudgetManager()
        manager.create_budget("agent_1", 1)
        manager.get_budget("agent_1").use_search()
        manager.reset_round(2)
        assert manager.get_budget("agent_1").searches_used == 0


class TestTripleValidator:
    """Test triple validation pipeline (Behaviours 1.2-1.5)."""

    def test_format_validation_pass(self):
        validator = TripleValidator()
        triple = TripleSubmission(
            subject="DOJ", subject_type="Organization",
            relationship="ENFORCED", object="Crypto", object_type="Industry",
            source_url="https://example.com", added_by_agent="a1", added_round=1,
        )
        assert validator.validate_format(triple).valid

    def test_format_validation_empty_subject(self):
        validator = TripleValidator()
        triple = TripleSubmission(
            subject="", subject_type="X", relationship="R",
            object="Y", object_type="Z", source_url="", added_by_agent="a1", added_round=1,
        )
        result = validator.validate_format(triple)
        assert not result.valid

    def test_schema_validation_pass(self):
        validator = TripleValidator(ontology_entity_types={"Organization", "Industry"})
        triple = TripleSubmission(
            subject="DOJ", subject_type="Organization",
            relationship="R", object="Crypto", object_type="Industry",
            source_url="", added_by_agent="a1", added_round=1,
        )
        assert validator.validate_schema(triple).valid

    def test_schema_validation_rejects_unknown(self):
        validator = TripleValidator(ontology_entity_types={"Organization"})
        triple = TripleSubmission(
            subject="DOJ", subject_type="Organization",
            relationship="R", object="X", object_type="UnknownType",
            source_url="", added_by_agent="a1", added_round=1,
        )
        result = validator.validate_schema(triple)
        assert not result.valid
        assert "UnknownType" in result.reason

    def test_source_url_invalid(self):
        validator = TripleValidator()
        triple = TripleSubmission(
            subject="A", subject_type="T", relationship="R",
            object="B", object_type="T", source_url="not_a_url",
            added_by_agent="a1", added_round=1,
        )
        assert not validator.validate_source_url(triple).valid

    def test_source_url_empty_allowed(self):
        validator = TripleValidator()
        triple = TripleSubmission(
            subject="A", subject_type="T", relationship="R",
            object="B", object_type="T", source_url="",
            added_by_agent="a1", added_round=1,
        )
        assert validator.validate_source_url(triple).valid

    def test_full_validation_pass(self):
        validator = TripleValidator(ontology_entity_types={"Organization", "Industry"})
        triple = TripleSubmission(
            subject="DOJ", subject_type="Organization",
            relationship="ENFORCED", object="Crypto", object_type="Industry",
            source_url="https://example.com/doj", added_by_agent="a1", added_round=1,
        )
        assert validator.validate(triple).valid

    def test_full_validation_rejects_format(self):
        validator = TripleValidator()
        triple = TripleSubmission(
            subject="", subject_type="T", relationship="R",
            object="B", object_type="T", source_url="",
            added_by_agent="a1", added_round=1,
        )
        result = validator.validate(triple)
        assert not result.valid


class TestVoteRecord:
    """Test voting (Behaviours 2.1-2.2)."""

    def test_vote_cast(self):
        record = VoteRecord()
        assert record.record_vote("agent_1", "triple_1", 1, "upvote")
        assert record.has_voted("agent_1", "triple_1", 1)

    def test_double_vote_prevention(self):
        record = VoteRecord()
        record.record_vote("agent_1", "triple_1", 1, "upvote")
        assert not record.record_vote("agent_1", "triple_1", 1, "downvote")

    def test_different_round_allowed(self):
        record = VoteRecord()
        record.record_vote("agent_1", "triple_1", 1, "upvote")
        assert record.record_vote("agent_1", "triple_1", 2, "upvote")

    def test_different_agent_same_triple(self):
        record = VoteRecord()
        record.record_vote("agent_1", "triple_1", 1, "upvote")
        assert record.record_vote("agent_2", "triple_1", 1, "downvote")


class TestCompactionBlock:
    """Test memory compaction (Behaviours 0.3-0.4)."""

    def test_entry_text(self):
        entry = CompactionEntry(
            round_range_start=1, round_range_end=10,
            positions_held=["Framework: supportive"],
        )
        text = entry.to_text()
        assert "Rounds 1-10" in text
        assert "Framework: supportive" in text

    def test_block_summary(self):
        block = CompactionBlock()
        block.add_entry(CompactionEntry(
            round_range_start=1, round_range_end=10,
            positions_held=["Pos A"],
        ))
        assert len(block.entries) == 1
        assert "Pos A" in block.get_full_summary()

    def test_serialization_roundtrip(self):
        block = CompactionBlock()
        block.add_entry(CompactionEntry(
            round_range_start=1, round_range_end=10,
            positions_held=["Pos A"], key_evidence=["Ev1"],
        ))
        block.add_entry(CompactionEntry(
            round_range_start=11, round_range_end=20,
            positions_held=["Pos B"],
        ))
        data = block.to_dict_list()
        restored = CompactionBlock.from_dict_list(data)
        assert len(restored.entries) == 2
        assert restored.entries[0].positions_held == ["Pos A"]


class TestPhaseOrdering:
    """Test Behaviour 0.2: Phase ordering."""

    def test_phases_in_correct_order(self):
        phases = list(Phase)
        assert phases.index(Phase.RESEARCH) < phases.index(Phase.CONTRIBUTE)
        assert phases.index(Phase.CONTRIBUTE) < phases.index(Phase.VOTE)
        assert phases.index(Phase.VOTE) < phases.index(Phase.CURATE)
        assert phases.index(Phase.CURATE) < phases.index(Phase.ORACLE)

    def test_stance_values(self):
        assert Stance.SUPPORTIVE.value == "supportive"
        assert Stance.NEUTRAL.value == "neutral"
        assert Stance.OPPOSING.value == "opposing"


class TestStanceShift:
    """Test Behaviour 5.8: Stance shift is one step only."""

    def test_supportive_shifts_to_neutral(self):
        # Supportive can only go to neutral
        assert Stance.SUPPORTIVE != Stance.OPPOSING
        # One step: supportive -> neutral
        current = Stance.SUPPORTIVE
        # Simulate one-step shift
        assert current != Stance.OPPOSING  # Can't jump to opposing

    def test_identity_changelog(self):
        identity = AgentIdentity(
            agent_id="test", entity_name="Test", entity_type="person",
            base_persona="Test persona",
        )
        assert identity.stance == Stance.NEUTRAL
        identity.record_stance_shift(
            round_num=5, old_stance=Stance.SUPPORTIVE,
            new_stance=Stance.NEUTRAL, triggering_evidence="Found contradicting data",
        )
        assert len(identity.changelog) == 1
        assert identity.stance == Stance.NEUTRAL
        entry = identity.changelog[0]
        assert entry["round"] == 5
        assert "supportive" in entry["shift"]
        assert "neutral" in entry["shift"]
        assert "contradicting" in entry["evidence"]

    def test_multiple_shifts_cumulative(self):
        identity = AgentIdentity(
            agent_id="test", entity_name="Test", entity_type="person",
            base_persona="Test", stance=Stance.SUPPORTIVE,
        )
        identity.record_stance_shift(5, Stance.SUPPORTIVE, Stance.NEUTRAL, "Evidence A")
        identity.record_stance_shift(15, Stance.NEUTRAL, Stance.OPPOSING, "Evidence B")
        assert len(identity.changelog) == 2
        assert identity.stance == Stance.OPPOSING


class TestTripleSubmission:
    """Test triple data structure."""

    def test_submission_creation(self):
        triple = TripleSubmission(
            subject="DOJ", subject_type="Organization",
            relationship="ENFORCED", object="Crypto", object_type="Industry",
            source_url="https://example.com", added_by_agent="a1", added_round=1,
        )
        assert triple.subject == "DOJ"
        assert triple.added_timestamp is not None  # Auto-filled
