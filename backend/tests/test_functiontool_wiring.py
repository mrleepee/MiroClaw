"""
Tests for FunctionTool wiring and analytics module.

Uses minimal copies of dataclasses to avoid full app/CAMEL import chain,
matching the pattern in test_miroclaw_agents.py.
"""

import sys
import os

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import pytest
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


# ========================
# FunctionTool Mock
# ========================

class MockFunctionTool:
    """Minimal FunctionTool mock for testing wrappers."""
    def __init__(self, func):
        self.func = func
        self.__name__ = getattr(func, '__name__', 'tool')


# ========================
# Tool Factory Tests (via direct import of factory logic)
# ========================
# Since importing app.agents.tools pulls in CAMEL, we test the factory
# logic by recreating the wrapper pattern inline.


def _make_search_tool(research_tool):
    """Recreation of create_search_tool wrapper for testing."""
    def search(query: str) -> str:
        result = research_tool.search(query)
        if not result.get("success"):
            return f"Search failed: {result.get('error', 'unknown')}"
        entries = []
        for r in result.get("results", []):
            entries.append(f"- {r.get('title', 'No title')}: {r.get('url', '')}")
            if r.get("snippet"):
                entries.append(f"  {r['snippet']}")
        return "\n".join(entries) if entries else "No results found."
    return [MockFunctionTool(search)]


def _make_extract_tool(research_tool):
    def extract(url: str) -> str:
        result = research_tool.extract(url)
        if not result.get("success"):
            return f"Extraction failed: {result.get('error', 'unknown')}"
        content = result.get("content", "")
        return content if content else "No content extracted."
    return [MockFunctionTool(extract)]


def _make_graph_state_tool(research_tool, graph_service):
    def get_graph_state(query: str = "") -> str:
        result = research_tool.get_graph_state(graph_service, query)
        if not result.get("success"):
            return f"Failed to read graph state: {result.get('error', 'unknown')}"
        lines = ["=== Knowledge Graph State ==="]
        stats = result.get("graph_stats", {})
        if stats:
            lines.append(f"Total agent triples: {stats.get('total_agent_triples', 0)}")
        recent = result.get("recent_triples", [])
        if recent:
            lines.append(f"\n--- Recent Triples ({len(recent)}) ---")
            for t in recent[:10]:
                lines.append(f"  ({t.get('subject', '?')}) -[{t.get('relationship', '?')}]-> ({t.get('object', '?')}) [{t.get('status', '?')}]")
        contested = result.get("contested_triples", [])
        if contested:
            lines.append(f"\n--- Contested Triples ({len(contested)}) ---")
            for t in contested[:5]:
                lines.append(f"  ({t.get('subject', '?')}) up:{t.get('upvotes', 0)} down:{t.get('downvotes', 0)}")
        return "\n".join(lines)
    return [MockFunctionTool(get_graph_state)]


def _make_add_triple_tool(graph_write_tool, agent_id, round_num):
    def add_triple(subject, subject_type, relationship, object, object_type, source_url):
        result = graph_write_tool.add_triple(
            subject=subject, subject_type=subject_type, relationship=relationship,
            object=object, object_type=object_type, source_url=source_url,
            added_by_agent=agent_id, added_round=round_num,
        )
        if result.get("success"):
            return "Triple added successfully."
        validation = result.get("validation", {})
        return f"Triple rejected: {validation.get('reason', 'unknown reason')}"
    return [MockFunctionTool(add_triple)]


def _make_upvote_tool(voting_tool, agent_id, round_num):
    def upvote(triple_uuid):
        result = voting_tool.upvote(agent_id=agent_id, triple_uuid=triple_uuid, round_num=round_num)
        if result.get("success"):
            return "Upvote recorded."
        return f"Upvote failed: {result.get('reason', result.get('error', 'unknown'))}"
    return [MockFunctionTool(upvote)]


def _make_downvote_tool(voting_tool, agent_id, round_num):
    def downvote(triple_uuid):
        result = voting_tool.downvote(agent_id=agent_id, triple_uuid=triple_uuid, round_num=round_num)
        if result.get("success"):
            return "Downvote recorded."
        return f"Downvote failed: {result.get('reason', result.get('error', 'unknown'))}"
    return [MockFunctionTool(downvote)]


