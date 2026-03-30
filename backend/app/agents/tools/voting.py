"""
Voting Tools

FunctionTools for agents to upvote/downvote triples during the Vote phase.

Vote rules:
- Per-agent, per-triple, per-round (no double-voting)
- Votes may be weighted by agent's influence_weight
- Contested status auto-assigned when upvotes AND downvotes exceed threshold

Satisfies: R08 (Voting system)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger

logger = get_logger('miroclaw.voting')


class VoteRecord:
    """Tracks individual vote records to prevent double-voting."""

    def __init__(self):
        # Key: (agent_id, triple_uuid, round_num) -> vote direction
        self._votes: Dict[tuple, str] = {}

    def has_voted(
        self,
        agent_id: str,
        triple_uuid: str,
        round_num: int,
    ) -> bool:
        """Check if an agent has already voted on a triple this round."""
        return (agent_id, triple_uuid, round_num) in self._votes

    def record_vote(
        self,
        agent_id: str,
        triple_uuid: str,
        round_num: int,
        direction: str,
    ) -> bool:
        """Record a vote. Returns False if already voted.

        Args:
            agent_id: The voting agent's identifier.
            triple_uuid: The UUID of the triple being voted on.
            round_num: Current round number.
            direction: "upvote" or "downvote".

        Returns:
            True if vote was recorded, False if already voted.
        """
        key = (agent_id, triple_uuid, round_num)
        if key in self._votes:
            return False
        self._votes[key] = direction
        return True

    def get_round_votes(self, round_num: int) -> List[Dict[str, Any]]:
        """Get all votes for a specific round."""
        return [
            {
                "agent_id": key[0],
                "triple_uuid": key[1],
                "round": key[2],
                "direction": direction,
            }
            for key, direction in self._votes.items()
            if key[2] == round_num
        ]

    def clear_round(self, round_num: int):
        """Clear votes for a specific round (for testing)."""
        self._votes = {
            k: v for k, v in self._votes.items() if k[2] != round_num
        }


class VotingTool:
    """MiroClaw voting tool for upvoting/downvoting triples.

    Registered as CAMEL FunctionTools on MiroClawAgent instances.
    Only invocable during the Vote phase.
    """

    CONTESTED_UPVOTE_THRESHOLD = 3
    CONTESTED_DOWNVOTE_THRESHOLD = 3

    def __init__(
        self,
        graph_service,
        vote_record: Optional[VoteRecord] = None,
        contested_upvote_threshold: int = 3,
        contested_downvote_threshold: int = 3,
    ):
        # Wrap with MiroClawGraphWriteAPI for triple operations
        from ...services.local_graph.graph_service import MiroClawGraphWriteAPI
        if isinstance(graph_service, MiroClawGraphWriteAPI):
            self._api = graph_service
        else:
            self._api = MiroClawGraphWriteAPI(graph_service)
        self.graph_service = graph_service
        self.vote_record = vote_record or VoteRecord()
        self.contested_upvote_threshold = contested_upvote_threshold
        self.contested_downvote_threshold = contested_downvote_threshold

    def upvote(
        self,
        agent_id: str,
        triple_uuid: str,
        round_num: int,
        influence_weight: float = 1.0,
    ) -> Dict[str, Any]:
        """Upvote a triple.

        Args:
            agent_id: The voting agent's identifier.
            triple_uuid: UUID of the triple to upvote.
            round_num: Current round number.
            influence_weight: Optional weight for the vote.

        Returns:
            Dict with success status.
        """
        return self._cast_vote(
            agent_id=agent_id,
            triple_uuid=triple_uuid,
            round_num=round_num,
            direction="upvote",
            influence_weight=influence_weight,
        )

    def downvote(
        self,
        agent_id: str,
        triple_uuid: str,
        round_num: int,
        influence_weight: float = 1.0,
    ) -> Dict[str, Any]:
        """Downvote a triple."""
        return self._cast_vote(
            agent_id=agent_id,
            triple_uuid=triple_uuid,
            round_num=round_num,
            direction="downvote",
            influence_weight=influence_weight,
        )

    def _cast_vote(
        self,
        agent_id: str,
        triple_uuid: str,
        round_num: int,
        direction: str,
        influence_weight: float,
    ) -> Dict[str, Any]:
        """Cast a vote on a triple."""
        # Check for double-voting
        if self.vote_record.has_voted(agent_id, triple_uuid, round_num):
            return {
                "success": False,
                "reason": f"Agent {agent_id} has already voted on triple {triple_uuid} this round",
            }

        # Record the vote
        if not self.vote_record.record_vote(agent_id, triple_uuid, round_num, direction):
            return {"success": False, "reason": "Vote already recorded"}

        # Update triple vote counts in graph
        try:
            if direction == "upvote":
                self._api.increment_triple_votes(
                    triple_uuid, "upvotes", influence_weight
                )
            else:
                self._api.increment_triple_votes(
                    triple_uuid, "downvotes", influence_weight
                )

            # Check for contested status
            self._check_contested_status(triple_uuid)

            logger.debug(
                f"Vote recorded: {direction} by {agent_id} on {triple_uuid} "
                f"(round {round_num})"
            )
            return {"success": True, "direction": direction}

        except Exception as e:
            logger.error(f"Failed to record vote: {e}")
            return {"success": False, "error": str(e)}

    def _check_contested_status(self, triple_uuid: str):
        """Auto-assign contested status when both sides exceed threshold."""
        try:
            triple = self._api.get_triple(triple_uuid)
            if not triple:
                return

            upvotes = triple.get("upvotes", 0)
            downvotes = triple.get("downvotes", 0)
            current_status = triple.get("status", "pending")

            if (
                upvotes >= self.contested_upvote_threshold
                and downvotes >= self.contested_downvote_threshold
                and current_status != "contested"
            ):
                self._api.update_triple_status(triple_uuid, "contested")
                logger.info(
                    f"Triple {triple_uuid} marked as contested "
                    f"(upvotes={upvotes}, downvotes={downvotes})"
                )
        except Exception as e:
            logger.warning(f"Failed to check contested status: {e}")
