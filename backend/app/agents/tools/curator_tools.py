"""
Curator Tools

FunctionTools for the Curate phase of MiroClaw simulation.
These tools wrap the CuratorAgent's algorithmic operations as CAMEL FunctionTools
so they can be registered on agents during the Curate phase.

Satisfies: R09 (Curator agent), R01 (FunctionTool)
"""

from typing import Any, Dict, List

from ...utils.logger import get_logger

logger = get_logger('miroclaw.curator_tools')


class CuratorMergeTool:
    """FunctionTool wrapper for merging near-duplicate triples."""

    def __init__(self, curator_agent):
        self.curator = curator_agent

    def merge_near_duplicates(self, round_num: int) -> Dict[str, Any]:
        """Merge triples with cosine similarity above threshold.

        Args:
            round_num: Current round number

        Returns:
            Dict with merge count and details
        """
        try:
            count = self.curator._merge_near_duplicates(round_num)
            return {
                "success": True,
                "merges_performed": count,
                "message": f"Merged {count} near-duplicate triple(s) in round {round_num}",
            }
        except Exception as e:
            logger.error(f"Merge tool failed: {e}")
            return {"success": False, "error": str(e)}


class CuratorPruneTool:
    """FunctionTool wrapper for pruning low-value triples."""

    def __init__(self, curator_agent):
        self.curator = curator_agent

    def prune_low_value(self, round_num: int) -> Dict[str, Any]:
        """Prune triples below vote threshold after N rounds of inactivity.

        Args:
            round_num: Current round number

        Returns:
            Dict with prune count and details
        """
        try:
            count = self.curator._prune_low_value_triples(round_num)
            return {
                "success": True,
                "pruned": count,
                "message": f"Pruned {count} low-value triple(s) in round {round_num}",
            }
        except Exception as e:
            logger.error(f"Prune tool failed: {e}")
            return {"success": False, "error": str(e)}


class CuratorFlagTool:
    """FunctionTool wrapper for flagging contested triples."""

    def __init__(self, curator_agent):
        self.curator = curator_agent

    def flag_contested(self, round_num: int) -> Dict[str, Any]:
        """Flag triples where both upvotes and downvotes exceed thresholds.

        Args:
            round_num: Current round number

        Returns:
            Dict with flag count and details
        """
        try:
            count = self.curator._flag_contested_triples(round_num)
            return {
                "success": True,
                "flagged": count,
                "message": f"Flagged {count} contested triple(s) in round {round_num}",
            }
        except Exception as e:
            logger.error(f"Flag tool failed: {e}")
            return {"success": False, "error": str(e)}


class CuratorCeilingTool:
    """FunctionTool wrapper for enforcing graph size ceiling."""

    def __init__(self, curator_agent):
        self.curator = curator_agent

    def enforce_ceiling(self, round_num: int) -> Dict[str, Any]:
        """Enforce graph size ceiling by pruning lowest-voted non-contested triples.

        Args:
            round_num: Current round number

        Returns:
            Dict with ceiling enforcement count and details
        """
        try:
            count = self.curator._enforce_graph_ceiling(round_num)
            return {
                "success": True,
                "ceiling_prunes": count,
                "message": f"Ceiling enforcement pruned {count} triple(s) in round {round_num}",
            }
        except Exception as e:
            logger.error(f"Ceiling tool failed: {e}")
            return {"success": False, "error": str(e)}


def create_curator_tools(curator_agent) -> List:
    """Create all curator FunctionTools for a CuratorAgent instance.

    Returns a list of tool instances that can be registered during the Curate phase.
    """
    return [
        CuratorMergeTool(curator_agent),
        CuratorPruneTool(curator_agent),
        CuratorFlagTool(curator_agent),
        CuratorCeilingTool(curator_agent),
    ]