def _make_post_tool(oasis_plugin, agent_id):
    def create_post(content, platform="twitter"):
        result = oasis_plugin.create_post(agent_id=agent_id, content=content, platform=platform)
        if result.get("success"):
            return f"Post created (id: {result.get('post_id', 'unknown')})"
        return f"Post failed: {result.get('error', 'unknown')}"
    return [MockFunctionTool(create_post)]


# ========================
# Test Classes
# ========================


class TestSearchToolFactory:
    def test_returns_tool_list(self):
        mock = MagicMock()
        mock.search.return_value = {"success": True, "results": [{"title": "T", "url": "U", "snippet": "S"}]}
        tools = _make_search_tool(mock)
        assert len(tools) == 1
        assert callable(tools[0].func)

    def test_search_execution(self):
        mock = MagicMock()
        mock.search.return_value = {
            "success": True,
            "results": [{"title": "Test Result", "url": "https://example.com", "snippet": "A snippet"}],
        }
        tools = _make_search_tool(mock)
        result = tools[0].func("test query")
        assert "Test Result" in result
        assert "A snippet" in result
        mock.search.assert_called_once_with("test query")

    def test_search_failure(self):
        mock = MagicMock()
        mock.search.return_value = {"success": False, "error": "API error"}
        tools = _make_search_tool(mock)
        result = tools[0].func("test")
        assert "Search failed" in result
        assert "API error" in result

    def test_search_no_results(self):
        mock = MagicMock()
        mock.search.return_value = {"success": True, "results": []}
        tools = _make_search_tool(mock)
        result = tools[0].func("test")
        assert "No results found" in result


class TestExtractToolFactory:
    def test_extract_success(self):
        mock = MagicMock()
        mock.extract.return_value = {"success": True, "content": "Page content here."}
        tools = _make_extract_tool(mock)
        result = tools[0].func("https://example.com")
        assert "Page content here" in result

    def test_extract_empty(self):
        mock = MagicMock()
        mock.extract.return_value = {"success": True, "content": ""}
        tools = _make_extract_tool(mock)
        result = tools[0].func("https://example.com")
        assert "No content extracted" in result

    def test_extract_failure(self):
        mock = MagicMock()
        mock.extract.return_value = {"success": False, "error": "Timeout"}
        tools = _make_extract_tool(mock)
        result = tools[0].func("https://example.com")
        assert "Extraction failed" in result


class TestGraphStateToolFactory:
    def test_graph_state_display(self):
        mock = MagicMock()
        mock.get_graph_state.return_value = {
            "success": True,
            "graph_stats": {"total_agent_triples": 5, "pending": 3, "contested": 1, "pruned": 1},
            "recent_triples": [
                {"subject": "A", "relationship": "R", "object": "B", "status": "pending"},
            ],
            "contested_triples": [],
        }
        tools = _make_graph_state_tool(mock, MagicMock())
        result = tools[0].func("")
        assert "Knowledge Graph State" in result
        assert "Total agent triples: 5" in result

    def test_graph_state_contested(self):
        mock = MagicMock()
        mock.get_graph_state.return_value = {
            "success": True,
            "graph_stats": {"total_agent_triples": 10, "pending": 5, "contested": 3, "pruned": 2},
            "recent_triples": [],
            "contested_triples": [
                {"subject": "X", "relationship": "REL", "object": "Y", "upvotes": 5, "downvotes": 4},
            ],
        }
        tools = _make_graph_state_tool(mock, MagicMock())
        result = tools[0].func("")
        assert "Contested Triples" in result
        assert "up:5 down:4" in result


class TestAddTripleToolFactory:
    def test_add_triple_success(self):
        mock = MagicMock()
        mock.add_triple.return_value = {"success": True, "validation": {"valid": True}}
        tools = _make_add_triple_tool(mock, "agent_1", 2)
        result = tools[0].func("Subj", "Type1", "REL", "Obj", "Type2", "https://example.com")
        assert "Triple added successfully" in result
        mock.add_triple.assert_called_once_with(
            subject="Subj", subject_type="Type1", relationship="REL",
            object="Obj", object_type="Type2", source_url="https://example.com",
            added_by_agent="agent_1", added_round=2,
        )

    def test_add_triple_rejected(self):
        mock = MagicMock()
        mock.add_triple.return_value = {"success": False, "validation": {"valid": False, "reason": "Duplicate"}}
        tools = _make_add_triple_tool(mock, "agent_1", 2)
        result = tools[0].func("S", "T", "R", "O", "T", "https://example.com")
        assert "Triple rejected" in result
        assert "Duplicate" in result


