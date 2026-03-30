"""
MiroClaw Analytics API

Post-simulation analytics endpoints for:
- Dispute maps (contested triples)
- Graph diff (seed vs post-simulation)
- Per-agent provenance trails
- Vote distribution analysis
- Position drift visualisation data
- Oracle forecast time series
- Round-by-round simulation evolution
- MiroClaw phase details (Research, Contribute, Vote, Curate, Oracle)

Satisfies: R14 (Post-simulation analytics), Phase 6 backend
"""

import json
import os
import traceback

from flask import request, jsonify

from . import analytics_bp
from ..services.local_graph.graph_service import MiroClawGraphWriteAPI
from ..services.miroclaw_analytics import MiroClawAnalytics
from ..utils.logger import get_logger

logger = get_logger('miroclaw.api.analytics')


def _resolve_graph_write_api(project=None):
    """Resolve the MiroClawGraphWriteAPI from the project's graph service."""
    try:
        from ..services.graph_builder import get_graph_service
        local_gs = get_graph_service()
        if local_gs:
            return MiroClawGraphWriteAPI(local_gs)
    except Exception:
        pass
    if project and hasattr(project, '_graph_write_api'):
        return project._graph_write_api
    return None


def _resolve_simulation_runner():
    """Resolve the SimulationRunner for action log queries."""
    try:
        from ..services.simulation_runner import SimulationRunner
        return SimulationRunner
    except Exception:
        return None


def _require_project():
    """Load project from request params. Returns (project, error_response)."""
    from ..models.project import ProjectManager

    project_id = request.args.get("project_id") or (
        request.get_json(silent=True) or {}
    ).get("project_id")
    if not project_id:
        return None, (jsonify({"success": False, "error": "project_id required"}), 400)

    project = ProjectManager.get_project(project_id)
    if not project:
        return None, (jsonify({"success": False, "error": "Project not found"}), 404)
    return project, None


# ── Dispute Map ────────────────────────────────────────────────


@analytics_bp.route('/dispute-map', methods=['GET'])
def get_dispute_map():
    """Get all contested triples with agent-type breakdown."""
    project, err = _require_project()
    if err:
        return err

    try:
        graph_api = _resolve_graph_write_api(project)
        if not graph_api:
            return jsonify({"success": False, "error": "Graph service unavailable"}), 503

        analytics = MiroClawAnalytics(graph_service=graph_api)
        result = analytics.generate_dispute_map()
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Dispute map error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Graph Diff ─────────────────────────────────────────────────


@analytics_bp.route('/graph-diff', methods=['GET'])
def get_graph_diff():
    """Compare seed graph vs post-simulation graph."""
    project, err = _require_project()
    if err:
        return err

    try:
        graph_api = _resolve_graph_write_api(project)
        if not graph_api:
            return jsonify({"success": False, "error": "Graph service unavailable"}), 503

        analytics = MiroClawAnalytics(graph_service=graph_api)
        result = analytics.generate_graph_diff()
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Graph diff error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Provenance Trail ───────────────────────────────────────────


@analytics_bp.route('/provenance/<agent_id>', methods=['GET'])
def get_provenance_trail(agent_id: str):
    """Get per-round provenance trail for a specific agent."""
    project, err = _require_project()
    if err:
        return err

    try:
        graph_api = _resolve_graph_write_api(project)
        if not graph_api:
            return jsonify({"success": False, "error": "Graph service unavailable"}), 503

        simulation_id = request.args.get("simulation_id")
        sim_runner = _resolve_simulation_runner()

        analytics = MiroClawAnalytics(
            graph_service=graph_api,
            simulation_runner=sim_runner,
            simulation_id=simulation_id,
        )
        result = analytics.generate_provenance_trail(agent_id=agent_id)
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Provenance trail error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Vote Analysis ──────────────────────────────────────────────


@analytics_bp.route('/vote-analysis', methods=['GET'])
def get_vote_analysis():
    """Analyse vote distribution across the simulation."""
    project, err = _require_project()
    if err:
        return err

    try:
        graph_api = _resolve_graph_write_api(project)
        if not graph_api:
            return jsonify({"success": False, "error": "Graph service unavailable"}), 503

        analytics = MiroClawAnalytics(graph_service=graph_api)
        result = analytics.generate_vote_analysis()
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Vote analysis error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Position Drift ─────────────────────────────────────────────


@analytics_bp.route('/position-drift', methods=['GET'])
def get_position_drift():
    """Get agent position drift data for visualisation.

    Requires the simulation to be loaded with agent instances that
    have identity changelogs. For completed simulations, this data
    should be serialised at simulation end.
    """
    project, err = _require_project()
    if err:
        return err

    try:
        # Try loading persisted drift data from simulation directory
        simulation_id = request.args.get("simulation_id")
        if simulation_id:
            from ..config import Config
            sim_dir = os.path.join(
                Config.UPLOAD_FOLDER, 'simulations', simulation_id
            )
            drift_path = os.path.join(sim_dir, "position_drift.json")
            if os.path.exists(drift_path):
                with open(drift_path, 'r', encoding='utf-8') as f:
                    return jsonify({"success": True, "data": json.load(f)})

        # Fallback: try graph-based reconstruction
        graph_api = _resolve_graph_write_api()
        if not graph_api:
            return jsonify({"success": False, "error": "Graph service unavailable"}), 503

        analytics = MiroClawAnalytics(graph_service=graph_api)
        result = analytics.generate_position_drift(agents=[])
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Position drift error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Oracle Time Series ─────────────────────────────────────────


