# MiroClaw: Migration Plan

## Context

We are forking MiroClaw to create an English-first version with two major infrastructure changes:

1. **LLM Provider**: Switch from Alibaba Qwen to **Minimax 2.7**
2. **Knowledge Graph**: Replace **Zep Cloud** (SaaS) with **Neo4j** (local) + **Qwen3-Embedding-4B** for embeddings + **Minimax 2.7 LLM** for entity extraction
3. **Language**: Translate all Chinese text (~5,700 occurrences across 56 files) to English

### Current State

| Component | Current | Target |
|-----------|---------|--------|
| LLM API | Alibaba Qwen (OpenAI-compatible) | Minimax 2.7 (OpenAI-compatible) |
| Knowledge Graph | Zep Cloud (SaaS) | Neo4j (local Docker) |
| Embeddings | Zep Cloud built-in | Qwen3-Embedding-4B (local) |
| Entity Extraction | Zep Cloud NLP | Minimax 2.7 LLM |
| UI/Code Language | Chinese-first | English-first |

## Phase Order

| Phase | Description | Risk | Rationale |
|-------|-------------|------|-----------|
| **1. Replace Zep Cloud** | Neo4j + Qwen3-Embedding-4B + LLM | HIGH | Critical path — system won't function without it |
| **2. Minimax 2.7 API** | Configuration change | LOW | Needed to test Phase 1 (LLM extraction) |
| **3. English Translation** | Translate all Chinese text | MEDIUM | Bulk work, no architectural impact |

---

## Phase 1: Replace Zep Cloud with Local Stack

### What Zep Does (and what we must replace)

Zep Cloud serves four critical roles that the system cannot function without:

| Role | What Zep Does | Local Replacement |
|------|--------------|-------------------|
| **Graph Storage** | Stores entities (nodes) and relationships (edges) with typed labels and attributes | **Neo4j** — native graph database with Cypher queries |
| **Entity Extraction** | Processes text chunks and extracts entities/relationships using NLP | **Minimax 2.7 LLM** — extract per ontology schema |
| **Semantic Search** | Natural language queries returning relevant facts, entities, relationships | **Qwen3-Embedding-4B** + Neo4j vector index |
| **Live Memory** | Agent actions during simulation become episodes that update the graph | **Same Neo4j** — insert episodes, run extraction |
| **Temporal Tracking** | Edges have valid_at, invalid_at, expired_at timestamps | **Neo4j edge properties** |

### Files That Use Zep (must be modified)

| File | Zep Operations |
|------|---------------|
| `backend/app/services/graph_builder.py` | `graph.create`, `set_ontology`, `add_batch`, `episode.get`, `delete` |
| `backend/app/services/zep_tools.py` | `graph.search`, `fetch_all_nodes/edges`, `node.get` |
| `backend/app/services/zep_graph_memory_updater.py` | `graph.add` (real-time episodes during simulation) |
| `backend/app/services/zep_entity_reader.py` | `fetch_all_nodes/edges`, `node.get`, `node.get_entity_edges` |
| `backend/app/services/oasis_profile_generator.py` | `graph.search` (context enrichment for profile gen) |
| `backend/app/utils/zep_paging.py` | Pagination wrapper for node/edge fetching |
| `backend/app/api/graph.py` | Instantiates `GraphBuilderService` |
| `backend/app/api/simulation.py` | Instantiates `ZepEntityReader` |
| `backend/app/config.py` | `ZEP_API_KEY` config + validation |

### New Module Structure

```
backend/app/services/local_graph/
    __init__.py              # Exports LocalGraphService
    neo4j_client.py          # Neo4j connection management + Cypher queries
    models.py                # Data classes matching Zep SDK attribute names
    entity_extractor.py      # LLM-based entity/relationship extraction from text
    embedding_service.py     # Qwen3-Embedding-4B for semantic search
    graph_service.py         # Main service class (drop-in replacement for Zep client)
    episode_processor.py     # Background processing: text -> entities/edges -> embeddings
```

### Neo4j Schema

```cypher
// Graph metadata
(:Graph {id, name, description, created_at})

// Ontology (stored as JSON properties)
(:Graph)-[:HAS_ONTOLOGY]->(:Ontology {entity_types: JSON, edge_types: JSON})

// Entities (nodes with dynamic labels from ontology)
(:Entity:Person {uuid, graph_id, name, summary, attributes: JSON, created_at})
(:Entity:Organization {uuid, graph_id, name, summary, attributes: JSON, created_at})

// Relationships (typed edges with temporal metadata)
(:Entity)-[:RELATIONSHIP {uuid, name, fact, attributes: JSON,
    created_at, valid_at, invalid_at, expired_at}]->(:Entity)

// Episodes (text chunks for processing tracking)
(:Episode {uuid, graph_id, data, type, processed: boolean, created_at})

// Vector indexes for semantic search (Neo4j 5.x native)
CREATE VECTOR INDEX entity_embeddings FOR (e:Entity) ON (e.embedding)
CREATE VECTOR INDEX edge_embeddings FOR ()-[r:RELATIONSHIP]-() ON (r.embedding)
```

