"""
MiroClaw Agent Tools — FunctionTool factories

Wraps each tool class into CAMEL FunctionTool instances for registration
on MiroClawAgent(ChatAgent). Phase-aware tool assignment ensures agents
only have access to phase-appropriate actions.

Satisfies: R01 (CAMEL-native agents, tools via FunctionTool)
"""

from typing import List, Optional, TYPE_CHECKING

from camel.toolkits import FunctionTool

from ...utils.logger import get_logger

logger = get_logger('miroclaw.tools')

if TYPE_CHECKING:
    from .graph_write import GraphWriteTool
    from .voting import VotingTool
    from .research import ResearchTool
    from .oracle import OracleConsultationTool
    from .oasis_platform import OasisPlatformPlugin


# ── Phase: Research ──────────────────────────────────────────────


def create_search_tool(research_tool: "ResearchTool") -> List[FunctionTool]:
    """Create FunctionTool for web search (Research phase)."""
    def search(query: str) -> str:
        """Search the web for information relevant to your research.

        Args:
            query: Search query string.

        Returns:
            Search results as formatted text.
        """
        result = research_tool.search(query)
        if not result.get("success"):
            return f"Search failed: {result.get('error', 'unknown')}"
        entries = []
        for r in result.get("results", []):
            entries.append(f"- {r.get('title', 'No title')}: {r.get('url', '')}")
            if r.get("snippet"):
                entries.append(f"  {r['snippet']}")
        return "\n".join(entries) if entries else "No results found."

    return [FunctionTool(search)]


def create_extract_tool(research_tool: "ResearchTool") -> List[FunctionTool]:
    """Create FunctionTool for page extraction (Research phase)."""
    def extract(url: str) -> str:
        """Extract text content from a web page.

        Args:
            url: URL to extract content from.

        Returns:
            Extracted page text.
        """
        result = research_tool.extract(url)
        if not result.get("success"):
            return f"Extraction failed: {result.get('error', 'unknown')}"
        content = result.get("content", "")
        return content if content else "No content extracted."

    return [FunctionTool(extract)]


def create_get_graph_state_tool(research_tool: "ResearchTool", graph_service) -> List[FunctionTool]:
    """Create FunctionTool for reading graph state (Research phase)."""
    def get_graph_state(query: str = "") -> str:
        """Read the current state of the knowledge graph.

        Returns recent triples, contested triples, and graph statistics.
        Does not count against any budget.

        Args:
            query: Optional filter query for specific topics.

        Returns:
            Formatted summary of graph state.
        """
        result = research_tool.get_graph_state(graph_service, query)
        if not result.get("success"):
            return f"Failed to read graph state: {result.get('error', 'unknown')}"

        lines = ["=== Knowledge Graph State ==="]
        stats = result.get("graph_stats", {})
        if stats:
            lines.append(f"Total agent triples: {stats.get('total_agent_triples', 0)}")
            lines.append(f"Pending: {stats.get('pending', 0)}, Contested: {stats.get('contested', 0)}, Pruned: {stats.get('pruned', 0)}")

        recent = result.get("recent_triples", [])
        if recent:
            lines.append(f"\n--- Recent Triples ({len(recent)}) ---")
            for t in recent[:10]:
                lines.append(f"  ({t.get('subject', '?')}) -[{t.get('relationship', '?')}]-> ({t.get('object', '?')}) [{t.get('status', '?')}]")

        contested = result.get("contested_triples", [])
        if contested:
            lines.append(f"\n--- Contested Triples ({len(contested)}) ---")
            for t in contested[:5]:
                lines.append(f"  ({t.get('subject', '?')}) -[{t.get('relationship', '?')}]-> ({t.get('object', '?')}) up:{t.get('upvotes', 0)} down:{t.get('downvotes', 0)}")

        return "\n".join(lines)

    return [FunctionTool(get_graph_state)]


