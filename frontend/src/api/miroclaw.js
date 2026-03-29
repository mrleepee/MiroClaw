import service, { requestWithRetry } from './index'

/**
 * Get triples from the knowledge graph.
 * @param {string} graphId
 * @param {Object} params - { filter_agent, status }
 */
export const getTriples = (graphId, params = {}) => {
  return service.get(`/api/graph/${graphId}/triples`, { params })
}

/**
 * Get a single triple by UUID.
 * @param {string} graphId
 * @param {string} tripleUuid
 */
export const getTriple = (graphId, tripleUuid) => {
  return service.get(`/api/graph/${graphId}/triple/${tripleUuid}`)
}

/**
 * Submit a structured triple to the knowledge graph.
 * @param {string} graphId
 * @param {Object} data - { subject, subject_type, relationship, object, object_type, source_url, added_by_agent, added_round }
 */
export const submitTriple = (graphId, data) => {
  return requestWithRetry(() => service.post(`/api/graph/${graphId}/triple`, data), 3, 1000)
}

/**
 * Vote on a triple (upvote or downvote).
 * @param {string} graphId
 * @param {string} tripleUuid
 * @param {Object} data - { agent_id, direction, round_num }
 */
export const voteTriple = (graphId, tripleUuid, data) => {
  return requestWithRetry(() => service.post(`/api/graph/${graphId}/triple/${tripleUuid}/vote`, data), 3, 1000)
}

/**
 * Get graph statistics (triple counts by status).
 * @param {string} graphId
 */
export const getGraphStats = (graphId) => {
  return service.get(`/api/graph/${graphId}/stats`)
}

// ── Analytics (Phase 6) ──────────────────────────────────────────────

export const getDisputeMap = (simulationId) => {
  return service.get('/api/analytics/dispute-map', { params: { simulation_id: simulationId } })
}

export const getGraphDiff = (simulationId) => {
  return service.get('/api/analytics/graph-diff', { params: { simulation_id: simulationId } })
}

export const getProvenanceTrail = (agentId, simulationId) => {
  return service.get(`/api/analytics/provenance/${agentId}`, { params: { simulation_id: simulationId } })
}

export const getVoteAnalysis = (simulationId) => {
  return service.get('/api/analytics/vote-analysis', { params: { simulation_id: simulationId } })
}

export const getPositionDrift = (simulationId) => {
  return service.get('/api/analytics/position-drift', { params: { simulation_id: simulationId } })
}

export const getOracleTimeSeries = (simulationId) => {
  return service.get('/api/analytics/oracle-time-series', { params: { simulation_id: simulationId } })
}

export const getFullAnalyticsReport = (simulationId) => {
  return service.get('/api/analytics/full-report', { params: { simulation_id: simulationId } })
}