**Deployment:** Add `neo4j:5` Docker service to `docker-compose.yml` alongside MiroClaw.

### Embedding Service: Qwen3-Embedding-4B

- Run locally via `transformers` or `sentence-transformers` library
- Generate embeddings for: node summaries, edge facts, search queries
- Store embeddings in Neo4j vector index — no separate FAISS needed
- Neo4j 5.x supports vector indexes natively

### LocalGraphService Interface

The service class provides a drop-in replacement for the Zep SDK client. Return objects match Zep attribute names (`uuid_`, `name`, `labels`, `summary`, `fact`, `source_node_uuid`, etc.) to minimize changes in calling code.

```python
class LocalGraphService:
    # Graph CRUD
    def create(graph_id, name, description)
    def delete(graph_id)
    def set_ontology(graph_ids, entity_types, edge_types)

    # Episodes
    def add_batch(graph_id, episodes) -> List[EpisodeResult]
    def add(graph_id, type, data)

    # Search (vector similarity via Qwen3-Embedding-4B + Neo4j)
    def search(graph_id, query, limit, scope, reranker) -> SearchResults

    # Node operations (nested namespace)
    class node:
        def get_by_graph_id(graph_id, limit, uuid_cursor)
        def get(uuid_)
        def get_entity_edges(node_uuid)

    # Edge operations (nested namespace)
    class edge:
        def get_by_graph_id(graph_id, limit, uuid_cursor)

    # Episode status
    class episode:
        def get(uuid_)
```

### Entity Extraction Strategy

Use Minimax 2.7 via `LLMClient` for extraction. The ontology is already defined (from Step 1 of the workflow), so the LLM has a schema to work against.

**Prompt design:**
```
Given ontology: {entity_types, edge_types}
Given text: {chunk}
Extract all entities and relationships matching the ontology.
Return: {"entities": [...], "relationships": [...]}
```

**Deduplication:** Cypher MERGE by case-insensitive name; update summary on collision.

### Search Implementation

| Search Type | Implementation |
|-------------|---------------|
| **QuickSearch** | Query → Qwen3-Embedding-4B → Neo4j vector similarity search |
| **InsightForge** | LLM generates sub-queries → multiple vector searches → aggregate results |
| **PanoramaSearch** | Cypher traversal for all nodes/edges with temporal filtering |

### File Modification Summary

| File | Change |
|------|--------|
| `backend/app/services/graph_builder.py` | Replace `Zep` client with `LocalGraphService`. Dict-based ontology instead of dynamic Pydantic models. |
| `backend/app/services/zep_entity_reader.py` | Replace `Zep` client with `LocalGraphService`. Direct method mapping via Cypher. |
| `backend/app/services/zep_tools.py` | Replace Zep search with Neo4j vector search. Keep `_local_search` as fallback. |
| `backend/app/services/zep_graph_memory_updater.py` | Replace `client.graph.add()` with `LocalGraphService.add()` |
| `backend/app/services/oasis_profile_generator.py` | Replace `Zep` client with `LocalGraphService.search()` |
| `backend/app/utils/zep_paging.py` | Remove — Neo4j handles pagination via `SKIP`/`LIMIT` |
| `backend/app/config.py` | Remove `ZEP_API_KEY`. Add `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`. |
| `backend/app/api/graph.py` | Update service instantiation |
| `backend/app/api/simulation.py` | Update service instantiation |
| `backend/requirements.txt` + `pyproject.toml` | Remove `zep-cloud==3.13.0`. Add `neo4j>=5.0`, `transformers`, `torch`. |
| `docker-compose.yml` | Add `neo4j:5` service with ports 7474/7687 |

### Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM entity extraction quality lower than Zep | HIGH | Compare entity counts on same documents. Iteratively tune extraction prompts. |
| Qwen3-Embedding-4B model size (~8GB) | MEDIUM | Document hardware requirements. Consider smaller model as fallback option. |
| Neo4j adds infrastructure complexity | LOW | Docker Compose keeps it self-contained. Single `docker compose up`. |
| Episode processing slower (each needs LLM call) | MEDIUM | Batch episodes and parallelize LLM calls. |
| Entity deduplication errors | MEDIUM | Cypher MERGE with fuzzy matching; conservative merge strategy. |

---

## Phase 2: Minimax 2.7 API Configuration