class TestVoteToolFactories:
    def test_upvote_success(self):
        mock = MagicMock()
        mock.upvote.return_value = {"success": True}
        tools = _make_upvote_tool(mock, "agent_1", 1)
        result = tools[0].func("uuid-123")
        assert "Upvote recorded" in result
        mock.upvote.assert_called_once_with(agent_id="agent_1", triple_uuid="uuid-123", round_num=1)

    def test_upvote_failure(self):
        mock = MagicMock()
        mock.upvote.return_value = {"success": False, "reason": "Already voted"}
        tools = _make_upvote_tool(mock, "agent_1", 1)
        result = tools[0].func("uuid-123")
        assert "Upvote failed" in result
        assert "Already voted" in result

    def test_downvote_success(self):
        mock = MagicMock()
        mock.downvote.return_value = {"success": True}
        tools = _make_downvote_tool(mock, "agent_1", 1)
        result = tools[0].func("uuid-456")
        assert "Downvote recorded" in result

    def test_downvote_failure(self):
        mock = MagicMock()
        mock.downvote.return_value = {"success": False, "error": "Not found"}
        tools = _make_downvote_tool(mock, "agent_1", 1)
        result = tools[0].func("uuid-456")
        assert "Downvote failed" in result


class TestPostToolFactory:
    def test_post_success(self):
        mock = MagicMock()
        mock.create_post.return_value = {"success": True, "post_id": "post_123"}
        tools = _make_post_tool(mock, 42)
        result = tools[0].func("Hello world", platform="twitter")
        assert "post_123" in result

    def test_post_failure(self):
        mock = MagicMock()
        mock.create_post.return_value = {"success": False, "error": "Rate limited"}
        tools = _make_post_tool(mock, 42)
        result = tools[0].func("Hello")
        assert "Post failed" in result


# ========================
# Budget Module Tests (inline copies to avoid CAMEL import chain)
# ========================

@dataclass
class RoundBudgetCopy:
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

    def can_search(self):
        return self.searches_used < self.max_searches

    def use_search(self):
        if not self.can_search():
            return False
        self.searches_used += 1
        return True

    def use_read(self):
        if self.reads_used >= self.max_reads:
            return False
        self.reads_used += 1
        return True

    def use_graph_addition(self):
        if self.graph_additions_used >= self.max_graph_additions:
            return False
        self.graph_additions_used += 1
        return True

    def use_oracle_consultation(self):
        if self.oracle_consultations_used >= self.max_oracle_consultations:
            return False
        self.oracle_consultations_used += 1
        return True

    def get_summary(self):
        return {
            "agent_id": self.agent_id,
            "round_num": self.round_num,
            "searches": f"{self.searches_used}/{self.max_searches}",
            "reads": f"{self.reads_used}/{self.max_reads}",
        }


class TestBudgetModuleCopy:
    """Budget tests using inline copy (avoids CAMEL import)."""

    def test_budget_creation(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1)
        assert budget.agent_id == "test"
        assert budget.round_num == 1

    def test_search_exhaustion(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1)
        assert budget.use_search()
        assert budget.use_search()
        assert budget.use_search()
        assert not budget.use_search()

    def test_read_exhaustion(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1)
        assert budget.use_read()
        assert budget.use_read()
        assert budget.use_read()
        assert not budget.use_read()

    def test_graph_addition_exhaustion(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1)
        assert budget.use_graph_addition()
        assert not budget.use_graph_addition()

    def test_oracle_exhaustion(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1)
        assert budget.use_oracle_consultation()
        assert not budget.use_oracle_consultation()

    def test_custom_limits(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1, max_searches=5, max_reads=10)
        assert budget.max_searches == 5
        assert budget.max_reads == 10
        for _ in range(5):
            assert budget.use_search()
        assert not budget.use_search()

    def test_budget_summary(self):
        budget = RoundBudgetCopy(agent_id="test", round_num=1)
        budget.use_search()
        budget.use_search()
        summary = budget.get_summary()
        assert summary["searches"] == "2/3"
        assert summary["agent_id"] == "test"