@analytics_bp.route('/oracle-time-series', methods=['GET'])
def get_oracle_time_series():
    """Get oracle forecast time series data."""
    project, err = _require_project()
    if err:
        return err

    try:
        # Try loading persisted oracle data from simulation directory
        simulation_id = request.args.get("simulation_id")
        if simulation_id:
            from ..config import Config
            sim_dir = os.path.join(
                Config.UPLOAD_FOLDER, 'simulations', simulation_id
            )
            oracle_path = os.path.join(sim_dir, "oracle_forecasts.json")
            if os.path.exists(oracle_path):
                with open(oracle_path, 'r', encoding='utf-8') as f:
                    return jsonify({"success": True, "data": json.load(f)})

        # Fallback: reconstruct from graph state
        graph_api = _resolve_graph_write_api()
        if graph_api:
            analytics = MiroClawAnalytics(graph_service=graph_api)
            result = analytics.generate_oracle_time_series(oracle_agents=[])
            return jsonify({"success": True, "data": result})

        return jsonify({"success": False, "error": "No oracle data available"}), 404

    except Exception as e:
        logger.error(f"Oracle time series error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Full Report ────────────────────────────────────────────────


@analytics_bp.route('/full-report', methods=['GET'])
def get_full_report():
    """Generate complete post-simulation analytics report."""
    project, err = _require_project()
    if err:
        return err

    try:
        graph_api = _resolve_graph_write_api(project)
        if not graph_api:
            return jsonify({"success": False, "error": "Graph service unavailable"}), 503

        analytics = MiroClawAnalytics(graph_service=graph_api)
        result = analytics.generate_full_report()
        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Full report error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Round Details (MiroClaw phased simulation) ────────────────


@analytics_bp.route('/round-details', methods=['GET'])
def get_round_details():
    """Get round-by-round MiroClaw simulation details from miroclaw_results.json.

    Returns per-round breakdown of triples added, votes cast, curator actions,
    oracle forecasts, and the triples added during each round's contribute phase.

    Query params:
        simulation_id — Required. The simulation ID.
    """
    simulation_id = request.args.get("simulation_id")
    if not simulation_id:
        return jsonify({"success": False, "error": "simulation_id required"}), 400

    try:
        from ..config import Config
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, 'simulations', simulation_id)
        results_path = os.path.join(sim_dir, "miroclaw_results.json")

        if not os.path.exists(results_path):
            return jsonify({
                "success": False,
                "error": "No MiroClaw results found for this simulation",
            }), 404

        with open(results_path, 'r', encoding='utf-8') as f:
            results = json.load(f)

        return jsonify({"success": True, "data": results})

    except Exception as e:
        logger.error(f"Round details error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ── Simulation Evolution ────────────────────────────────────────


@analytics_bp.route('/simulation-evolution', methods=['GET'])
def get_simulation_evolution():
    """Get high-level MiroClaw simulation evolution summary.

    Combines miroclaw_results.json with Neo4j triple data to show how
    the simulation progressed across rounds.

    Query params:
        simulation_id — Required. The simulation ID.
        project_id — Required. The project ID for graph access.
    """
    simulation_id = request.args.get("simulation_id")
    project_id = request.args.get("project_id")
    if not simulation_id or not project_id:
        return jsonify({
            "success": False,
            "error": "simulation_id and project_id required",
        }), 400

    try:
        from ..config import Config

        # Load round results
        sim_dir = os.path.join(Config.UPLOAD_FOLDER, 'simulations', simulation_id)
        results_path = os.path.join(sim_dir, "miroclaw_results.json")
        if not os.path.exists(results_path):
            return jsonify({
                "success": False,
                "error": "No MiroClaw results found for this simulation",
            }), 404

        with open(results_path, 'r', encoding='utf-8') as f:
            results = json.load(f)

        # Load triples from Neo4j
        graph_api = _resolve_graph_write_api()
        triples_by_round = {}
        if graph_api:
            try:
                all_triples = graph_api.get_agent_triples()
                for t in all_triples:
                    rnd = t.get("added_round", 0)
                    if rnd not in triples_by_round:
                        triples_by_round[rnd] = []
                    triples_by_round[rnd].append(t)
            except Exception as e:
                logger.warning(f"Failed to query triples for evolution: {e}")

        # Build evolution summary
        evolution = {
            "total_rounds": len(results),
            "total_triples": sum(r.get("triples_added", 0) for r in results),
            "total_votes": sum(r.get("votes_cast", 0) for r in results),
            "total_curator_actions": sum(r.get("curator_actions", 0) for r in results),
            "total_oracle_forecasts": sum(r.get("oracle_forecasts", 0) for r in results),
            "rounds": [],
        }

        for rnd_data in sorted(results, key=lambda x: x.get("round_num", 0)):
            rnd = rnd_data.get("round_num", 0)
            round_entry = {
                "round_num": rnd,
                "triples_added": rnd_data.get("triples_added", 0),
                "votes_cast": rnd_data.get("votes_cast", 0),
                "curator_actions": rnd_data.get("curator_actions", 0),
                "oracle_forecasts": rnd_data.get("oracle_forecasts", 0),
                "phases_executed": ["research", "contribute", "vote", "curate"],
                "triples": [],
            }
            if rnd_data.get("oracle_forecasts", 0) > 0:
                round_entry["phases_executed"].append("oracle")

            # Attach triples for this round
            for t in triples_by_round.get(rnd, []):
                round_entry["triples"].append({
                    "subject": t.get("subject", ""),
                    "relationship": t.get("relationship", ""),
                    "object": t.get("object", ""),
                    "added_by_agent": t.get("added_by_agent", ""),
                    "status": t.get("status", "pending"),
                    "upvotes": t.get("upvotes", 0),
                    "downvotes": t.get("downvotes", 0),
                })

            evolution["rounds"].append(round_entry)

        return jsonify({"success": True, "data": evolution})

    except Exception as e:
        logger.error(f"Simulation evolution error: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500