**Risk: LOW** — The existing `LLMClient` (`backend/app/utils/llm_client.py`) already uses the OpenAI SDK with configurable `base_url` and already strips `<think>` tags from reasoning models (commit 985f89f, tested with Minimax M2.5).

### Steps

1. **Update `.env.example`** with Minimax 2.7 endpoint and model name
2. **Verify JSON mode** — `chat_json()` sends `response_format={"type": "json_object"}`. Confirm Minimax 2.7 supports this; if not, add prompt-level JSON enforcement fallback
3. **Verify direct SDK calls** — Two files bypass `LLMClient` and use `OpenAI()` directly but read from the same `Config.LLM_*` values (auto-pick up new config):
   - `backend/app/services/oasis_profile_generator.py`
   - `backend/app/services/simulation_config_generator.py`
4. **Test `<think>` tag handling** — Already implemented. Verify regex works for Minimax 2.7 output format.

### Files to modify
- `.env.example` — Update comments and default values
- Likely no code changes (already OpenAI-compatible)

---

## Phase 3: Chinese-to-English Translation

**Risk: MEDIUM** — LLM prompt translation may affect output quality. Each translated prompt needs testing.

**Scope: ~5,700 Chinese text occurrences across 56 files.**

### Tier 1: LLM System Prompts (CRITICAL — affects output quality)

| File | What to translate |
|------|-------------------|
| `backend/app/services/oasis_profile_generator.py` | System prompts for persona generation (~2000 chars), gender mappings, fallback persona text |
| `backend/app/services/ontology_generator.py` | `ONTOLOGY_SYSTEM_PROMPT` — large system prompt for ontology design |
| `backend/app/services/simulation_config_generator.py` | Prompts for generating simulation parameters |
| `backend/app/services/report_agent.py` | ReACT prompts for report generation |
| `backend/app/services/zep_tools.py` | Sub-query generation, agent selection, interview prompts |
| `backend/app/api/simulation.py` | `INTERVIEW_PROMPT_PREFIX` |

### Tier 2: Frontend UI Text (CRITICAL — user-facing)

| File | Occurrences | Content type |
|------|-------------|--------------|
| `frontend/src/components/Step4Report.vue` | 227 | Report generation UI |
| `frontend/src/components/Step2EnvSetup.vue` | 210 | Simulation setup labels, agent config |
| `frontend/src/views/Process.vue` | 191 | Process view |
| `frontend/src/components/HistoryDatabase.vue` | 144 | History display |
| `frontend/src/components/GraphPanel.vue` | 91 | Graph visualization labels |
| `frontend/src/components/Step5Interaction.vue` | 90 | Agent interview UI |
| `frontend/src/views/Home.vue` | 78 | Hero text, workflow steps, upload labels |
| `frontend/src/components/Step3Simulation.vue` | 74 | Simulation execution monitor |
| `frontend/src/views/SimulationRunView.vue` | 43 | Simulation runner view |
| `frontend/src/views/SimulationView.vue` | 42 | Simulation config screen |
| All other frontend files | ~124 | API modules, router, store, remaining views |

### Tier 3: Backend Display Text (HIGH)

- Action descriptions and platform display names in `zep_graph_memory_updater.py`
- `to_text()` methods in `zep_tools.py` (LLM-facing search result formatting)
- Error messages across all backend files

### Tier 4: Comments, Docstrings, Logging (MEDIUM)

All 36 backend Python files, plus config/Docker files. Bulk work, no functional impact.

### Tier 5: Documentation (LOW)

- Make `README-EN.md` the primary `README.md`
- Translate `.env.example`, `docker-compose.yml`, `Dockerfile` comments

### Translation Approach

- Work file-by-file, one tier at a time
- For LLM prompts: translate carefully, preserving JSON field names and format instructions
- For gender mappings: keep both Chinese and English keys for robustness
- For `file_parser.py`: update Chinese sentence delimiters to also handle English

---

## Verification Plan

| Phase | Test |
|-------|------|
| Phase 1 (Zep replacement) | Upload document → build graph in Neo4j → verify entities/edges → run simulation → verify memory updates → generate report → verify search |
| Phase 2 (Minimax) | Start backend with Minimax 2.7 config → verify ontology generation, profile generation, report generation |
| Phase 3 (Translation) | Visual review of all UI pages (no Chinese). Run backend (English logs/errors). |
| **Full E2E** | Complete workflow end-to-end with all three changes applied |

## Infrastructure Requirements

| Component | Requirement |
|-----------|------------|
| Neo4j | Docker image `neo4j:5`, ports 7474 (browser) / 7687 (bolt) |
| Qwen3-Embedding-4B | ~8GB model, GPU recommended for speed (CPU fallback available) |
| Minimax 2.7 API | API key, OpenAI-compatible endpoint |
| Python | 3.11-3.12 |
| Node.js | 18+ |
