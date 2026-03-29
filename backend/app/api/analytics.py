"""
MiroClaw Analytics API

Post-simulation analytics endpoints for:
- Dispute maps (contested triples)
- Graph diff (seed vs post-simulation)
- Per-agent provenance trails
- Vote distribution analysis
- Position drift visualisation data
- Oracle forecast time series

Satisfies: R14 (Post-simulation analytics), Phase 6 backend
"""

import traceback

from flask import request, jsonify

from . import analytics_bp
from ..services.local_graph.graph_service import MiroClawGraphWriteAPI
from ..services.miroclaw_analytics import MiroClawAnalytics
from ..utils.logger import get_logger

logger = get_logger('miroclaw.api.analytics')


def _resolve_graph_write_api(project):
    """Resolve the MiroClawGraphWriteAPI from the project's graph service."""
    try:
        from ..services.local_graph import get_shared_graph_service
        local_gs = get_shared_graph_service()
        if local_gs:
            return MiroClawGraphWriteAPI(local_gs)
    except ImportError:
        pass
    if hasattr(project, '_graph_write_api'):
        return project._graph_write_api
    return None


def _resolve_simulation_runner():
    """Resolve the SimulationRunner for action log queries."""
    try:
        from ..services.simulation_runner import SimulationRunner
        return SimulationRunner()
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
        # Position drift requires live agent instances or serialised data
        # Check for serialised drift data in project
        if hasattr(project, 'position_drift_data'):
            return jsonify({"success": True, "data": project.position_drift_data})

        # Fallback: try to reconstruct from graph state
        graph_api = _resolve_graph_write_api(project)
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
        # Oracle time series requires serialised forecast history
        if hasattr(project, 'oracle_time_series_data'):
            return jsonify({"success": True, "data": project.oracle_time_series_data})

        analytics = MiroClawAnalytics()
        result = analytics.generate_oracle_time_series(oracle_agents=[])
        return jsonify({"success": True, "data": result})

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
