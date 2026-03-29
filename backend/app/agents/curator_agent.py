"""
Curator Agent

Non-posting agent responsible for maintaining knowledge graph quality.
Evaluates engagement (votes) and redundancy (similarity), NEVER factual accuracy.

Curator responsibilities:
- Merge near-duplicates (cosine similarity > threshold)
- Prune low-value triples (below vote threshold after N rounds)
- Flag contested triples (high upvotes AND high downvotes)
- Enforce graph size ceiling

Curator constraints:
- NEVER evaluates factual accuracy
- Contested triples are protected from pruning
- Pruned triples are soft-deleted to pruned_triples collection
- All actions logged with reasoning for audit trail

Satisfies: R09 (Curator agent)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .miroclaw_agent import MiroClawAgent
from ..utils.logger import get_logger

logger = get_logger('miroclaw.curator')


@dataclass
class CuratorAction:
    """Audit trail entry for a curator action."""
    action_type: str  # "merge", "prune", "flag", "ceiling_enforce"
    target_triples: List[str]  # UUIDs affected
    reasoning: str
    round_num: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "target_triples": self.target_triples,
            "reasoning": self.reasoning,
            "round_num": self.round_num,
            "timestamp": self.timestamp,
        }


@dataclass
class CuratorConfig:
    """Configuration for the curator agent."""
    merge_similarity_threshold: float = 0.90
    prune_vote_threshold: int = 1
    prune_inactive_rounds: int = 3
    graph_size_ceiling: int = 5000
    contested_upvote_threshold: int = 3
    contested_downvote_threshold: int = 3


class CuratorAgent:
    """Curator agent for knowledge graph quality maintenance.

    The curator is algorithmic (not LLM-based) for deterministic, auditable
    curation. It runs during the Curate phase of each round.

    Decision: Algorithmic over LLM (see DECISIONS.md D1).
    """

    def __init__(
        self,
        graph_service,
        embedding_service=None,
        config: Optional[CuratorConfig] = None,
    ):
        self.graph_service = graph_service
        self.embedding_service = embedding_service
        self.config = config or CuratorConfig()
        self.audit_trail: List[CuratorAction] = []
        self._pruned_triples: List[Dict[str, Any]] = []

    def run_curation(self, round_num: int) -> Dict[str, Any]:
        """Execute full curation pipeline for the current round.

        Returns:
            Dict with action counts and details.
        """
        actions_count = 0

        # 1. Merge near-duplicates
        merge_count = self._merge_near_duplicates(round_num)
        actions_count += merge_count

        # 2. Flag contested triples
        flag_count = self._flag_contested_triples(round_num)
        actions_count += flag_count

        # 3. Enforce graph size ceiling
        ceiling_count = self._enforce_graph_ceiling(round_num)
        actions_count += ceiling_count

        # 4. Prune low-value triples
        prune_count = self._prune_low_value_triples(round_num)
        actions_count += prune_count

        logger.info(
            f"Curator round {round_num}: "
            f"{merge_count} merges, {flag_count} flags, "
            f"{ceiling_count} ceiling prunes, {prune_count} quality prunes"
        )

        return {
            "actions_count": actions_count,
            "merges": merge_count,
            "flags": flag_count,
            "ceiling_prunes": ceiling_count,
            "quality_prunes": prune_count,
        }

    def _merge_near_duplicates(self, round_num: int) -> int:
        """Merge triples with cosine similarity above the merge threshold."""
        if self.embedding_service is None:
            return 0

        try:
            agent_triples = self.graph_service.get_agent_triples()
            if len(agent_triples) < 2:
                return 0

            merged_count = 0
            merged_uuids = set()

            for i, triple_a in enumerate(agent_triples):
                if triple_a["uuid"] in merged_uuids:
                    continue

                for j in range(i + 1, len(agent_triples)):
                    triple_b = agent_triples[j]
                    if triple_b["uuid"] in merged_uuids:
                        continue

                    text_a = f"{triple_a['subject']} {triple_a['relationship']} {triple_a['object']}"
                    text_b = f"{triple_b['subject']} {triple_b['relationship']} {triple_b['object']}"

                    emb_a = self.embedding_service.get_embedding(text_a)
                    emb_b = self.embedding_service.get_embedding(text_b)

                    similarity = self._cosine_similarity(emb_a, emb_b)

                    if similarity > self.config.merge_similarity_threshold:
                        # Merge: keep the one with more votes, combine provenance
                        self._merge_pair(triple_a, triple_b, round_num)
                        merged_uuids.add(triple_b["uuid"])
                        merged_count += 1

            return merged_count

        except Exception as e:
            logger.error(f"Merge near-duplicates failed: {e}")
            return 0

    def _merge_pair(
        self,
        triple_a: Dict[str, Any],
        triple_b: Dict[str, Any],
        round_num: int,
    ):
        """Merge two triples into one, preserving provenance."""
        # Keep the triple with higher vote count
        votes_a = triple_a.get("upvotes", 0) - triple_a.get("downvotes", 0)
        votes_b = triple_b.get("upvotes", 0) - triple_b.get("downvotes", 0)

        if votes_b > votes_a:
            triple_a, triple_b = triple_b, triple_a  # Swap: keep b, remove a

        # Combine vote counts
        combined_upvotes = triple_a.get("upvotes", 0) + triple_b.get("upvotes", 0)
        combined_downvotes = triple_a.get("downvotes", 0) + triple_b.get("downvotes", 0)

        self.graph_service.update_triple_properties(
            triple_a["uuid"],
            {
                "upvotes": combined_upvotes,
                "downvotes": combined_downvotes,
                "merged_from": triple_b["uuid"],
            },
        )

        # Soft-delete the merged triple
        self.graph_service.update_triple_status(triple_b["uuid"], "merged")

        self._log_action(CuratorAction(
            action_type="merge",
            target_triples=[triple_a["uuid"], triple_b["uuid"]],
            reasoning=f"Merged near-duplicate (similarity > {self.config.merge_similarity_threshold}). "
                      f"Kept {triple_a['uuid']} with combined votes.",
            round_num=round_num,
        ))

    def _flag_contested_triples(self, round_num: int) -> int:
        """Flag triples with high upvotes AND high downvotes as contested."""
        try:
            agent_triples = self.graph_service.get_agent_triples()
            flag_count = 0

            for triple in agent_triples:
                if triple.get("status") == "contested":
                    continue

                upvotes = triple.get("upvotes", 0)
                downvotes = triple.get("downvotes", 0)

                if (
                    upvotes >= self.config.contested_upvote_threshold
                    and downvotes >= self.config.contested_downvote_threshold
                ):
                    self.graph_service.update_triple_status(
                        triple["uuid"], "contested"
                    )
                    flag_count += 1
                    self._log_action(CuratorAction(
                        action_type="flag",
                        target_triples=[triple["uuid"]],
                        reasoning=f"Flagged as contested: {upvotes} upvotes, {downvotes} downvotes",
                        round_num=round_num,
                    ))

            return flag_count

        except Exception as e:
            logger.error(f"Flag contested triples failed: {e}")
            return 0

    def _enforce_graph_ceiling(self, round_num: int) -> int:
        """Prune lowest-voted non-contested triples when ceiling exceeded."""
        try:
            agent_triples = self.graph_service.get_agent_triples()

            if len(agent_triples) <= self.config.graph_size_ceiling:
                return 0

            excess = len(agent_triples) - self.config.graph_size_ceiling

            # Sort by net vote score (upvotes - downvotes), ascending
            # Contested triples are NEVER pruned
            prunable = [
                t for t in agent_triples
                if t.get("status") != "contested"
            ]
            prunable.sort(
                key=lambda t: t.get("upvotes", 0) - t.get("downvotes", 0)
            )

            pruned_count = 0
            for triple in prunable[:excess]:
                self._soft_delete_triple(triple, round_num, "ceiling_enforce")
                pruned_count += 1

            return pruned_count

        except Exception as e:
            logger.error(f"Graph ceiling enforcement failed: {e}")
            return 0

    def _prune_low_value_triples(self, round_num: int) -> int:
        """Prune triples with low engagement after N rounds."""
        try:
            agent_triples = self.graph_service.get_agent_triples()
            pruned_count = 0

            for triple in agent_triples:
                # Skip contested — always protected
                if triple.get("status") == "contested":
                    continue

                # Skip newly added triples
                added_round = triple.get("added_round", round_num)
                rounds_since_addition = round_num - added_round
                if rounds_since_addition < self.config.prune_inactive_rounds:
                    continue

                # Check vote threshold
                total_votes = triple.get("upvotes", 0) + triple.get("downvotes", 0)
                if total_votes < self.config.prune_vote_threshold:
                    self._soft_delete_triple(triple, round_num, "prune")
                    pruned_count += 1

            return pruned_count

        except Exception as e:
            logger.error(f"Prune low-value triples failed: {e}")
            return 0

    def _soft_delete_triple(
        self,
        triple: Dict[str, Any],
        round_num: int,
        reason: str,
    ):
        """Soft-delete a triple: move to pruned_triples collection."""
        # Store in pruned collection
        self._pruned_triples.append({
            **triple,
            "pruned_round": round_num,
            "pruned_reason": reason,
            "pruned_timestamp": datetime.now().isoformat(),
        })

        # Update status in graph
        self.graph_service.update_triple_status(triple["uuid"], "pruned")

        self._log_action(CuratorAction(
            action_type="prune" if reason == "prune" else "ceiling_enforce",
            target_triples=[triple["uuid"]],
            reasoning=f"{'Low engagement' if reason == 'prune' else 'Graph size ceiling'}. "
                      f"Votes: {triple.get('upvotes', 0)} up, {triple.get('downvotes', 0)} down",
            round_num=round_num,
        ))

    def _log_action(self, action: CuratorAction):
        """Log a curator action to the audit trail."""
        self.audit_trail.append(action)
        logger.debug(
            f"Curator action: {action.action_type} on {action.target_triples} "
            f"(round {action.round_num}): {action.reasoning}"
        )

    def get_audit_trail(
        self,
        round_num: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get curator audit trail, optionally filtered by round."""
        if round_num is not None:
            return [
                a.to_dict() for a in self.audit_trail
                if a.round_num == round_num
            ]
        return [a.to_dict() for a in self.audit_trail]

    def get_pruned_triples(self) -> List[Dict[str, Any]]:
        """Get all soft-deleted (pruned) triples for post-simulation analysis."""
        return self._pruned_triples

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
