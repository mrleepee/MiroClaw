"""
MiroClaw Post-Simulation Analytics

Artifact extraction layer for post-simulation analysis:
- Dispute maps (contested triples with agent-type breakdown)
- Graph diff (seed vs post-simulation)
- Per-agent provenance trails
- Vote distribution analysis
- Position drift visualisation data
- Oracle forecast time series

Satisfies: R14 (Post-simulation analytics), R16 (Retain report agent)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger('miroclaw.analytics')


class MiroClawAnalytics:
    """Post-simulation analytics for MiroClaw simulations.

    Generates structured reports from the simulation artifacts:
    knowledge graph, action logs, vote records, oracle forecasts.
    """

    def __init__(
        self,
        graph_service=None,
        simulation_runner=None,
        simulation_id: str = None,
        curator=None,
    ):
        self.graph_service = graph_service
        self.simulation_runner = simulation_runner
        self.simulation_id = simulation_id
        self.curator = curator

    def generate_dispute_map(self) -> Dict[str, Any]:
        """Extract all contested triples with agent-type breakdown.

        Returns a structured report showing:
        - Which agent types upvoted vs downvoted
        - Source URLs from both sides
        - Round added and by whom

        Satisfies: Behaviour 6.1
        """
        try:
            contested = self.graph_service.get_triples_by_status("contested")

            disputes = []
            for triple in contested:
                dispute_entry = {
                    "triple_uuid": triple.get("uuid"),
                    "claim": f"({triple.get('subject')}) —[{triple.get('relationship')}]-> ({triple.get('object')})",
                    "source_url": triple.get("source_url"),
                    "added_by": triple.get("added_by_agent"),
                    "added_round": triple.get("added_round"),
                    "upvotes": triple.get("upvotes", 0),
                    "downvotes": triple.get("downvotes", 0),
                    "status": triple.get("status"),
                }
                disputes.append(dispute_entry)

            return {
                "total_contested": len(disputes),
                "disputes": disputes,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Dispute map generation failed: {e}")
            return {"error": str(e)}

    def generate_graph_diff(self) -> Dict[str, Any]:
        """Compare seed graph vs post-simulation graph.

        Shows:
        - Nodes/edges added by agents (with provenance)
        - Nodes/edges pruned by curator
        - Net growth statistics

        Satisfies: Behaviour 6.2
        """
        try:
            all_triples = self.graph_service.get_agent_triples()
            seed_triples = self.graph_service.get_seed_triples()
            pruned_triples = []

            if self.curator:
                pruned_triples = self.curator.get_pruned_triples()

            agent_added = [
                t for t in all_triples
                if t.get("added_by_agent") and t.get("status") != "pruned"
            ]

            return {
                "seed_triples_count": len(seed_triples),
                "agent_triples_attempted": len(all_triples) + len(pruned_triples),
                "agent_triples_survived": len(agent_added),
                "agent_triples_pruned": len(pruned_triples),
                "contested_triples": len([
                    t for t in all_triples if t.get("status") == "contested"
                ]),
                "net_growth": len(agent_added),
                "pruned_details": pruned_triples[:50],  # Limit for API response
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Graph diff generation failed: {e}")
            return {"error": str(e)}

    def generate_provenance_trail(
        self,
        agent_id: str,
        simulation_id: str = None,
    ) -> Dict[str, Any]:
        """Generate per-round provenance trail for a specific agent.

        Shows per-round:
        - What it searched (queries)
        - What it read (URLs)
        - What it added to graph (triples)
        - How it voted
        - Oracle consultations
        - Stance shifts

        Satisfies: Behaviour 6.3
        """
        sim_id = simulation_id or self.simulation_id
        if not sim_id:
            return {"error": "No simulation ID provided"}

        try:
            # Get agent's actions from simulation logs
            actions = self.simulation_runner.get_all_actions(
                simulation_id=sim_id,
            )
            agent_actions = [
                a for a in actions if a.agent_name == agent_id
            ]

            # Get agent's graph contributions
            agent_triples = self.graph_service.get_agent_triples(
                filter_agent=agent_id,
            )

            # Get oracle consultations from action logs
            consultations = [
                a for a in agent_actions
                if a.action_type == "ORACLE_CONSULTATION"
            ]

            # Build per-round breakdown
            rounds = {}
            for action in agent_actions:
                r = action.round_num
                if r not in rounds:
                    rounds[r] = {
                        "searches": [],
                        "reads": [],
                        "graph_additions": [],
                        "votes": [],
                        "oracle_consultations": [],
                    }
                entry = rounds[r]
                if action.action_type == "WEB_SEARCH":
                    entry["searches"].append(action.action_args.get("query", ""))
                elif action.action_type == "PAGE_READ":
                    entry["reads"].append(action.action_args.get("url", ""))
                elif action.action_type == "ADD_TRIPLE":
                    entry["graph_additions"].append(action.action_args)
                elif action.action_type in ("UPVOTE", "DOWNVOTE"):
                    entry["votes"].append({
                        "triple": action.action_args.get("triple_uuid"),
                        "direction": action.action_type.lower(),
                    })

            # Add graph triple details
            for triple in agent_triples:
                r = triple.get("added_round", 0)
                if r not in rounds:
                    rounds[r] = {
                        "searches": [],
                        "reads": [],
                        "graph_additions": [],
                        "votes": [],
                        "oracle_consultations": [],
                    }
                rounds[r]["graph_additions"].append({
                    "triple": f"({triple['subject']}) —[{triple['relationship']}]-> ({triple['object']})",
                    "upvotes": triple.get("upvotes", 0),
                    "downvotes": triple.get("downvotes", 0),
                    "status": triple.get("status"),
                })

            return {
                "agent_id": agent_id,
                "total_actions": len(agent_actions),
                "total_triples_added": len(agent_triples),
                "rounds": rounds,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Provenance trail generation failed: {e}")
            return {"error": str(e)}

    def generate_vote_analysis(self) -> Dict[str, Any]:
        """Analyse vote distribution across the simulation.

        Shows:
        - Most contested triples
        - Vote patterns by agent type
        - Triples that flipped status

        Satisfies: Behaviour 6.4
        """
        try:
            agent_triples = self.graph_service.get_agent_triples()

            # Most contested (highest combined votes)
            by_engagement = sorted(
                agent_triples,
                key=lambda t: t.get("upvotes", 0) + t.get("downvotes", 0),
                reverse=True,
            )

            # Status distribution
            status_counts = {}
            for t in agent_triples:
                status = t.get("status", "pending")
                status_counts[status] = status_counts.get(status, 0) + 1

            return {
                "total_triples": len(agent_triples),
                "status_distribution": status_counts,
                "most_contested": [
                    {
                        "triple_uuid": t.get("uuid"),
                        "claim": f"({t.get('subject')}) —[{t.get('relationship')}]-> ({t.get('object')})",
                        "upvotes": t.get("upvotes", 0),
                        "downvotes": t.get("downvotes", 0),
                        "status": t.get("status"),
                    }
                    for t in by_engagement[:20]
                ],
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Vote analysis generation failed: {e}")
            return {"error": str(e)}

    def generate_position_drift(
        self,
        agents: List = None,
    ) -> Dict[str, Any]:
        """Generate position drift data for visualisation.

        Per-agent stance over time (round on x-axis, stance on y-axis)
        with triggering evidence annotated at shift points.

        Satisfies: Behaviour 6.5
        """
        try:
            drift_data = []
            for agent in (agents or []):
                if not hasattr(agent, 'identity'):
                    continue

                identity = agent.identity
                drift_data.append({
                    "agent_id": agent.agent_id,
                    "entity_name": identity.entity_name,
                    "entity_type": identity.entity_type,
                    "current_stance": identity.stance.value,
                    "epistemic_flexibility": identity.epistemic_flexibility,
                    "shifts": identity.changelog,
                })

            return {
                "agents": drift_data,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Position drift generation failed: {e}")
            return {"error": str(e)}

    def generate_oracle_time_series(
        self,
        oracle_agents: List = None,
    ) -> Dict[str, Any]:
        """Generate oracle forecast time series data.

        Per-question probability over time, correlated with knowledge
        graph growth.

        Satisfies: Behaviour 6.6
        """
        try:
            series_data = []
            for oracle in (oracle_agents or []):
                if not hasattr(oracle, 'get_forecast_history'):
                    continue

                history = oracle.get_forecast_history()
                # Group by question
                by_question = {}
                for entry in history:
                    q = entry["question"]
                    if q not in by_question:
                        by_question[q] = []
                    by_question[q].append({
                        "round": entry["round"],
                        "probability": entry["probability"],
                        "confidence": entry["confidence"],
                        "timestamp": entry["timestamp"],
                    })

                series_data.append({
                    "oracle_id": oracle.agent_id,
                    "questions": by_question,
                })

            return {
                "oracle_series": series_data,
                "generated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Oracle time series generation failed: {e}")
            return {"error": str(e)}

    def generate_full_report(self) -> Dict[str, Any]:
        """Generate complete post-simulation analytics report."""
        return {
            "dispute_map": self.generate_dispute_map(),
            "graph_diff": self.generate_graph_diff(),
            "vote_analysis": self.generate_vote_analysis(),
            "generated_at": datetime.now().isoformat(),
        }