def create_consult_oracle_tool(oracle_tool: "OracleConsultationTool", agent_id: str, round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for oracle consultation (Research phase)."""
    def consult_oracle(question: str) -> str:
        """Consult an Oracle agent for a calibrated probability estimate.

        Limited to 1 consultation per round. The oracle returns a
        probability estimate with reasoning.

        Args:
            question: The question to ask the oracle.

        Returns:
            Probability estimate and reasoning.
        """
        result = oracle_tool.consult(
            agent_id=agent_id,
            question=question,
            round_num=round_num,
        )
        if not result.get("success"):
            return f"Oracle consultation failed: {result.get('error', 'unknown')}"

        prob = result.get("probability", "N/A")
        reasoning = result.get("reasoning", "No reasoning provided")
        confidence = result.get("confidence", "N/A")
        return f"Oracle probability: {prob}\nConfidence: {confidence}\nReasoning: {reasoning}"

    return [FunctionTool(consult_oracle)]


# ── Phase: Contribute ─────────────────────────────────────────────


def create_add_triple_tool(graph_write_tool: "GraphWriteTool", agent_id: str, round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for adding triples (Contribute phase)."""
    def add_triple(
        subject: str,
        subject_type: str,
        relationship: str,
        object: str,
        object_type: str,
        source_url: str,
    ) -> str:
        """Add a structured triple to the knowledge graph.

        Limited to 1 triple per round. Must be a structured triple, not free text.

        Args:
            subject: Subject entity name.
            subject_type: Subject entity type (from ontology).
            relationship: Relationship type between subject and object.
            object: Object entity name.
            object_type: Object entity type (from ontology).
            source_url: URL where the evidence was found.

        Returns:
            Success or validation error message.
        """
        result = graph_write_tool.add_triple(
            subject=subject,
            subject_type=subject_type,
            relationship=relationship,
            object=object,
            object_type=object_type,
            source_url=source_url,
            added_by_agent=agent_id,
            added_round=round_num,
        )
        if result.get("success"):
            return "Triple added successfully."
        validation = result.get("validation", {})
        return f"Triple rejected: {validation.get('reason', 'unknown reason')}"

    return [FunctionTool(add_triple)]


def create_post_tool(oasis_plugin: "OasisPlatformPlugin", agent_id: int) -> List[FunctionTool]:
    """Create FunctionTool for social media posting (Contribute phase)."""
    def create_post(content: str, platform: str = "twitter") -> str:
        """Create a post on the social media platform.

        Args:
            content: Post content text.
            platform: Platform to post on ("twitter" or "reddit").

        Returns:
            Success or error message.
        """
        result = oasis_plugin.create_post(
            agent_id=agent_id,
            content=content,
            platform=platform,
        )
        if result.get("success"):
            return f"Post created (id: {result.get('post_id', 'unknown')})"
        return f"Post failed: {result.get('error', 'unknown')}"

    return [FunctionTool(create_post)]


# ── Phase: Vote ──────────────────────────────────────────────────


def create_upvote_tool(voting_tool: "VotingTool", agent_id: str, round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for upvoting triples (Vote phase)."""
    def upvote(triple_uuid: str) -> str:
        """Upvote a triple in the knowledge graph.

        Args:
            triple_uuid: UUID of the triple to upvote.

        Returns:
            Success or error message.
        """
        result = voting_tool.upvote(
            agent_id=agent_id,
            triple_uuid=triple_uuid,
            round_num=round_num,
        )
        if result.get("success"):
            return "Upvote recorded."
        return f"Upvote failed: {result.get('reason', result.get('error', 'unknown'))}"

    return [FunctionTool(upvote)]


def create_downvote_tool(voting_tool: "VotingTool", agent_id: str, round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for downvoting triples (Vote phase)."""
    def downvote(triple_uuid: str) -> str:
        """Downvote a triple in the knowledge graph.

        Args:
            triple_uuid: UUID of the triple to downvote.

        Returns:
            Success or error message.
        """
        result = voting_tool.downvote(
            agent_id=agent_id,
            triple_uuid=triple_uuid,
            round_num=round_num,
        )
        if result.get("success"):
            return "Downvote recorded."
        return f"Downvote failed: {result.get('reason', result.get('error', 'unknown'))}"

    return [FunctionTool(downvote)]


# ── Convenience: Create all tools for a phase ────────────────────


def create_research_tools(
    research_tool: "ResearchTool",
    agent_id: str,
    round_num: int,
    oracle_tool: Optional["OracleConsultationTool"] = None,
    graph_service=None,
) -> List[FunctionTool]:
    """Create all FunctionTools for the Research phase.

    Returns: search, extract, get_graph_state, and optionally consult_oracle.
    """
    tools: List[FunctionTool] = []
    tools.extend(create_search_tool(research_tool))
    tools.extend(create_extract_tool(research_tool))
    if graph_service:
        tools.extend(create_get_graph_state_tool(research_tool, graph_service))
    if oracle_tool:
        tools.extend(create_consult_oracle_tool(oracle_tool, agent_id, round_num))
    return tools


def create_contribute_tools(
    graph_write_tool: "GraphWriteTool",
    agent_id: str,
    round_num: int,
    oasis_plugin: Optional["OasisPlatformPlugin"] = None,
    oasis_agent_id: int = 0,
) -> List[FunctionTool]:
    """Create all FunctionTools for the Contribute phase.

    Returns: add_triple, and optionally create_post.
    """
    tools: List[FunctionTool] = []
    tools.extend(create_add_triple_tool(graph_write_tool, agent_id, round_num))
    if oasis_plugin:
        tools.extend(create_post_tool(oasis_plugin, oasis_agent_id))
    return tools


def create_vote_tools(
    voting_tool: "VotingTool",
    agent_id: str,
    round_num: int,
) -> List[FunctionTool]:
    """Create all FunctionTools for the Vote phase.

    Returns: upvote, downvote.
    """
    tools: List[FunctionTool] = []
    tools.extend(create_upvote_tool(voting_tool, agent_id, round_num))
    tools.extend(create_downvote_tool(voting_tool, agent_id, round_num))
    return tools


# ── Phase: Curate ────────────────────────────────────────────────


def create_merge_tool(curator_merge_tool: "CuratorMergeTool", round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for merging near-duplicate triples (Curate phase)."""
    def merge_near_duplicates() -> str:
        """Merge near-duplicate triples in the knowledge graph.

        Finds triples with cosine similarity above threshold and merges them,
        preserving provenance from both originals.

        Returns:
            Summary of merges performed.
        """
        result = curator_merge_tool.merge_near_duplicates(round_num)
        if result.get("success"):
            return f"Merged {result.get('merges_performed', 0)} near-duplicate triple(s)."
        return f"Merge failed: {result.get('error', 'unknown')}"

    return [FunctionTool(merge_near_duplicates)]


def create_prune_tool(curator_prune_tool: "CuratorPruneTool", round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for pruning low-value triples (Curate phase)."""
    def prune_low_value() -> str:
        """Prune triples below vote threshold after rounds of inactivity.

        Contested triples are never pruned. Pruned triples are soft-deleted
        and remain queryable for post-simulation analysis.

        Returns:
            Summary of prunes performed.
        """
        result = curator_prune_tool.prune_low_value(round_num)
        if result.get("success"):
            return f"Pruned {result.get('pruned', 0)} low-value triple(s)."
        return f"Prune failed: {result.get('error', 'unknown')}"

    return [FunctionTool(prune_low_value)]


def create_flag_contested_tool(curator_flag_tool: "CuratorFlagTool", round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for flagging contested triples (Curate phase)."""
    def flag_contested() -> str:
        """Flag triples where both upvotes and downvotes exceed thresholds.

        Contested triples represent genuine factual disputes and are
        protected from pruning regardless of net vote score.

        Returns:
            Summary of flags applied.
        """
        result = curator_flag_tool.flag_contested(round_num)
        if result.get("success"):
            return f"Flagged {result.get('flagged', 0)} contested triple(s)."
        return f"Flag failed: {result.get('error', 'unknown')}"

    return [FunctionTool(flag_contested)]


def create_ceiling_tool(curator_ceiling_tool: "CuratorCeilingTool", round_num: int) -> List[FunctionTool]:
    """Create FunctionTool for enforcing graph size ceiling (Curate phase)."""
    def enforce_ceiling() -> str:
        """Enforce graph size ceiling by pruning lowest-voted non-contested triples.

        Pruning continues until the triple count is at or below the ceiling.
        Contested triples are never pruned even when the ceiling is exceeded.

        Returns:
            Summary of ceiling enforcement.
        """
        result = curator_ceiling_tool.enforce_ceiling(round_num)
        if result.get("success"):
            return f"Ceiling enforcement pruned {result.get('ceiling_prunes', 0)} triple(s)."
        return f"Ceiling enforcement failed: {result.get('error', 'unknown')}"

    return [FunctionTool(enforce_ceiling)]


def create_curate_tools(
    curator_agent,
    round_num: int,
) -> List[FunctionTool]:
    """Create all FunctionTools for the Curate phase.

    Returns: merge_near_duplicates, prune_low_value, flag_contested, enforce_ceiling.
    """
    from .curator_tools import (
        CuratorMergeTool,
        CuratorPruneTool,
        CuratorFlagTool,
        CuratorCeilingTool,
    )

    tools: List[FunctionTool] = []
    tools.extend(create_merge_tool(CuratorMergeTool(curator_agent), round_num))
    tools.extend(create_prune_tool(CuratorPruneTool(curator_agent), round_num))
    tools.extend(create_flag_contested_tool(CuratorFlagTool(curator_agent), round_num))
    tools.extend(create_ceiling_tool(CuratorCeilingTool(curator_agent), round_num))
    return tools
