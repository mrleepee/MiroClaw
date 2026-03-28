# MiroClaw Product Roadmap

> MiroFish agents with real-time web research capabilities, collaborative knowledge graph curation, and adversarial evidence testing.

## 1. Problem Statement

MiroFish simulations currently generate discourse from frozen knowledge — agent personas are built from a knowledge graph constructed at setup time, and no new evidence enters the system during simulation. This produces debates that are rhetorically interesting but epistemically closed: agents argue from what they were given, not from what exists.

This limits the value of simulation outputs for hypothesis testing, prediction, and research synthesis. A framework-testing simulation (e.g., The Narcissist State) cannot produce genuinely surprising results if agents cannot discover evidence the seed documents didn't contain.

### What MiroClaw Changes

Agents gain the ability to research the open web during simulation rounds, distill findings into structured facts, and add them to a shared knowledge graph that grows and is contested throughout the simulation. The post-simulation graph becomes a collaboratively-researched, adversarially-tested knowledge base — potentially more valuable than the social media discourse itself.

---

## 2. Core Concepts

### 2.1 Research-Armed Agents

Each agent has access to a sandboxed web browser (via OpenClaw's `agent-browser` skill using Chrome DevTools Protocol). During each simulation round, agents can search the web and read pages before composing their social media posts.

**Spec: Agent Browser Integration**
- Each agent receives a named browser profile managed by OpenClaw's CDP-based browser tool
- Browser sessions are isolated per agent (no cross-agent cookie/session leakage)
- Agents interact via CLI commands: `navigate`, `snapshot`, `extract`, `search`
- Browser runs on loopback only; no public network exposure from the gateway

### 2.2 The Living Knowledge Graph

The Neo4j knowledge graph is no longer frozen after the build phase. Agents contribute new facts discovered during research. The graph becomes a living artifact that grows, is contested, and is curated throughout the simulation.

**Spec: Graph Growth Model**
- Initial state: graph built from seed documents (existing MiroFish flow)
- During simulation: agents add new triples discovered via web research
- Post-simulation: the final graph is an artifact containing both seed knowledge and agent-discovered evidence, with provenance and vote metadata on every node

### 2.3 Triple-Format Knowledge Constraint

Agent additions to the graph must be expressed as structured triples — not free text, not page dumps. This keeps the graph queryable, compact, and native to Neo4j's node-edge-node model.

**Spec: Triple Structure**

```
(Subject Entity) —[RELATIONSHIP]-> (Object Entity)
  {
    date: "2015-05-29",
    source_url: "https://...",
    added_by_agent: "agent_042",
    added_round: 37,
    upvotes: 12,
    downvotes: 3,
    status: "accepted" | "contested" | "pruned"
  }
```

Examples:
```
(Ross Ulbricht) —[SENTENCED_TO]-> (Life Without Parole)
  { court: "SDNY", date: "2015-05-29", source_url: "..." }

(eBay) —[RESOLVES_ANNUALLY]-> (60M Disputes)
  { method: "private arbitration", source: "Richman 2004" }

(Tornado Cash Developers) —[CHARGED_WITH]-> (Money Laundering Conspiracy)
  { jurisdiction: "SDNY", date: "2023-08-23", source_url: "..." }
```

### 2.4 Research Budget

Agents have a fixed research budget per round that forces prioritisation. They can look at more than they can keep — the constraint is on what enters the shared graph, not on what informs their posts.

**Spec: Per-Agent Per-Round Budget**

| Action | Budget | Notes |
|---|---|---|
| Web searches | 3 | Full search queries via browser |
| Page reads | 3 | Can extract text/snapshots from up to 3 URLs |
| Graph additions | 1 | Must be a structured triple. Agent chooses the single most important finding to commit. |
| Votes on others' additions | N (configurable) | Upvote or downvote new triples added by other agents this round |

The asymmetry is intentional: agents can research broadly (3 searches, 3 reads) but must distill ruthlessly (1 addition). This mirrors how human researchers work — you read 20 papers and cite 3.

### 2.5 Voting System

Each round, agents can upvote or downvote new triples added by other agents. Votes are stored as properties on graph edges/nodes and drive the curator's pruning decisions.

**Spec: Voting Mechanics**

- Votes are per-agent, per-triple, per-round (no double-voting)
- Votes may be weighted by `influence_weight` from the agent's simulation config
- Vote counts are stored as node/edge properties: `upvotes`, `downvotes`
- **Contested** status: assigned when a triple has significant votes on BOTH sides (e.g., upvotes > threshold AND downvotes > threshold)
- Contested triples are the most analytically valuable — they represent genuine factual disputes between agents with different explanatory frames

### 2.6 Curator Agent

A special non-posting agent that runs after each round (or every N rounds) to maintain graph quality. The curator is adversarial to bloat, not to any position.

**Spec: Curator Responsibilities**

| Task | Method | Trigger |
|---|---|---|
| Merge near-duplicates | Cosine similarity on triple text > threshold | Every round |
| Prune low-value nodes | Remove triples below vote threshold after N rounds of low engagement | Every N rounds |
| Flag contested nodes | Mark triples with high upvotes AND high downvotes as `status: contested` | Every round |
| Enforce graph size budget | If total new triples exceed ceiling, prune lowest-voted first | When ceiling reached |

**Spec: Curator Constraints**
- The curator NEVER evaluates factual accuracy — only engagement and redundancy
- Contested nodes are protected from pruning regardless of net vote score
- Pruned nodes are soft-deleted (moved to a `pruned_triples` collection) for post-simulation analysis
- Curator actions are logged with reasoning for full audit trail

---

## 3. Round Lifecycle

```
Round N begins
  |
  |-- Phase 1: RESEARCH (parallel, per agent)
  |     Agent reads current graph state + recent posts
  |     Agent performs up to 3 web searches
  |     Agent reads up to 3 pages
  |     Agent may consult an Oracle (1 consultation per round)
  |     Agent selects 1 finding to add as structured triple
  |
  |-- Phase 2: CONTRIBUTE (parallel, per agent)
  |     Agent writes 1 triple to graph (with provenance metadata)
  |     Agent composes social media post (may reference research or oracle advice)
  |
  |-- Phase 3: VOTE (parallel, per agent)
  |     Agent sees new triples added this round by other agents
  |     Agent upvotes/downvotes based on their explanatory frame
  |
  |-- Phase 4: CURATE (single curator agent)
  |     Merge near-duplicate triples
  |     Flag contested triples
  |     Prune if graph size ceiling exceeded
  |
  |-- Phase 5: ORACLE FORECAST (every N rounds, oracle agents only)
  |     Each oracle produces calibrated probability estimates on core questions
  |     Forecasts logged with round number for tracking confidence drift
  |
Round N+1 begins
```

---

## 4. Post-Simulation Artifacts

### 4.1 The Contested Knowledge Graph

The primary output of a MiroClaw simulation is not the social media discourse — it's the knowledge graph. After 96 rounds with 80 agents, each adding 1 triple per round:

- ~7,680 new triples attempted
- ~30-40% pruned by curator as duplicates or low-vote noise
- ~4,500 researched, voted-on, structured facts remain
- Contested nodes represent genuine evidence disputes

### 4.2 Provenance Trail

Every triple carries:
- Which agent added it
- What round it was added
- What search query led to its discovery
- What URL it was sourced from
- Full vote history across rounds
- Curator actions (merged, pruned, flagged)

### 4.3 Dispute Map

Contested triples can be extracted as a standalone report: "These are the specific factual claims where framework-aligned and alternative-explanation agents genuinely disagreed about reality." For the book author, this is the most valuable output — it shows exactly where the framework's predictions meet real-world evidence that is genuinely ambiguous.

---

## 5. Architecture Decisions

### 5.1 Browser Runtime

**Decision: OpenClaw `agent-browser` via CDP**

- Rust-based headless browser automation
- Per-agent named browser profiles in `~/.openclaw/openclaw.json`
- Loopback-only HTTP API for agent actions
- Supports session persistence (auth workflows survive across rounds)
- Already has CLI interface compatible with tool-use patterns

**Alternative considered:** Playwright via Python. Rejected because OpenClaw's agent-browser is purpose-built for AI agent use, has accessibility tree extraction, and the skill ecosystem allows extension.

### 5.2 Graph Write Path

**Decision: Triple validation before write**

New triples pass through a validation layer before entering Neo4j:
1. Schema check: subject and object must map to existing or valid new entity types
2. Dedup check: cosine similarity against existing triples (reject if > 0.95 similarity)
3. Source check: `source_url` must be reachable and the triple must be extractable from the page content
4. Format check: structured triple format, not free text

### 5.3 Simulation Engine

**Decision: Build on CAMEL's Workforce and Societies, not OASIS's flat loop**

OASIS is a thin wrapper around CAMEL's `ChatAgent` that adds social media action tools and a flat round-robin simulation loop ("every agent posts each round"). MiroClaw's phased rounds (research → contribute → vote → curate) and longer-running simulations with evolving agents need richer coordination than OASIS provides.

CAMEL's own ecosystem offers the right primitives:

| CAMEL Module | MiroClaw Use |
|---|---|
| `societies/workforce/` | Structured agent coordination — task decomposition, worker assignment, inter-agent channels. Replaces OASIS's flat loop with phased rounds where agent teams can specialise (researchers, debaters, curators) |
| `societies/role_playing.py` | Richer agent-agent interactions — structured two-agent dialogue with critic. For deep debate sequences between opposing agents, not just "post and react to feed" |
| `agents/ChatAgent` | Still the base agent class (same as OASIS uses). MiroClaw agents inherit from `ChatAgent` directly, bypassing OASIS's `SocialAgent` |
| `toolkits/FunctionTool` | Agent action tools — research, graph write, vote. Same mechanism OASIS uses, just with MiroClaw-specific tools |

**OASIS is retained as one interaction surface**, not the framework. The social media platforms (Twitter/Reddit databases, feed algorithms, follower graphs) remain useful for generating discourse. But the simulation engine — round orchestration, agent memory, task coordination — is CAMEL-native.

**What this changes:**
- Round orchestration uses Workforce task channels, not OASIS's `round_robin()` loop
- Agent creation uses CAMEL's `ChatAgent` directly, with MiroClaw-specific tools registered via `FunctionTool`
- OASIS's `SocialPlatform` and database layer are used as a plugin for social media interactions, not as the simulation backbone
- New interaction modes (structured debates, evidence challenges) use `RolePlaying` societies alongside social media posting

### 5.4 Agent Memory: Hybrid Memory with Compaction

**Decision: Build on CAMEL's `LongtermAgentMemory`, add structured compaction on top**

**Background:** OASIS's `SocialAgent` inherits CAMEL's `ChatAgent` with no memory management. In a 72-round simulation with 182 agents, this caused unbounded memory growth — 40GB RAM, OOM crash at round 44. The immediate fix (token-limited windowed memory, see `apply_memory_limits()` in `run_parallel_simulation.py`) prevents the crash but has a ceiling: agents can only retain as much history as fits in the model's context window.

For MiroClaw — with longer simulations, research phases generating more context per round, and the need for agents to track evidence across potentially hundreds of rounds — a fixed context window is insufficient.

**CAMEL already provides the building blocks.** Rather than building a custom memory system from scratch, MiroClaw layers on top of what CAMEL has:

| CAMEL Component | What it provides | MiroClaw extension |
|---|---|---|
| `ChatHistoryMemory` | Recent message window with token-limited pruning | Used as-is for recent rounds |
| `VectorDBMemory` | Semantic similarity retrieval of past messages | Enables agents to recall relevant past evidence when debating a specific topic |
| `LongtermAgentMemory` | Hybrid: `ChatHistoryBlock` (recent) + `VectorDBBlock` (semantic retrieval) | **The base class for MiroClaw agent memory** |
| `ScoreBasedContextCreator` | Token-budgeted context assembly | Controls how much recent vs. retrieved memory fits in each prompt |
| Vector DB backends (Qdrant, FAISS, Chroma) | Persistent embedding storage | Agent memories survive across sessions — agents evolve across simulation runs |

**What MiroClaw adds on top: structured compaction summaries**

`LongtermAgentMemory` solves the retrieval problem (finding relevant past messages) but not the narrative coherence problem. An agent debating in round 150 needs to know "I shifted from supportive to neutral at round 22 because of [evidence]" — that's a narrative arc, not a similarity match.

MiroClaw adds a `CompactionBlock` alongside CAMEL's existing blocks:

```
MiroClawAgentMemory(LongtermAgentMemory):
  ├── CompactionBlock        ← NEW: structured summary of position history
  │     - Positions held and shifts with triggering evidence
  │     - Graph contributions and vote history
  │     - Active debate threads
  ├── ChatHistoryBlock       ← CAMEL existing: recent N messages in full
  └── VectorDBBlock          ← CAMEL existing: semantic retrieval of older messages
```

Context window layout at prompt assembly:
```
┌──────────────────────────────────────────────────┐
│ System prompt (persona, epistemic character)      │  ~2K tokens, always present
├──────────────────────────────────────────────────┤
│ Compaction summary (rounds 1-N)                  │  ~2-4K tokens, updated periodically
│  - Key positions taken and evidence cited         │
│  - Stance changes with triggering evidence        │
│  - Graph contributions and vote outcomes          │
│  - Active debate threads                          │
├──────────────────────────────────────────────────┤
│ VectorDB retrievals (semantically relevant past) │  ~2-4K tokens, query-dependent
├──────────────────────────────────────────────────┤
│ ChatHistory (recent rounds in full detail)        │  Variable, up to remaining budget
├──────────────────────────────────────────────────┤
│ Current round environment prompt                 │  ~1-2K tokens
└──────────────────────────────────────────────────┘
```

**Compaction trigger:** When `ChatHistoryBlock` exceeds 70% of its token budget, the oldest 50% of messages are summarised by an LLM call. The summary is structured, not prose:

```
## Compacted Memory (Rounds 1-35)
### Positions held:
- NS framework: supportive → neutral (shifted round 22, triggered by [triple])
- Alternative explanation (deterrence theory): initially dismissed, now considering
### Key evidence cited:
- Round 8: Referenced DOJ enforcement statistics from [source]
- Round 15: Engaged with Academic_042's counter-argument on selection bias
### Graph contributions:
- Round 12: Added triple (DOJ) —[ENFORCED_SELECTIVELY]→ (Crypto Exchanges) [3 upvotes, 1 downvote]
### Active threads:
- Ongoing debate with Journalist_017 about enforcement proportionality
```

**Why hybrid (compaction + vector DB) beats either alone:**
1. **Compaction alone** preserves narrative arc but loses detail — an agent knows it "cited DOJ statistics in round 8" but can't recall the specific numbers
2. **Vector DB alone** retrieves relevant fragments but lacks narrative coherence — an agent can recall the DOJ statistics but doesn't know how its position evolved
3. **Both together** give agents a coherent self-narrative (compaction) plus the ability to recall specific evidence on demand (vector DB). The compaction summary says "I shifted because of [evidence X]"; the vector DB can retrieve the actual round-8 message with the full statistics

**Why this combination beats pure RAG:** The compaction summary mirrors the SOUL.md changelog pattern already spec'd for epistemic flexibility (Section 7.1). Position drift is a first-class output, not an emergent property of retrieved fragments.

**Cost model:** Compaction adds ~1 LLM call per agent per compaction event. At 70% threshold, compaction fires roughly every 50 rounds. For 182 agents over 72 rounds, that's ~182 extra LLM calls — negligible vs. the ~26K calls for the simulation itself. Vector DB operations (embed + store + query) add milliseconds, not seconds.

**Persistent storage for cross-session evolution:** Because CAMEL's `VectorDBBlock` supports persistent backends (Qdrant, FAISS, Chroma, Neo4j), agent memories can survive across simulation runs. An agent in Simulation 2 can recall evidence it discovered in Simulation 1. This is the foundation for MiroClaw's agent evolution — agents that learn across sessions, not just within a single run.

### 5.5 CAMEL Ecosystem Strategy

**Decision: Build directly on CAMEL's primitives; use OASIS and OWL patterns selectively**

The camel-ai ecosystem includes several projects. MiroClaw's relationship to each:

| Project | Repo | MiroClaw relationship |
|---|---|---|
| **CAMEL** | `camel-ai/camel` | **Foundation.** MiroClaw agents are CAMEL `ChatAgent` subclasses. Memory uses `LongtermAgentMemory`. Round orchestration uses `Workforce`. Agent interactions use `RolePlaying` societies. |
| **OASIS** | `camel-ai/oasis` | **Interaction surface.** OASIS's `SocialPlatform` database layer (Twitter/Reddit schemas, feed algorithms, follower graphs) is retained as a plugin for social media interactions. OASIS's `SocialAgent` and round loop are replaced by CAMEL-native equivalents. |
| **OWL** | `camel-ai/owl` | **Pattern reference.** OWL's MCP (Model Context Protocol) integration pattern — standardised tool discovery and invocation across agents — is the model for how MiroClaw agents discover and use research tools, graph write tools, and voting tools. OWL's Workforce optimisation techniques inform MiroClaw's agent coordination. |
| **CRAB** | `camel-ai/crab` | **Future evaluation.** CRAB's graph-based benchmarking framework provides the evaluation infrastructure for measuring simulation quality: did agents produce better predictions? Did the contested knowledge graph converge on truth? Relevant for Phase 4 (analytics). |

### 5.6 Oracle Agents and the Forecasting Model

**Decision: Introduce specialist "Oracle" agents powered by a purpose-built forecasting model**

**The concept:** In ancient Greek society, oracles — Delphi, Dodona, Didyma — were not participants in political debate. They were *consulted*. Citizens, generals, and kings sought them out before making consequential decisions. The oracle's role was not to advocate but to read the signs and speak probabilities.

MiroClaw introduces **Oracle agents** — a small number of specialist agents whose purpose is forecasting, not advocacy. They don't post opinions on social media. Instead, other agents can *consult* them during the research phase, and the simulation's final report is synthesised through their lens.

**The forecasting ecosystem**

The [OpenReward](https://openreward.ai) benchmark platform reveals a maturing ecosystem of forecasting models and evaluation frameworks. MiroClaw's oracle architecture should engage with this ecosystem at two levels: the model that powers oracle agents, and the evaluation framework that measures oracle quality.

**Primary oracle model: OpenForecaster-8B**

[OpenForecaster-8B](https://huggingface.co/nikhilchandak/OpenForecaster-8B) is the leading candidate for the Oracle model:

| Property | Detail |
|---|---|
| Base | Qwen3-8B, fine-tuned via GRPO (reinforcement learning) |
| Training objective | Joint reward: accuracy + Brier score calibration |
| Training data | [OpenForesight](https://huggingface.co/datasets/nikhilchandak/OpenForesight) — 52K+ forecasting questions from global news |
| Performance | Outperforms 100B+ general-purpose models on FutureX benchmark (July-Aug 2025) |
| Licence | MIT |
| Size | 8B params — runnable on consumer hardware |

The critical property is **calibration**. OpenForecaster is trained to minimise Brier score, meaning its probability estimates are meaningful: when it says 70%, it means 70%. General-purpose LLMs (including MiniMax-M2.7) are not calibrated — their confidence expressions are rhetorical, not statistical.

**Complementary frameworks:**

| Framework | What it does | MiroClaw role |
|---|---|---|
| [BrierBench](https://github.com/djrhails/brierbench) | Evaluates LLM forecasting on real-world binary questions from prediction markets. Uses web search + simulated time — the model researches at a simulated point in time, then forecasts. Time-weighted Brier score. | **Evaluation framework.** BrierBench's methodology is directly applicable to measuring oracle quality: simulate a point in time, let the oracle research, measure calibration against resolved outcomes. Use as the benchmark for Phase 5 acceptance testing and Phase 6 analytics. |
| [HoTPP](https://openreward.ai/task/long-horizon-events-forecasting) (Marked Temporal Point Processes) | Models *when* events happen in continuous time, not whether binary outcomes occur. Top model RMTPP achieves 38.28% accuracy (T-mAP metric). | **Future extension.** Current oracle design answers "will X happen?" — HoTPP could add "when will X happen?" time-to-event forecasting. Relevant for Phase 6+ when oracle predictions include temporal resolution, not just probability. |

The forecasting field is moving fast. OpenForecaster-8B is the best available model for local deployment today, but the oracle architecture should be model-agnostic — any OpenAI-compatible endpoint serving a calibrated forecasting model can power the oracle agents. If a better model emerges (e.g., an OpenForecaster variant trained on legal/political domains), swapping it in should require only changing the `ModelManager` endpoint URL.

**Oracle agent roles:**

| Role | How it works |
|---|---|
| **Consultation** | During the research phase, agents can invoke a `consult_oracle` tool. The oracle receives the agent's question plus relevant context from the knowledge graph, and returns a calibrated probability estimate with reasoning. Budget: each agent gets 1 oracle consultation per round. |
| **Periodic forecasts** | Every N rounds, each oracle independently produces a structured forecast on the simulation's core questions (derived from the seed documents). These forecasts are logged and become trackable — does the oracle's confidence shift as the knowledge graph grows? |
| **Report synthesis** | The post-simulation report is generated through an OpenForecaster-powered agent rather than the current general-purpose ReACT agent. The report agent has access to the full contested knowledge graph and produces calibrated probability estimates for each prediction, not just narrative analysis. |

**Oracle agent count:** Small — 2-4 per simulation. Oracles are expensive (each consultation is an LLM call to a separate model) and should be rare, not ubiquitous. The scarcity mirrors the ancient model: you don't consult the oracle about everything, only about what matters most.

**Why a separate model, not a prompt:**

You cannot make a general-purpose LLM calibrated by prompting it to "think in probabilities." Calibration requires training signal (Brier score optimisation). OpenForecaster's 8B parameters with calibration training outperform 100B+ general-purpose models on forecasting — the specialisation matters.

**Running forecasting models locally:**

The oracle architecture requires a local model serving an OpenAI-compatible API. OpenForecaster-8B (8B params) is practical for co-deployment alongside the main simulation:

```
Hardware requirements:
├── Main simulation agents (MiniMax-M2.7 via API)     → cloud API, no local GPU needed
└── Oracle agents (forecasting model, local)           → local GPU / unified memory

Deployment options (OpenForecaster-8B as example — swap for any GGUF/safetensors model):
┌─────────────────────────────────────────────────────────────────┐
│ Option A: Ollama (simplest)                                     │
│   ollama pull nikhilchandak/OpenForecaster-8B                   │
│   ollama serve  # exposes OpenAI-compatible API on :11434       │
│   VRAM: ~5-6GB quantised (Q4_K_M), ~16GB F16                   │
├─────────────────────────────────────────────────────────────────┤
│ Option B: vLLM (highest throughput)                             │
│   pip install vllm                                              │
│   vllm serve nikhilchandak/OpenForecaster-8B                    │
│     --dtype auto --max-model-len 8192                           │
│   VRAM: ~16GB F16, ~8GB AWQ/GPTQ quantised                     │
│   Benefit: batches concurrent oracle consultations efficiently  │
├─────────────────────────────────────────────────────────────────┤
│ Option C: llama.cpp / LM Studio (Mac-friendly)                  │
│   Download GGUF quantisation from HuggingFace                   │
│   llama-server -m OpenForecaster-8B-Q4_K_M.gguf --port 8080    │
│   VRAM: ~5GB Q4, runs on M-series Mac unified memory            │
│   Benefit: no CUDA needed, runs on the same Mac as Flask        │
└─────────────────────────────────────────────────────────────────┘
```

For MiroClaw development on Mac: **Option C** (llama.cpp / LM Studio) is the path of least resistance. An M-series Mac with 32GB+ unified memory can run both the Flask server and a quantised 8B model simultaneously. The oracle's inference speed doesn't need to be fast — consultations are infrequent (1 per agent per round, 2-4 oracles total).

**Model swap:** When a better forecasting model emerges (domain-specific fine-tune, larger calibrated model, or MSA-extended variant), replace the GGUF file and restart the server. CAMEL's `ModelManager` endpoint URL is the only configuration that changes.

**Integration with CAMEL:** Oracle agents are `MiroClawAgent(ChatAgent)` instances configured with a CAMEL `ModelManager` pointing at the local OpenForecaster endpoint (OpenAI-compatible API). The `consult_oracle` tool on regular agents makes a CAMEL `RolePlaying` call to the oracle agent with the question and graph context.

**Why CAMEL-native instead of extending OASIS:**
1. OASIS uses ~5 of CAMEL's 31 subpackages. MiroClaw needs Workforce, LongtermAgentMemory, persistent storage, RolePlaying — none of which OASIS touches.
2. OASIS's `SocialAgent` adds social media tools but also adds assumptions (flat round loop, no memory management, single-model agents) that MiroClaw must override.
3. Going CAMEL-native means MiroClaw benefits from upstream CAMEL improvements (new memory strategies, new society patterns, new storage backends) without waiting for OASIS to expose them.
4. OASIS's social platform layer remains valuable — it provides realistic social media dynamics. Keeping it as a plugin preserves this value without inheriting OASIS's architectural limitations.

---

## 6. Implementation Phases

### Phase 0: CAMEL Foundation
Establish the CAMEL-native agent and orchestration layer that replaces OASIS's simulation loop. This is the architectural shift — everything after this phase builds on CAMEL primitives directly.

**Acceptance criteria:**
- [ ] `MiroClawAgent(ChatAgent)` base class created — bypasses OASIS's `SocialAgent`, registers MiroClaw-specific tools via `FunctionTool`
- [ ] `MiroClawAgentMemory(LongtermAgentMemory)` implemented — `ChatHistoryBlock` + `VectorDBBlock` + `CompactionBlock` with structured summary generation
- [ ] Round orchestration uses CAMEL `Workforce` task channels — phased rounds (research → contribute → vote → curate) replace OASIS's flat `round_robin()`
- [ ] OASIS `SocialPlatform` integrated as a plugin — agents can post to Twitter/Reddit databases via registered tools, but the simulation loop is CAMEL-native
- [ ] Persistent vector DB backend selected and configured (Qdrant or FAISS) for agent memory that survives across sessions
- [ ] Smoke test: run a minimal simulation (10 agents, 10 rounds) through the CAMEL-native loop with social media posting via OASIS platform plugin

### Phase 1: Graph Write API
Add a write path to the Neo4j knowledge graph that accepts structured triples with provenance metadata during simulation. No browser integration yet — triples are LLM-generated from existing knowledge.

**Acceptance criteria:**
- [ ] `POST /api/graph/triple` accepts a structured triple and writes to Neo4j
- [ ] Provenance metadata (agent_id, round, source) stored on every new node/edge
- [ ] Deduplication via cosine similarity rejects near-duplicate triples
- [ ] Existing graph queries return both seed and agent-added triples
- [ ] Graph write registered as a `FunctionTool` on `MiroClawAgent` — agents invoke it through CAMEL's tool-use mechanism

### Phase 2: Voting and Curation
Add the voting system and curator agent.

**Acceptance criteria:**
- [ ] Agents can upvote/downvote triples via registered `FunctionTool`
- [ ] Vote counts stored as node properties and queryable
- [ ] Contested status auto-assigned when upvotes AND downvotes exceed threshold
- [ ] Curator agent (a specialised `MiroClawAgent` with curator tools) runs in the curate phase of each round
- [ ] Pruned nodes soft-deleted to `pruned_triples` for post-analysis
- [ ] Curator actions logged with reasoning

### Phase 3: Browser Integration
Add OpenClaw agent-browser as a research tool available to agents during the research phase.

**Acceptance criteria:**
- [ ] `agent-browser` installed and configured with per-agent profiles
- [ ] Research tools (search, navigate, extract) registered as `FunctionTool` on `MiroClawAgent`
- [ ] Workforce orchestration enforces research phase before contribute phase
- [ ] Agents perform up to 3 searches and 3 page reads per round
- [ ] Research findings flow into agent memory (both `ChatHistoryBlock` and `VectorDBBlock`) for cross-round recall
- [ ] Agent selects 1 finding to commit as structured triple via graph write tool
- [ ] Research budget enforced via tool invocation limits (hard limit, not advisory)

### Phase 4: Cross-Session Evolution
Enable agents to carry memory and evolved positions across simulation runs.

**Acceptance criteria:**
- [ ] `VectorDBBlock` persists to disk between simulations (Qdrant/FAISS)
- [ ] `CompactionBlock` summaries serialised and reloaded for returning agents
- [ ] Agent identity (SOUL.md equivalent) updated with cross-session changelog
- [ ] Simulation 2 agents can recall evidence discovered in Simulation 1
- [ ] Position drift is tracked cumulatively across sessions, not just within a single run
- [ ] Guard rails: agents can be reset to "fresh" state for control experiments

### Phase 5: Oracle Agents and Forecasting Model
Introduce OpenForecaster-8B as a locally-hosted specialist model powering Oracle agents for consultation and report synthesis.

**Acceptance criteria:**
- [ ] OpenForecaster-8B deployed locally via llama.cpp or Ollama, exposed as OpenAI-compatible API
- [ ] `OracleAgent(MiroClawAgent)` subclass created — uses CAMEL `ModelManager` pointing at local OpenForecaster endpoint
- [ ] `consult_oracle` tool registered on regular `MiroClawAgent` — sends question + graph context to oracle, returns calibrated probability estimate
- [ ] Oracle consultation budget enforced (1 per agent per round)
- [ ] Periodic oracle forecasts (every N rounds) on core simulation questions, logged with timestamps
- [ ] Oracle confidence drift tracked across rounds — visualisable as a time series
- [ ] Report generation powered by OpenForecaster — final report includes calibrated probability estimates, not just narrative analysis
- [ ] A/B comparison: report quality from OpenForecaster vs. general-purpose model (current MiniMax ReACT agent)

### Phase 6: Post-Simulation Analytics
Build the artifact extraction layer — dispute maps, provenance reports, graph diff (seed vs. final).

**Acceptance criteria:**
- [ ] Export contested triples as standalone report
- [ ] Graph diff showing seed graph vs. post-simulation graph
- [ ] Per-agent research audit trail (what they searched, what they read, what they added)
- [ ] Vote distribution analysis (which triples were most contested, by which agent types)
- [ ] Position drift visualisation — per-agent stance over time, with triggering evidence
- [ ] Oracle forecast time series — how oracle confidence evolved as the knowledge graph grew
- [ ] Cross-session evolution report — how agents changed across multiple simulation runs
- [ ] Integration with existing MiroFish report agent (ReACT loop can query agent-added triples)
- [ ] Evaluation framework (CRAB-informed) for measuring prediction quality — compare oracle forecasts against resolved outcomes

---

## 7. Open Questions

### Resolved

| Question | Resolution |
|---|---|
| What happens when an agent's research contradicts their persona? | **Agents should be able to change their position.** Intellectual honesty is the default — agents can update their stance when evidence warrants it. But this is modulated by epistemic flexibility (see 7.1 below). |

### 7.1 Epistemic Flexibility and the SOUL.md Model

**Concept:** Borrowing from OpenClaw's `SOUL.md` pattern — where each agent has a persistent identity document that defines who they are — each MiroClaw agent gets an equivalent that includes not just their persona but their *epistemic character*: how open they are to changing their mind.

**The `epistemic_flexibility` parameter:**

Each agent has a probability factor (0.0 to 1.0) representing how likely they are to update their position when confronted with contradicting evidence:

| Value | Behaviour | Real-world analogue |
|---|---|---|
| 0.0 - 0.2 | **Entrenched.** Will research selectively, dismiss contradicting evidence, double down when challenged. May still add evidence to the graph but frames it to support existing position. | True believers, institutional actors with career lock-in, ideologues |
| 0.3 - 0.5 | **Resistant but persuadable.** Needs strong, repeated evidence to shift. Will acknowledge contradictions privately (in research phase) before reflecting them in posts. Position drift is slow. | Most people in most debates |
| 0.6 - 0.8 | **Open.** Actively seeks disconfirming evidence. Will change position mid-simulation if the evidence warrants it. Posts may visibly evolve. | Journalists, researchers, genuinely curious citizens |
| 0.9 - 1.0 | **Hyper-flexible.** Shifts easily — possibly too easily. May appear inconsistent. Useful as a canary: if these agents converge on a position, the evidence is likely strong. | Devil's advocates, contrarians, undecided observers |

**Distribution across the agent population:**

The spread should mirror real discourse — most agents in the 0.2-0.5 range, with tails at both ends:
- ~20% entrenched (0.0-0.2) — institutional actors, committed advocates
- ~50% resistant but persuadable (0.3-0.5) — the movable middle
- ~25% open (0.6-0.8) — journalists, researchers, curious citizens
- ~5% hyper-flexible (0.9-1.0) — canary agents

This distribution can be set during profile generation — either by the LLM based on entity type, or as a configurable parameter in `AgentActivityConfig`.

**How it works mechanically:**

When an agent's research in Round N finds evidence contradicting their current position:
1. Roll against `epistemic_flexibility` — if the roll succeeds, the agent's internal stance shifts
2. Stance shift is gradual, not binary — the agent's `stance` field moves one step (e.g., `supportive` → `neutral`, not `supportive` → `opposing`)
3. The agent's SOUL.md equivalent is updated with a changelog: "Round 37: shifted from supportive to neutral after finding [triple]"
4. Future posts reflect the new position
5. If the roll fails, the agent acknowledges the evidence internally but frames it to support their existing position in public posts — this is a realistic and interesting behaviour

**What this produces:**

Position drift over time becomes a measurable simulation output. You can track:
- Which agents shifted and when
- What evidence caused the shift
- Whether shifted agents cluster by type or by the evidence they found
- Whether the simulation converges toward one position or remains genuinely divided

For the Narcissist State test: if 30% of initially framework-aligned agents shift to neutral/alternative by Round 96 based on evidence they found themselves, that tells the author something important. If 0% shift, that also tells them something.

**Open design question:** How does epistemic flexibility interact with the voting system? Should an agent who has shifted positions re-vote on triples they previously voted on? This could create interesting dynamics where contested triples become accepted as agents shift.

### Still Open

| Question | Context | Impact |
|---|---|---|
| Should agents see each other's research queries? | Transparency vs. strategic search behaviour. If agents see what others searched, they may counter-research. If not, they may duplicate effort. | Affects simulation dynamics significantly |
| How does the curator handle contradictory triples that are both well-sourced? | e.g., "Exchange had zero fraud complaints" vs. "Exchange had 3 compliance warnings" — both true, different scope | Core to the contested-knowledge model |
| Should the research budget scale with simulation length? | 96 rounds x 80 agents x 1 triple = 7,680 triples. At 200 rounds that's 16,000. | Graph size ceiling may need to be dynamic |
| How do we handle paywalled or geo-restricted content? | Some academic papers, court records, news articles behind paywalls | May need institutional access or accept that some evidence is unreachable |
| Is the curator a fixed algorithm or an LLM agent? | Algorithm is deterministic and auditable. LLM is more flexible but less predictable. | Affects trust in the curation process |
| How does epistemic flexibility interact with voting? | Should agents who shift positions re-vote on previously voted triples? Creates interesting dynamics but adds complexity. | Could cause contested triples to flip status mid-simulation |
| How to model epistemic flexibility accurately? | Real opinion change is driven by trust networks, emotional stakes, identity threat — not just evidence quality. A simple probability roll may not capture this. | Hard to model well. May need iteration across multiple simulations to calibrate. |
| CAMEL version pinning vs. tracking HEAD? | OASIS pins an older CAMEL version that lacks newer features (OWL's MCP patterns, latest Workforce improvements). MiroClaw going CAMEL-native means we control the CAMEL version directly — but tracking HEAD risks breaking changes. | Pin to a release, upgrade deliberately. Budget time for version bumps. |
| Which vector DB backend for persistent agent memory? | Qdrant (managed service, rich filtering), FAISS (local, fast, no server), Chroma (simple API). Need to support both local dev and production deployment. | Affects Phase 0 and all subsequent phases. FAISS for dev, Qdrant for production is a common pattern. |

---

## 8. Success Metrics

For the first MiroClaw simulation (Narcissist State framework test):

| Metric | Target | Why it matters |
|---|---|---|
| Agent-added triples that survive curation | > 3,000 | Demonstrates agents can find and distill real evidence |
| Contested triples | > 200 | Demonstrates genuine factual disputes emerge |
| Triples with valid source URLs | > 90% | Demonstrates evidence is real, not hallucinated |
| Agent types on both sides of contested triples | Framework-aligned AND alternative-explanation agents on each | Demonstrates the debate is two-sided |
| Post-simulation graph used in report generation | Report agent cites agent-discovered evidence | Demonstrates the living graph feeds back into analysis |
| Oracle Brier score on resolvable questions | < 0.25 | Demonstrates calibrated forecasting — better than uninformed base rate |
| Oracle confidence drift correlates with evidence | Confidence moves in direction of accumulating evidence | Demonstrates oracles respond to the growing knowledge graph, not just prior training |
| Oracle-generated report vs. general-purpose report | Blind evaluation prefers oracle report | Demonstrates forecasting-trained model produces better analytical output |
