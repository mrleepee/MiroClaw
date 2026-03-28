# MiroClaw

**Research-armed multi-agent prediction engine with collaborative knowledge graph curation and calibrated forecasting.**

MiroClaw extends [MiroFish](https://github.com/666ghj/MiroFish) to give AI agents real-time web research capabilities. Agents discover evidence from the open web during simulation rounds, contribute structured triples to a living knowledge graph, and vote on each other's findings. A curator agent maintains graph quality, and oracle agents provide calibrated probability forecasts. The post-simulation graph is a collaboratively-researched, adversarially-tested knowledge base.

> Upload seed materials. MiroClaw builds a knowledge graph, populates a simulated world with research-armed agents, runs adversarial evidence testing, and returns a prediction report with calibrated probabilities.

## What MiroClaw Changes

| MiroFish | MiroClaw |
|----------|----------|
| Frozen knowledge graph | Living graph that grows during simulation |
| Agents argue from seed documents only | Agents research the open web each round |
| Flat simulation loop (OASIS) | Phased rounds: Research, Contribute, Vote, Curate, Oracle |
| Unbounded agent memory | Hybrid memory with structured compaction |
| General-purpose report agent | Oracle-powered reports with calibrated probabilities |

## Workflow

1. **Graph Building** -- Seed extraction, ontology generation (FOAF + Schema.org), Neo4j graph construction
2. **Environment Setup** -- Entity filtering (actors only), agent profile generation, simulation config
3. **Simulation** -- Phased rounds with web research, triple contribution, voting, curation
4. **Report Generation** -- Oracle-powered analysis with calibrated probability estimates
5. **Deep Interaction** -- Chat with any agent or the report agent

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Any OpenAI SDK-compatible API |
| Graph Database | Neo4j 5 with APOC |
| Agent Framework | CAMEL-AI (ChatAgent, Workforce, LongtermAgentMemory) |
| Social Platforms | OASIS (Twitter/Reddit as interaction surface) |
| Forecasting | OpenForecaster-8B (local, calibrated) |
| Browser | OpenClaw agent-browser (CDP) |
| Frontend | Vue 3 / Vite (port 3000) |
| Backend | Flask / Python (port 5001) |
| Embeddings | Qwen3-Embedding-4B (default, configurable) |

## Quick Start

### Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Node.js | 18+ | `node -v` |
| Python | 3.11 -- 3.12 | `python --version` |
| uv | Latest | `uv --version` |
| Neo4j | 5+ | `neo4j --version` |

### Setup

```bash
cp .env.example .env
# Edit .env with your API keys and Neo4j credentials

npm run setup:all   # Install all dependencies
npm run dev          # Start frontend + backend
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

### Docker

```bash
cp .env.example .env
docker compose up -d
```

## Documentation

- [MiroClaw Spec](docs/specs/miroclaw.md) -- Behaviour-first implementation spec
- [MiroClaw Roadmap](docs/miroclaw-roadmap.md) -- Product vision and architecture decisions

## Acknowledgments

Built on the [MiroFish](https://github.com/666ghj/MiroFish) foundation. Simulation engine powered by [CAMEL-AI](https://github.com/camel-ai/camel) with [OASIS](https://github.com/camel-ai/oasis) social platforms.

## License

AGPL-3.0
