# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MiroClaw** is a research-armed multi-agent prediction engine. It extends the MiroClaw foundation with real-time web research, collaborative knowledge graph curation, adversarial evidence testing, and calibrated forecasting. Agents discover evidence from the open web during simulation, contribute structured triples to a living knowledge graph, and vote on each other's findings. The post-simulation graph is a collaboratively-researched, adversarially-tested knowledge base.

**Current state:** The codebase is the MiroClaw foundation being transformed into MiroClaw. The simulation engine (OASIS flat loop) is being replaced with CAMEL-native phased rounds. See `docs/specs/miroclaw.md` for the full behaviour spec and `docs/miroclaw-roadmap.md` for the product vision.

## Common Commands

```bash
# Install all dependencies (Node root + frontend + Python backend)
npm run setup:all

# Start both frontend and backend concurrently
npm run dev

# Start individually
npm run frontend    # Vue 3 dev server on http://localhost:3000
npm run backend     # Flask API on http://localhost:5001

# Build frontend for production
npm run build

# Docker deployment
docker compose up -d
```

### Backend-only commands

```bash
cd backend
uv sync                    # Install/update Python dependencies
uv run python run.py       # Start Flask server directly
uv run pytest              # Run tests
```

### Environment setup

```bash
cp .env.example .env
# Required keys: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME
# Neo4j: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
```

## Architecture

### High-Level Flow (Current — MiroClaw foundation)

```
Upload docs -> Ontology extraction (LLM) -> Graph construction (Neo4j)
-> Entity filtering (actors only) -> Agent profile generation (LLM)
-> Simulation config (LLM) -> OASIS simulation (subprocess)
-> Report generation (ReACT agent) -> Interactive chat
```

### High-Level Flow (Target — MiroClaw)

```
Upload docs -> Ontology extraction (LLM) -> Graph construction (Neo4j)
-> Entity filtering (actors only) -> MiroClawAgent creation (CAMEL ChatAgent)
-> Phased simulation (Research -> Contribute -> Vote -> Curate -> Oracle)
-> Living knowledge graph grows during simulation
-> Report generation (Oracle-powered) -> Interactive chat
```

### Frontend (Vue 3 + Vite)

- **Framework**: Vue 3 Composition API, Vue Router, Axios, D3 for graph visualization
- **API proxy**: Vite proxies `/api` requests to backend at `localhost:5001`
- **State**: Minimal — mostly component-local state with polling for async operations.

#### Route flow
`Home (/)` -> `Process (/process/:projectId)` [Steps 1-2] -> `SimulationRun (/simulation/:simulationId/start)` [Step 3] -> `Report (/report/:reportId)` [Step 4] -> `Interaction (/interaction/:reportId)` [Step 5]

### Backend (Flask + Python)

- **Entry point**: `backend/run.py` -> validates config -> `create_app()` -> Flask on port 5001
- **Config**: `backend/app/config.py` loads from root `.env` file via python-dotenv
- **CORS**: Enabled for all `/api/*` routes

#### API Blueprints
| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `graph` | `/api/graph` | Project CRUD, ontology generation, graph building |
| `simulation` | `/api/simulation` | Entity filtering, profile gen, sim execution, interviews |
| `report` | `/api/report` | Report generation, chat with ReportAgent |

#### Key services (`app/services/`)
- **`ontology_generator.py`** — LLM extracts entity types (FOAF actors + Schema.org context) and relationships
- **`graph_builder.py`** — Builds Neo4j knowledge graph from text chunks via LocalGraphService
- **`oasis_profile_generator.py`** — Converts graph actor entities to agent profiles with LLM-enriched personas
- **`simulation_config_generator.py`** — LLM generates simulation parameters (timing, events, activity patterns)
- **`simulation_runner.py`** — Spawns OASIS simulation as subprocess, monitors via file-based action logs
- **`report_agent.py`** — ReACT-pattern agent with reflection, uses graph search + simulation query tools
- **`graph_search_tools.py`** — Three search strategies: InsightForge (deep), PanoramaSearch (broad), QuickSearch
- **`simulation_query_tools.py`** — Direct SQLite access to simulation posts, debates, content analysis, timeline

#### Local graph engine (`app/services/local_graph/`)
- **`graph_service.py`** — Neo4j-backed graph service (replaced Zep Cloud)
- **`entity_extractor.py`** — LLM entity extraction with ontology category propagation
- **`episode_processor.py`** — Entity upsert with `entity_category` (actor/context) stored in Neo4j
- **`embedding_service.py`** — Sentence-transformer embeddings (Qwen3-Embedding-4B)
- **`neo4j_client.py`** — Neo4j driver wrapper with index management

#### Simulation subprocess (`scripts/`)
- `run_parallel_simulation.py` — Dual-platform (Twitter + Reddit) OASIS simulation
- Outputs: action logs as JSONL, file-based IPC for interviews

### External Dependencies
- **LLM API**: Any OpenAI SDK-compatible endpoint (configured via `LLM_*` env vars)
- **Neo4j 5**: Knowledge graph storage with APOC, fulltext + vector indexes
- **CAMEL 0.2.78**: Agent framework (currently using ModelFactory, ChatHistoryMemory)
- **OASIS 0.2.5**: Social platform simulation (Twitter/Reddit databases, feed algorithms)

### Key Design Decisions
- **Actor/context separation**: Ontology uses FOAF for actor types (Person, Organization, Group) and Schema.org for context types (CreativeWork, Event, Place, Intangible). Only actor entities become simulation agents; context entities enrich the graph.
- **Entity-to-agent boundary**: Structural, via `actors_only=True` in `graph_entity_reader.py`

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 18+ |
| Python | >=3.11, <=3.12 |
| uv | Latest |
| Neo4j | 5+ |
