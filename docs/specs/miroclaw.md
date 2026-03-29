# MiroClaw Behaviour Spec

> Research-armed multi-agent prediction engine. Agents discover evidence from the open web, contribute structured triples to a living knowledge graph, and vote on each other's findings.

**Status:** All "Must" requirements implemented. Phases 0–2 fully coded. Phase 3 research tools wired to camofox-browser REST API with session isolation and graceful fallback. Phase 4 persistence implemented. Phase 5 oracle/epistemic logic implemented. Phase 6 analytics backend + API complete. Phase 7 UI refresh implemented (design tokens, dark mode, SVG icons, accessibility, chart components).

### Implementation Progress

All tool classes are registered as CAMEL FunctionTools via factory functions in `tools/__init__.py`. `MiroClawAgent(ChatAgent)` has phase-aware tool swapping and budget integration. The critical FunctionTool wiring gap is resolved.

---

## Requirements

| ID | Name | Pri | Description | Status |
|----|------|-----|-------------|--------|
| R01 | CAMEL-native agents | Must | Replace OASIS `SocialAgent` with `MiroClawAgent(ChatAgent)`, tools via `FunctionTool` | Implemented — ChatAgent extended, FunctionTool factories wired, phase-aware tool swapping |
| R02 | Phased round orchestration | Must | Research -> Contribute -> Vote -> Curate -> Oracle phases via CAMEL `Workforce` task channels | Implemented — orchestrator runs 5-phase loop with async gather |
| R03 | Hybrid agent memory | Must | `LongtermAgentMemory` with `ChatHistoryBlock` + `VectorDBBlock` + new `CompactionBlock` for narrative coherence | Implemented — memory.py with ChatHistoryMemory + CompactionBlock, LLM-powered compaction |
| R04 | OASIS platform plugin | Must | Retain Twitter/Reddit databases and feed algorithms as interaction surface, not simulation backbone | Implemented — OasisPlatformPlugin wired as FunctionTool via create_contribute_tools |
| R05 | Living knowledge graph | Must | Agents add structured triples to Neo4j during simulation with full provenance metadata | Implemented — MiroClawGraphWriteAPI with write_triple, provenance, stats |
| R06 | Triple validation | Must | Schema check, cosine dedup (>0.95 rejected), source URL reachability, structured format enforcement | Implemented — TripleValidator with 4-stage pipeline including HTTP HEAD |
| R07 | Research budget | Must | Per-agent per-round hard limits: 3 web searches, 3 page reads, 1 graph addition | Implemented — BudgetTracker/RoundBudget in budget.py |
| R08 | Voting system | Must | Per-agent per-triple per-round votes; contested status auto-assigned when both sides exceed threshold | Implemented — VotingTool with upvote/downvote/double-vote prevention |
| R09 | Curator agent | Must | Non-posting agent: merge near-dupes, prune low-vote, flag contested, enforce graph size ceiling | Implemented — CuratorAgent with merge/prune/flag/ceiling + audit trail |
| R10 | Browser integration | Must | Camofox-browser REST client; per-agent isolated browser sessions via userId/sessionKey | Implemented — CamofoxBrowserClient with search/extract/health, session isolation, graceful fallback |
| R11 | Oracle agents | Should | Calibrated forecasting via locally-hosted model (OpenForecaster-8B); consultation + periodic forecasts | Implemented — OracleConsultationTool with budget + consultation log, no model deployment |
| R12 | Epistemic flexibility | Should | Probability-driven stance shifts (0.0-1.0) with SOUL.md-style identity changelog | Implemented — roll_epistemic_flexibility() with gradual one-step shifts + changelog |
| R13 | Cross-session evolution | Should | Persistent VectorDB + serialised CompactionBlock summaries across simulation runs | Implemented — save_to_disk/load_from_disk for CompactionBlock + IdentityDocument persistence |
| R14 | Post-simulation analytics | Should | Dispute maps, provenance trails, position drift visualisation, graph diff, oracle time series | Implemented — MiroClawAnalytics service + 7 REST endpoints + Chart.js chart components |
| R15 | Retain frontend | Must | Vue 3 frontend adapts API calls to new endpoints; same user-facing workflow | Implemented — design tokens, dark mode, SVG icons, accessibility, toast notifications, chart components |
| R16 | Retain report agent | Must | ReACT report agent extended with MiroClaw-specific tools (contested triples, provenance, oracle forecasts) | Implemented — AnalyticsTools class with query_disputed/provenance/oracle_forecasts/stance_history |
| R17 | Retain ontology pipeline | Must | Standards-based ontology (FOAF actors + Schema.org context) feeds MiroClaw agent creation unchanged | Implemented — unchanged from MiroFish |

---

## Not in scope

| Item | Justification |
|------|---------------|
| Mobile frontend | Research/analysis tool, desktop-first |
| Multi-tenant auth | Single-user local deployment; auth adds complexity without value |
| New social platform types | Twitter + Reddit cover the discourse model; new platforms are future work |
| Agent fine-tuning | Agents are configured via prompts and persona docs, not trained |
| Real-time collaborative editing | Single-operator workflow |
| CI/CD pipeline | Manual deployment; infrastructure automation is a separate concern |

---

## Phase 0: CAMEL Foundation

**Status:** Implemented
**Satisfies:** R01, R02, R03, R04
**Files:** `backend/app/agents/miroclaw_agent.py`, `backend/app/agents/memory.py`, `backend/app/agents/round_orchestrator.py`, `backend/app/agents/tools/budget.py`, `backend/app/agents/tools/__init__.py`

Replace the OASIS flat simulation loop with CAMEL-native agent creation, phased round orchestration, and hybrid memory. OASIS social platforms become a plugin for Twitter/Reddit interactions.

**Implementation audit (2026-03-29, updated):**
- `MiroClawAgent(ChatAgent)` exists at `miroclaw_agent.py:84`
- Phase enum exists: RESEARCH, CONTRIBUTE, VOTE, CURATE, ORACLE
- Orchestrator runs 5-phase loop with parallel execution per phase
- Memory classes implemented: ChatHistoryMemory (CAMEL), CompactionBlock (MiroClaw)
- BudgetManager/RoundBudget implemented in `budget.py`
- FunctionTool factories in `tools/__init__.py` — 8 per-tool factories + 4 phase aggregators (research, contribute, vote, curate)
- Phase-aware tool swapping via `_swap_active_tools()` on `set_phase()`
- Epistemic flexibility with population distribution + runtime roll logic
- All import chains verified passing (17/17) — `OpenAITokenCounter` from `camel.utils`
- `curator_tools.py` provides FunctionTool wrappers for Curate phase operations

### Behaviour 0.1: Agent creation from graph entities

**Given** a Neo4j graph with actor entities filtered by `actors_only=True`
**And** the existing `OasisProfileGenerator` has produced agent profiles
**When** the simulation is initialised
**Then** each agent profile becomes a `MiroClawAgent(ChatAgent)` instance
**And** each agent has MiroClaw tools registered via CAMEL `FunctionTool`
**And** each agent has a persona derived from the graph entity and its relationships

**Traces to:** R01, R17

### Behaviour 0.2: Phased round execution

**Given** a configured MiroClaw simulation with N agents
**When** a simulation round executes
**Then** it progresses through exactly 5 phases in order:
  1. **Research** — agents read graph state, perform web searches, read pages, consult oracle (parallel, per-agent)
  2. **Contribute** — agents write 1 triple to graph and compose social media post (parallel, per-agent)
  3. **Vote** — agents upvote/downvote new triples from other agents this round (parallel, per-agent)
  4. **Curate** — curator agent merges, prunes, and flags triples (single agent)
  5. **Oracle Forecast** — oracle agents produce calibrated forecasts on core questions (every N rounds, oracle agents only)

**And** agents cannot execute actions from a later phase during an earlier phase
**And** round orchestration uses CAMEL `Workforce` task channels, not OASIS `round_robin()`

**Traces to:** R02

### Behaviour 0.3: Hybrid memory initialisation

**Given** a new `MiroClawAgent` is created
**When** its memory system is initialised
**Then** it contains three memory blocks:
  - `ChatHistoryBlock` — recent N messages in full detail (token-limited)
  - `VectorDBBlock` — semantic similarity retrieval of older messages
  - `CompactionBlock` — structured summary of position history (new, MiroClaw-specific)
**And** the memory system extends CAMEL's `LongtermAgentMemory`
**And** `ScoreBasedContextCreator` controls token budget allocation across blocks

**Traces to:** R03

### Behaviour 0.4: Memory compaction trigger

**Given** an agent's `ChatHistoryBlock` has exceeded 70% of its token budget
**When** the compaction process fires
**Then** the oldest 50% of messages are summarised by an LLM call
**And** the summary is structured (not prose) with sections:
  - Positions held and shifts with triggering evidence
  - Key evidence cited with round numbers
  - Graph contributions and vote outcomes
  - Active debate threads
**And** the structured summary is stored in the `CompactionBlock`
**And** the summarised messages are removed from `ChatHistoryBlock`

**Traces to:** R03

### Behaviour 0.5: Context window assembly

**Given** an agent is about to act in a simulation round
**When** its prompt is assembled
**Then** the context window is composed in this order:
  1. System prompt (persona, epistemic character) — ~2K tokens, always present
  2. Compaction summary (cumulative) — ~2-4K tokens
  3. VectorDB retrievals (semantically relevant past) — ~2-4K tokens, query-dependent
  4. ChatHistory (recent rounds in full) — variable, up to remaining budget
  5. Current round environment prompt — ~1-2K tokens
**And** total tokens stay within the model's context limit

**Traces to:** R03

### Behaviour 0.6: OASIS social platform as plugin

**Given** a `MiroClawAgent` with a `create_post` tool registered
**When** the agent invokes `create_post` during the Contribute phase
**Then** the post is written to OASIS's Twitter/Reddit SQLite database
**And** the post appears in other agents' feeds via OASIS's feed algorithm
**And** the simulation loop itself is CAMEL-native (Workforce), not OASIS's `round_robin()`

**Traces to:** R04

### Behaviour 0.7: Smoke test — minimal simulation

**Given** 10 agents and 10 rounds configured
**When** the simulation runs through the CAMEL-native loop
**Then** all 5 round phases execute in order for each round
**And** social media posts appear in the OASIS SQLite database
**And** memory blocks are populated (ChatHistory has messages, VectorDB has embeddings)
**And** no OOM crash occurs
**And** the simulation completes within a reasonable time

**Traces to:** R01, R02, R03, R04

### Verification: Phase 0

| Check | Method | Expected |
|-------|--------|----------|
| Agent class hierarchy | `isinstance(agent, ChatAgent)` returns True | MiroClawAgent extends ChatAgent, not SocialAgent |
| Tools registered | Inspect agent's tool list | FunctionTool instances for MiroClaw actions |
| Phase ordering | Log phase transitions per round | Research -> Contribute -> Vote -> Curate -> Oracle, strict order |
| Phase enforcement | Attempt Contribute-phase action during Research | Action rejected or unavailable |
| Memory blocks | Inspect agent memory after 5 rounds | ChatHistoryBlock, VectorDBBlock, CompactionBlock all non-empty |
| Compaction fires | Run 50+ rounds with active agent | CompactionBlock contains structured summary |
| OASIS posts | Query OASIS SQLite after simulation | Posts exist with correct agent attribution |
| No OOM | Monitor RSS during 10-agent 10-round sim | Memory stays below 4GB |

### Files to modify

| File | Change |
|------|--------|
| `backend/scripts/run_parallel_simulation.py` | Replace with CAMEL Workforce orchestration |
| `backend/app/services/simulation_runner.py` | Adapt subprocess management for new script |
| `backend/app/services/oasis_profile_generator.py` | Output MiroClawAgent configs instead of OASIS profiles |
| `backend/pyproject.toml` | Add CAMEL memory/workforce dependencies if not already in 0.2.78 |
| New: `backend/app/agents/miroclaw_agent.py` | MiroClawAgent(ChatAgent) base class |
| New: `backend/app/agents/memory.py` | MiroClawAgentMemory(LongtermAgentMemory) with CompactionBlock |
| New: `backend/app/agents/round_orchestrator.py` | Workforce-based phased round execution |

---

## Phase 1: Graph Write API

**Status:** Implemented
**Satisfies:** R05, R06

Add a write path to the Neo4j knowledge graph. Agents submit structured triples with provenance metadata during simulation. Triples pass through validation before entering the graph.

### Behaviour 1.1: Triple submission with provenance

**Given** an agent in the Contribute phase of round N
**When** it submits a structured triple:
```
(Subject Entity) —[RELATIONSHIP]-> (Object Entity)
  { source_url, added_by_agent, added_round, date }
```
**Then** the triple is written to Neo4j
**And** provenance metadata is stored on the edge/node:
  - `added_by_agent`: agent identifier
  - `added_round`: round number
  - `source_url`: URL the evidence was found at
  - `added_timestamp`: ISO timestamp
  - `upvotes`: 0 (initial)
  - `downvotes`: 0 (initial)
  - `status`: "pending" (initial)
**And** the triple is distinguishable from seed triples (which have no `added_by_agent`)

**Traces to:** R05

### Behaviour 1.2: Schema validation

**Given** a triple where the subject or object entity type does not exist in the ontology
**When** triple validation runs
**Then** the triple is rejected with a schema error
**And** the rejection reason is returned to the agent
**And** no data is written to Neo4j

**Traces to:** R06

### Behaviour 1.3: Deduplication via cosine similarity

**Given** an existing triple "A —[R]-> B" in the graph
**When** a new triple is submitted with >0.95 cosine similarity to the existing triple
**Then** the new triple is rejected as a duplicate
**And** the rejection includes the UUID of the existing triple it matched

**Traces to:** R06

### Behaviour 1.4: Source URL verification

**Given** a triple with a `source_url` field
**When** source validation runs
**Then** the URL must be reachable (HTTP 200 or redirect to 200)
**And** the triple's claim must be extractable from the page content (LLM verification)
**And** if either check fails, the triple is rejected with the specific failure reason

**Traces to:** R06

### Behaviour 1.5: Format enforcement

**Given** an agent attempts to add free text or an unstructured note to the graph
**When** format validation runs
**Then** the submission is rejected unless it conforms to the structured triple format
**And** the rejection message explains the required format

**Traces to:** R06

### Behaviour 1.6: Mixed query — seed and agent-added triples

**Given** a graph containing both seed triples (from initial build) and agent-added triples (from simulation)
**When** the graph is queried (by agents, report agent, or API)
**Then** both seed and agent-added triples are returned
**And** each result includes provenance metadata so the caller can distinguish origin
**And** existing `GraphSearchService` (InsightForge, Panorama, Quick) works with both types

**Traces to:** R05, R16

### Behaviour 1.7: Graph write as FunctionTool

**Given** a `MiroClawAgent` during simulation
**When** its tools are inspected
**Then** `add_triple` is registered as a CAMEL `FunctionTool`
**And** the tool is only invocable during the Contribute phase
**And** invoking it outside the Contribute phase returns a phase-restriction error

**Traces to:** R05, R01

### Verification: Phase 1

| Check | Method | Expected |
|-------|--------|----------|
| Triple persisted | Submit valid triple, query Neo4j | Triple exists with all provenance fields |
| Schema rejection | Submit triple with unknown entity type | Rejected, no data written |
| Dedup rejection | Submit near-duplicate (>0.95 similarity) | Rejected, existing UUID returned |
| Source rejection | Submit triple with unreachable URL | Rejected, specific failure reason |
| Format rejection | Submit free text instead of triple | Rejected, format guidance returned |
| Mixed query | Query graph with both seed and agent triples | Both returned, provenance distinguishes |
| Phase restriction | Invoke `add_triple` during Research phase | Tool unavailable or error returned |

### Files to modify

| File | Change |
|------|--------|
| `backend/app/services/local_graph/graph_service.py` | Add `write_triple()` method with validation pipeline |
| `backend/app/services/local_graph/episode_processor.py` | Extend entity upsert for agent-sourced triples with provenance |
| `backend/app/services/local_graph/embedding_service.py` | Support cosine similarity check for dedup |
| `backend/app/services/graph_search_tools.py` | Ensure search returns provenance metadata |
| New: `backend/app/agents/tools/graph_write.py` | `add_triple` FunctionTool with validation |
| New: `backend/app/api/graph.py` route | `POST /api/graph/triple` REST endpoint |

---

## Phase 2: Voting and Curation

**Status:** Implemented
**Satisfies:** R08, R09

Add a voting system for agents to upvote/downvote triples, and a curator agent that maintains graph quality by merging duplicates, pruning low-value triples, and flagging contested ones.

### Behaviour 2.1: Vote cast

**Given** an agent in the Vote phase
**And** a triple was added this round by a different agent
**When** the agent casts an upvote or downvote on the triple
**Then** the vote is stored as a property on the triple's edge/node:
  - `upvotes` incremented (for upvote) or `downvotes` incremented (for downvote)
  - Vote record stored: `{ agent_id, round, direction }`
**And** votes may be weighted by the agent's `influence_weight` from simulation config

**Traces to:** R08

### Behaviour 2.2: No double-voting

**Given** an agent has already voted on a specific triple this round
**When** it attempts to vote on the same triple again this round
**Then** the vote is rejected
**And** the agent is informed it has already voted on this triple

**Traces to:** R08

### Behaviour 2.3: Contested status auto-assignment

**Given** a triple where `upvotes > threshold` AND `downvotes > threshold`
**When** vote status is evaluated (end of each Vote phase)
**Then** the triple's `status` is set to "contested"
**And** contested triples represent genuine factual disputes between agents

**Traces to:** R08

### Behaviour 2.4: Curator — merge near-duplicates

**Given** two triples with cosine similarity above the merge threshold
**When** the curator agent runs during the Curate phase
**Then** the triples are merged into one
**And** vote counts are combined
**And** provenance from both originals is preserved
**And** the merge action is logged with reasoning

**Traces to:** R09

### Behaviour 2.5: Curator — prune low-value triples

**Given** a triple below the vote threshold after N rounds of low engagement
**When** the curator agent runs
**Then** the triple is soft-deleted to a `pruned_triples` collection
**And** the pruned triple remains queryable for post-simulation analysis
**And** the prune action is logged with reasoning

**Traces to:** R09

### Behaviour 2.6: Curator — contested triples are protected

**Given** a triple with `status: contested`
**And** the triple has a negative net vote score
**When** the curator evaluates it for pruning
**Then** the contested triple is NOT pruned, regardless of net vote score
**And** contested triples are the most analytically valuable output

**Traces to:** R09

### Behaviour 2.7: Curator — enforce graph size ceiling

**Given** total agent-added triples exceed the configured ceiling
**When** the curator runs
**Then** the lowest-voted non-contested triples are pruned first
**And** pruning continues until the triple count is at or below the ceiling
**And** contested triples are never pruned even when the ceiling is exceeded

**Traces to:** R09

### Behaviour 2.8: Curator — factual neutrality

**Given** any triple in the graph
**When** the curator evaluates it
**Then** the curator NEVER evaluates factual accuracy
**And** the curator only evaluates engagement (votes) and redundancy (similarity)
**And** the curator is adversarial to bloat, not to any position

**Traces to:** R09

### Behaviour 2.9: Curator audit trail

**Given** any curator action (merge, prune, flag, ceiling enforcement)
**When** the action executes
**Then** the action is logged with:
  - Action type
  - Target triple(s)
  - Reasoning
  - Round number
  - Timestamp

**Traces to:** R09

### Verification: Phase 2

| Check | Method | Expected |
|-------|--------|----------|
| Vote persisted | Cast vote, query triple properties | upvotes/downvotes incremented |
| Double-vote blocked | Vote twice on same triple same round | Second vote rejected |
| Contested assigned | Create triple with high upvotes AND downvotes | status = "contested" |
| Merge works | Add two near-duplicate triples, run curator | One merged triple with combined votes |
| Prune works | Add low-vote triple, wait N rounds, run curator | Triple in pruned_triples collection |
| Contested protected | Contested triple with negative net score | NOT pruned |
| Ceiling enforced | Exceed ceiling, run curator | Total triples at or below ceiling |
| Audit trail | Run curator with various actions | All actions logged with reasoning |

### Files to modify

| File | Change |
|------|--------|
| `backend/app/services/local_graph/graph_service.py` | Add vote storage, contested status evaluation, pruned_triples collection |
| New: `backend/app/agents/tools/voting.py` | `upvote_triple`, `downvote_triple` FunctionTools |
| New: `backend/app/agents/curator_agent.py` | Curator agent with merge/prune/flag/ceiling tools |
| New: `backend/app/agents/tools/curator_tools.py` | Curator-specific FunctionTools |

---

## Phase 3: Browser Integration

**Status:** Implemented — CamofoxBrowserClient wired to ResearchTool with session isolation, budget enforcement, and graceful fallback
**Satisfies:** R07, R10
**Files:** `backend/app/agents/tools/camofox_client.py`, `backend/app/agents/tools/research.py`, `backend/app/config.py`

Agents access the open web during the Research phase via camofox-browser's REST API (headless browser with anti-detection). Each agent gets an isolated browser session. Research budgets are enforced as hard limits. When camofox-browser is not running, research tools return empty results gracefully.

### Behaviour 3.1: Per-agent browser profile

**Given** a new MiroClawAgent is initialised for simulation
**When** browser access is configured
**Then** a camofox-browser tab is created for the agent via REST API (POST `/tabs`)
**And** the tab is isolated via `userId = miroclaw_{agent_id}` — no cross-agent cookie/session leakage
**And** the browser runs on loopback only (localhost:9377, no public network exposure)

**Traces to:** R10

### Behaviour 3.2: Web search

**Given** an agent in the Research phase
**When** it invokes the `search` tool with a query string
**Then** a web search is performed via the agent's browser profile
**And** search results (titles, URLs, snippets) are returned to the agent
**And** the search counts against the agent's per-round search budget

**Traces to:** R10, R07

### Behaviour 3.3: Page read and extraction

**Given** an agent with a URL from search results
**When** it invokes the `extract` tool on the URL
**Then** the page content is extracted via camofox accessibility tree snapshot
**And** the extracted text (capped at 10K chars) is returned to the agent
**And** the read counts against the agent's per-round page read budget

**Traces to:** R10, R07

### Behaviour 3.4: Search budget enforcement (hard limit)

**Given** an agent that has used 3 searches this round
**When** it attempts a 4th search
**Then** the tool returns a budget-exhausted error
**And** the agent cannot circumvent the limit (hard enforcement, not advisory)

**Traces to:** R07

### Behaviour 3.5: Page read budget enforcement (hard limit)

**Given** an agent that has read 3 pages this round
**When** it attempts a 4th page read
**Then** the tool returns a budget-exhausted error

**Traces to:** R07

### Behaviour 3.6: Graph addition budget enforcement

**Given** an agent that has already added 1 triple this round
**When** it attempts to add a 2nd triple
**Then** the tool returns a budget-exhausted error
**And** the agent must distill ruthlessly — 1 addition from potentially 3 searches and 3 reads

**Traces to:** R07

### Behaviour 3.7: Research findings flow into memory

**Given** an agent has performed web searches and page reads during Research phase
**When** the Research phase ends
**Then** research findings are stored in both:
  - `ChatHistoryBlock` — full detail for recent rounds
  - `VectorDBBlock` — embedded for semantic retrieval in future rounds
**And** the agent can recall relevant research from prior rounds via semantic search

**Traces to:** R07, R03

### Behaviour 3.8: Research-to-triple flow

**Given** an agent has completed research during the Research phase
**When** the Contribute phase begins
**Then** the agent selects its single most important finding
**And** expresses it as a structured triple with source URL provenance
**And** submits it via the `add_triple` tool

**Traces to:** R07, R05

### Behaviour 3.9: Session isolation between agents

**Given** two agents with separate browser profiles
**When** both perform web research simultaneously
**Then** cookies, sessions, and browsing history do not leak between profiles
**And** each agent's browser state is independent

**Traces to:** R10

### Verification: Phase 3

| Check | Method | Expected |
|-------|--------|----------|
| Browser session created | Check camofox after agent research | Per-agent tab exists |
| Search returns results | Invoke search tool | Results with titles, URLs, snippets |
| Extract returns content | Invoke extract on a known URL | Page text extracted |
| Search budget hit | Perform 4 searches | 4th returns budget-exhausted |
| Read budget hit | Read 4 pages | 4th returns budget-exhausted |
| Addition budget hit | Add 2 triples | 2nd returns budget-exhausted |
| Memory populated | Check VectorDB after research | Research embeddings stored |
| Session isolation | Two agents browse same site | Independent userId sessions |
| Graceful fallback | Research with camofox not running | Empty results, no crash |

### Files to modify

| File | Change |
|------|--------|
| New: `backend/app/agents/tools/research.py` | `search`, `navigate`, `extract` FunctionTools wrapping OpenClaw CDP |
| New: `backend/app/agents/tools/budget.py` | Per-agent per-round budget tracker (shared across all tools) |
| `backend/app/agents/round_orchestrator.py` | Wire Research phase to browser tools with budget reset per round |
| `backend/app/agents/memory.py` | Store research findings in VectorDBBlock |

---

## Phase 4: Cross-Session Evolution

**Status:** Implemented
**Satisfies:** R13

Enable agents to carry memory and evolved positions across simulation runs. An agent in Simulation 2 can recall evidence it discovered in Simulation 1.

### Behaviour 4.1: VectorDB persistence to disk

**Given** a completed simulation
**When** the simulation finalises
**Then** each agent's `VectorDBBlock` embeddings are persisted to disk (Qdrant or FAISS backend)
**And** the storage location is deterministic from the agent's identity (reproducible path)

**Traces to:** R13

### Behaviour 4.2: CompactionBlock serialisation

**Given** a completed simulation
**When** the simulation finalises
**Then** each agent's `CompactionBlock` structured summaries are serialised to JSON
**And** the JSON includes: positions held, evidence cited, graph contributions, debate threads, round ranges covered

**Traces to:** R13

### Behaviour 4.3: Memory reload for returning agents

**Given** an agent that participated in a prior simulation
**When** a new simulation initialises and the agent is included
**Then** its `VectorDBBlock` is loaded from persisted embeddings
**And** its `CompactionBlock` is loaded from serialised JSON
**And** the agent's `ChatHistoryBlock` starts empty (fresh for this session)

**Traces to:** R13

### Behaviour 4.4: Cross-session semantic recall

**Given** a returning agent encounters a topic it researched in a prior simulation
**When** the `VectorDBBlock` is queried for semantic similarity
**Then** relevant messages from the prior simulation are retrieved
**And** the agent can reference prior evidence in its current reasoning

**Traces to:** R13

### Behaviour 4.5: Cumulative identity changelog

**Given** a returning agent with position shifts across sessions
**When** its identity document is loaded
**Then** it includes a cumulative changelog:
  - Session 1: positions taken, shifts, triggering evidence
  - Session 2: positions taken, shifts, triggering evidence
  - etc.
**And** the changelog is included in the system prompt (persona section)

**Traces to:** R13, R12

### Behaviour 4.6: Fresh reset for control experiments

**Given** a returning agent marked for fresh reset
**When** the simulation initialises
**Then** the agent starts with empty memory — no VectorDB, no CompactionBlock, no changelog
**And** only its base persona (from graph entity) is preserved
**And** this enables controlled comparison: experienced agent vs naive agent

**Traces to:** R13

### Verification: Phase 4

| Check | Method | Expected |
|-------|--------|----------|
| VectorDB persisted | Check disk after sim 1 completes | Embedding files exist at expected path |
| Compaction serialised | Check disk after sim 1 | JSON file with structured summary |
| Memory reloaded | Start sim 2, inspect agent memory | VectorDB and CompactionBlock populated from sim 1 |
| Cross-session recall | Agent encounters sim 1 topic in sim 2 | Relevant sim 1 messages retrieved |
| Changelog cumulative | Inspect identity doc after sim 2 | Both sim 1 and sim 2 entries present |
| Fresh reset works | Mark agent for reset, start sim | Empty memory, base persona only |

### Files to modify

| File | Change |
|------|--------|
| `backend/app/agents/memory.py` | Add `save_to_disk()`, `load_from_disk()` methods |
| `backend/app/agents/miroclaw_agent.py` | Support `returning=True` flag to load prior memory |
| New: `backend/app/agents/identity.py` | Identity document with cumulative changelog |
| `backend/app/services/simulation_runner.py` | Save agent state on completion, load on restart |

---

## Phase 5: Oracle Agents and Forecasting

**Status:** Implemented (tool logic + epistemic flexibility, no model deployment)
**Satisfies:** R11, R12

Introduce specialist Oracle agents powered by a locally-hosted calibrated forecasting model. Regular agents can consult oracles during research. Epistemic flexibility governs how agents respond to contradicting evidence.

### Behaviour 5.1: Local forecasting model deployment

**Given** an OpenForecaster-8B GGUF file (or equivalent calibrated model)
**When** deployed via llama.cpp, Ollama, or LM Studio
**Then** it serves an OpenAI-compatible API on localhost
**And** the endpoint is configurable via environment variable (e.g., `ORACLE_MODEL_URL`)

**Traces to:** R11

### Behaviour 5.2: Oracle agent creation

**Given** the oracle model endpoint is configured
**When** `OracleAgent(MiroClawAgent)` instances are created (2-4 per simulation)
**Then** each oracle's CAMEL `ModelManager` points at the local forecasting endpoint
**And** oracles are distinct from regular agents — they do not post on social media
**And** oracles do not have a persona or stance; they are position-neutral

**Traces to:** R11

### Behaviour 5.3: Oracle consultation

**Given** an agent in the Research phase
**When** it invokes the `consult_oracle` tool with a question
**Then** the oracle receives: the question + relevant context from the knowledge graph
**And** the oracle returns a calibrated probability estimate with reasoning
**And** the consultation is implemented as a CAMEL `RolePlaying` call between the agent and oracle

**Traces to:** R11

### Behaviour 5.4: Oracle consultation budget

**Given** an agent that has already consulted an oracle this round
**When** it attempts another oracle consultation this round
**Then** the tool returns a budget-exhausted error (1 consultation per agent per round)

**Traces to:** R11, R07

### Behaviour 5.5: Periodic oracle forecasts

**Given** the simulation is at a round divisible by N (configurable)
**When** the Oracle Forecast phase runs
**Then** each oracle independently produces probability estimates on the simulation's core questions (derived from seed documents)
**And** forecasts are logged with: oracle_id, round, question, probability, reasoning
**And** forecasts are comparable across rounds to track confidence drift

**Traces to:** R11

### Behaviour 5.6: Oracle confidence drift tracking

**Given** oracle forecasts across multiple rounds
**When** forecasts on the same question are compared
**Then** confidence changes are trackable as a time series
**And** the direction of drift correlates with the accumulating evidence in the knowledge graph

**Traces to:** R11

### Behaviour 5.7: Epistemic flexibility — roll against evidence

**Given** an agent with `epistemic_flexibility = F` (0.0-1.0)
**And** its research this round found evidence contradicting its current position
**When** the epistemic flexibility check runs
**Then** with probability F, the agent's internal stance shifts one step (e.g., supportive -> neutral)
**And** with probability (1-F), the agent acknowledges the evidence internally but frames public posts to support its existing position

**Traces to:** R12

### Behaviour 5.8: Stance shift is gradual

**Given** a successful epistemic flexibility roll
**When** the agent's stance shifts
**Then** the shift is one step only (supportive -> neutral, NOT supportive -> opposing)
**And** the agent's identity changelog is updated: "Round N: shifted from X to Y after finding [triple]"
**And** future posts reflect the new position

**Traces to:** R12

### Behaviour 5.9: Epistemic flexibility distribution

**Given** a new simulation with agent profiles
**When** `epistemic_flexibility` values are assigned
**Then** the distribution across the agent population follows:
  - ~20% entrenched (0.0-0.2)
  - ~50% resistant but persuadable (0.3-0.5)
  - ~25% open (0.6-0.8)
  - ~5% hyper-flexible (0.9-1.0)
**And** values may be set by LLM based on entity type or as configurable parameters

**Traces to:** R12

### Behaviour 5.10: Oracle-powered report synthesis

**Given** a completed simulation with oracle forecasts and a contested knowledge graph
**When** the report is generated
**Then** it uses the oracle model (not just the general-purpose LLM)
**And** the report includes calibrated probability estimates for each prediction
**And** the report references agent-discovered evidence and contested triples

**Traces to:** R11, R16

### Verification: Phase 5

| Check | Method | Expected |
|-------|--------|----------|
| Model serves API | `curl localhost:8080/v1/models` | Model listed, responds to completions |
| Oracle created | Inspect OracleAgent instances | ModelManager points at oracle endpoint |
| Consultation works | Agent consults oracle | Probability estimate returned with reasoning |
| Consultation budget | Consult twice in one round | 2nd returns budget-exhausted |
| Periodic forecasts | Run N rounds, check logs | Forecasts logged every N rounds |
| Confidence drift | Compare forecasts across rounds | Values change as evidence accumulates |
| Flexibility roll | Agent with F=0.8 encounters contradiction | ~80% chance of stance shift |
| Gradual shift | Trigger stance shift | One step only, changelog updated |
| Oracle report | Generate report | Contains calibrated probabilities |

### Files to modify

| File | Change |
|------|--------|
| New: `backend/app/agents/oracle_agent.py` | `OracleAgent(MiroClawAgent)` with forecasting model |
| New: `backend/app/agents/tools/oracle.py` | `consult_oracle` FunctionTool |
| `backend/app/agents/miroclaw_agent.py` | Add `epistemic_flexibility` field, stance shift logic |
| `backend/app/agents/identity.py` | Add stance changelog entries |
| `backend/app/services/report_agent.py` | Extend with oracle model for report synthesis |
| `backend/app/config.py` | Add `ORACLE_MODEL_URL`, `ORACLE_FORECAST_INTERVAL` |

---

## Phase 6: Post-Simulation Analytics

**Status:** Implemented
**Satisfies:** R14, R16

Build the artifact extraction layer — dispute maps, provenance reports, graph diff, position drift visualisation, oracle time series. Extend the existing report agent with MiroClaw-specific query tools.

### Behaviour 6.1: Dispute map extraction

**Given** a completed simulation with contested triples
**When** a dispute map is requested
**Then** it extracts all triples with `status: contested`
**And** for each contested triple, shows:
  - The claim (subject, relationship, object)
  - Which agent types upvoted vs downvoted
  - Source URLs from both sides
  - The round it was added and by whom
**And** the output is a structured report: "These are the specific factual claims where agents genuinely disagreed about reality"

**Traces to:** R14

### Behaviour 6.2: Graph diff — seed vs post-simulation

**Given** the seed knowledge graph (pre-simulation) and the post-simulation graph
**When** a graph diff is requested
**Then** it shows:
  - Nodes added by agents (with provenance)
  - Edges added by agents (with provenance)
  - Nodes/edges pruned by curator
  - Net growth statistics (attempted, survived, pruned, contested)

**Traces to:** R14

### Behaviour 6.3: Per-agent provenance trail

**Given** a specific agent
**When** its provenance trail is requested
**Then** it shows per-round:
  - What it searched (queries)
  - What it read (URLs)
  - What it added to the graph (triples)
  - How it voted (which triples, direction)
  - Oracle consultations (questions asked, answers received)
  - Stance shifts (from, to, triggering evidence)

**Traces to:** R14

### Behaviour 6.4: Vote distribution analysis

**Given** all votes cast during the simulation
**When** vote analysis is requested
**Then** it shows:
  - Most contested triples (highest combined upvotes + downvotes)
  - Vote patterns by agent type (do framework-aligned agents vote differently from alternative-explanation agents?)
  - Triples that flipped from pending to contested to accepted

**Traces to:** R14

### Behaviour 6.5: Position drift visualisation

**Given** agent stance history across rounds
**When** position drift visualisation is requested
**Then** it shows per-agent stance over time (round on x-axis, stance on y-axis)
**And** triggering evidence is annotated at shift points
**And** agents are grouped by initial stance and entity type
**And** the visualisation answers: "Did the simulation converge, diverge, or stay divided?"

**Traces to:** R14

### Behaviour 6.6: Oracle forecast time series

**Given** oracle forecasts logged across rounds
**When** the oracle time series is requested
**Then** it shows per-question probability over time
**And** knowledge graph growth is overlaid (new triples per round)
**And** the visualisation answers: "Did oracle confidence shift as evidence accumulated?"

**Traces to:** R14

### Behaviour 6.7: Report agent integration with MiroClaw tools

**Given** the existing ReACT report agent
**When** MiroClaw tools are registered
**Then** it can query:
  - Contested triples (via `query_disputed`)
  - Agent provenance trails (via `query_provenance`)
  - Oracle forecasts (via `query_oracle_forecasts`)
  - Position drift data (via `query_stance_history`)
**And** these tools are available alongside existing `GraphSearchService` and `SimulationDBTools`

**Traces to:** R14, R16

### Verification: Phase 6

| Check | Method | Expected |
|-------|--------|----------|
| Dispute map | Request after sim with contested triples | All contested triples with agent-type breakdown |
| Graph diff | Request after sim | Shows added/pruned/net with provenance |
| Provenance trail | Request for specific agent | Per-round search/read/add/vote/shift history |
| Vote analysis | Request after sim | Most contested triples, patterns by agent type |
| Position drift | Request after sim with stance shifts | Time series with annotated shift points |
| Oracle time series | Request after sim with oracle forecasts | Probability over rounds, correlated with graph growth |
| Report agent tools | Generate report using MiroClaw tools | Report references contested triples, oracle forecasts |

### Files to modify

| File | Change |
|------|--------|
| New: `backend/app/services/miroclaw_analytics.py` | Dispute map, graph diff, vote analysis, position drift, oracle time series |
| New: `backend/app/agents/tools/analytics.py` | FunctionTools wrapping analytics for report agent |
| `backend/app/services/report_agent.py` | Register MiroClaw analytics tools alongside existing tools |
| `backend/app/services/simulation_query_tools.py` | Extend with MiroClaw-specific queries (contested triples, provenance) |
| `backend/app/api/report.py` | Add endpoints for analytics artifacts |

---

## Phase 7: UI Refresh

**Status:** Implemented
**Satisfies:** R14 (visualisation), R15 (retain frontend), UX quality

Audit the existing Vue 3 frontend against the UI/UX Pro Max rulebase. Fix accessibility violations, introduce a design token system, add MiroClaw-specific analytics visualisations, and establish dark mode. The existing monochrome + orange-accent identity is preserved and strengthened — not replaced.

### Current State Assessment

**What works:**
- Monochrome + orange (#FF4500) identity is distinctive and fits a research/analytics tool
- Space Grotesk + JetBrains Mono pairing is appropriate for the technical aesthetic
- D3 force-directed graph in GraphPanel is functional and well-implemented
- Split-panel workbench layout in MainView is effective for the 5-step workflow
- Console-style upload panel on Home page is on-brand
- MiroClaw phase tracker in Step3Simulation is structurally present

**What needs fixing (priority order):**

| Priority | Issue | Impact |
|----------|-------|--------|
| CRITICAL | No ARIA labels, no focus management, no keyboard navigation | Accessibility fail |
| CRITICAL | No `prefers-reduced-motion` support | Accessibility fail, animation sickness risk |
| HIGH | No design tokens — colours scattered as raw hex across 15 files | Maintainability zero, dark mode impossible |
| HIGH | No dark mode — light-only dashboard | Extended-use fatigue, analytics products need dark mode |
| HIGH | Emoji used as icons (📄 in file list, ❖ in empty state, ◇◈◆ in history cards) | Inconsistent cross-platform rendering, not themeable |
| HIGH | No analytics charts — only D3 force graph exists | Phase 6 analytics (dispute maps, drift, oracle time series) have no visualisation surface |
| MEDIUM | Only one responsive breakpoint (1024px) | Breaks on phones and wide monitors |
| MEDIUM | No skeleton loading states — uses spinners and "waiting..." text | Perceived performance poor |
| MEDIUM | No toast/notification system | Feedback only in terminal-style log panel |
| LOW | Typography repeated in every component's scoped CSS | Maintenance burden, inconsistent fallbacks |

### Behaviour 7.1: Design token system

**Given** the MiroClaw frontend
**When** a developer opens any component
**Then** all colours, spacing, typography, shadows, and border-radius values come from CSS custom properties defined in `App.vue :root`
**And** a `theme-light.css` and `theme-dark.css` file provides the token values per mode
**And** toggling a `data-theme="dark"` attribute on `<html>` switches the entire palette

**Token categories (minimum):**

| Token | Example | Purpose |
|-------|---------|---------|
| `--color-bg-primary` | `#FFFFFF` / `#0A0A0A` | Main background |
| `--color-bg-surface` | `#FAFAFA` / `#141414` | Card/panel background |
| `--color-bg-elevated` | `#F5F5F5` / `#1A1A1A` | Input, hover, inset areas |
| `--color-text-primary` | `#000000` / `#F0F0F0` | Headings, main text |
| `--color-text-secondary` | `#666666` / `#999999` | Descriptions, labels |
| `--color-text-tertiary` | `#999999` / `#666666` | Timestamps, meta |
| `--color-accent` | `#FF4500` | Orange accent (both themes) |
| `--color-success` | `#1A936F` / `#34D399` | Completed, confirmed |
| `--color-warning` | `#F59E0B` | Pending, caution |
| `--color-error` | `#EF4444` | Failed, rejected |
| `--color-border` | `#EAEAEA` / `#2A2A2A` | Borders, dividers |
| `--font-sans` | `'Space Grotesk', system-ui, sans-serif` | Body text |
| `--font-mono` | `'JetBrains Mono', monospace` | Code, IDs, data |
| `--radius-sm` | `2px` | Badges, chips |
| `--radius-md` | `6px` | Buttons, inputs |
| `--radius-lg` | `10px` | Cards, panels |
| `--shadow-sm` | `0 2px 4px rgba(0,0,0,0.04)` | Subtle elevation |
| `--shadow-md` | `0 4px 16px rgba(0,0,0,0.08)` | Cards |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,0.12)` | Modals, overlays |

**Traces to:** R15

### Behaviour 7.2: Dark mode

**Given** a user viewing the MiroClaw dashboard
**When** the user toggles the theme switch in the header
**Then** the entire UI switches between light and dark themes
**And** the preference is persisted to `localStorage`
**And** the initial theme respects `prefers-color-scheme` media query
**And** all components use design tokens (no raw hex in component styles)
**And** contrast ratios meet WCAG AA in both themes (4.5:1 for text, 3:1 for large text/UI elements)

**Key dark mode rules:**
- Background: `#0A0A0A` (near-black, not pure black — reduces eye strain)
- Surface cards: `#141414` with `#2A2A2A` borders
- Text primary: `#F0F0F0` (not pure white — too harsh on OLED)
- Graph panel: dot grid pattern becomes `#1A1A1A` dots on `#0F0F0F` background
- Timeline axis line: `#2A2A2A`
- System log panel: already dark (`#000` background) — remains unchanged
- Orange accent (`#FF4500`) stays the same in both themes
- Graph node strokes: `#2A2A2A` instead of `#FFFFFF`

**Traces to:** R15

### Behaviour 7.3: Replace emoji with SVG icons

**Given** any MiroClaw component currently using emoji characters as visual elements
**When** the component renders
**Then** all icons are SVG (inline or from Lucide icon set)
**And** icons are sized via design tokens (`--icon-sm`, `--icon-md`, `--icon-lg`)
**And** icons inherit colour from parent via `currentColor`

**Specific replacements:**

| Current | Location | Replacement |
|---------|----------|-------------|
| `📄` emoji | Home.vue file list | Lucide `file-text` SVG |
| `↑` character | Home.vue upload icon | Lucide `upload` SVG |
| `×` text | Home.vue remove button | Lucide `x` SVG |
| `↓` character | Home.vue scroll button | Lucide `chevron-down` SVG |
| `→` text | Various buttons | Lucide `arrow-right` SVG |
| `↻` character | GraphPanel refresh | Lucide `refresh-cw` SVG |
| `⛶` character | GraphPanel maximize | Lucide `maximize-2` SVG |
| `❖` character | GraphPanel empty state | Lucide `hexagon` SVG |
| `◇ ◈ ◆` characters | HistoryDatabase status | Lucide `diamond` / `hexagon` / `gem` SVGs |
| `■` character | Home.vue status dot | CSS-styled `<span>` with border-radius |
| `_` blinking cursor | Home.vue slogan | CSS-styled pseudo-element |

**Traces to:** R15

### Behaviour 7.4: Accessibility fixes

**Given** the MiroClaw frontend
**When** a user navigates via keyboard or screen reader
**Then** all interactive elements have focus-visible outlines (2-4px, `--color-accent` colour)
**And** all buttons and links have visible text labels (or `aria-label` if icon-only)
**And** heading hierarchy follows h1 → h2 → h3 with no skipped levels
**And** all form inputs have associated `<label>` elements
**And** `<html lang="en">` is set
**And** `prefers-reduced-motion: reduce` disables all animations (pulse, spin, blink, ripple, breathe)
**And** ARIA roles are set on landmark elements (`role="main"`, `role="navigation"`, `role="banner"`)
**And** focus trap is active in detail panels and modals

**Specific fixes:**

| Component | Issue | Fix |
|-----------|-------|-----|
| GraphPanel | SVG nodes have no ARIA labels | Add `aria-label="Entity: {name}"` to circles, `role="img"` to SVG |
| Step3Simulation | Timeline cards have no heading hierarchy | Add `h3` for agent names, wrap feed in `<section aria-label="Activity Timeline">` |
| Home.vue | File upload zone has no keyboard trigger | Add `role="button"`, `tabindex="0"`, `@keydown.enter` handler |
| Home.vue | Upload `<input>` has no `<label>` | Add `<label for="file-upload">` |
| All buttons | No focus-visible styles | Add `:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }` |
| Detail panel | No escape-to-close | Add `@keydown.escape="closeDetailPanel"` |

**Traces to:** R15

### Behaviour 7.5: MiroClaw analytics visualisations

**Given** a completed simulation with Phase 6 analytics data available
**When** the user views the Report page (Step 4)
**Then** MiroClaw-specific charts are rendered:

**7.5a: Dispute Map**
- Interactive heatmap showing contested triples
- X-axis: triple subject, Y-axis: relationship type
- Cell colour: intensity of disagreement (upvotes vs downvotes ratio)
- Tooltip: triple detail, agent-type breakdown, source URLs from both sides
- Fallback: sortable table for screen readers

**7.5b: Position Drift Chart**
- Multi-line chart: one line per agent
- X-axis: simulation round, Y-axis: stance (supportive=1, neutral=0, opposing=-1)
- Annotated markers at stance shift points with triggering evidence
- Agent grouping: by initial stance and entity type
- Toggle: show/hide individual agents or groups

**7.5c: Oracle Forecast Time Series**
- Line chart with confidence band
- X-axis: simulation round, Y-axis: predicted probability
- One series per oracle question
- Overlay: knowledge graph growth (new triples per round) as bar chart on secondary Y-axis
- Legend: interactive — click to toggle series visibility

**7.5d: Graph Growth Metrics**
- Stacked area chart showing cumulative triples by status (pending, accepted, contested, pruned)
- X-axis: simulation round, Y-axis: count
- Tooltips show exact counts per status per round

**7.5e: Provenance Trail**
- Not a chart — an interactive list view for a selected agent
- Shows per-round timeline: searches, reads, graph additions, votes, oracle consultations, stance shifts
- Each entry expandable to show detail
- Filterable by action type

**Chart library:** Chart.js (lightweight, good Vue 3 integration via `vue-chartjs`, accessible by default)
**Rendering:** All charts use design tokens for colours. All charts provide a table fallback for screen readers.

**Traces to:** R14, R15

### Behaviour 7.6: Responsive breakpoints

**Given** the MiroClaw frontend
**When** viewed on different screen sizes
**Then** the layout adapts at these breakpoints:

| Breakpoint | Target | Layout Changes |
|------------|--------|----------------|
| `≥1440px` | Desktop wide | Two-column split (50/50 graph/workbench) |
| `1024px–1439px` | Desktop | Two-column split (40/60 graph/workbench) |
| `768px–1023px` | Tablet | Single column, graph becomes collapsible panel |
| `<768px` | Mobile | Single column, stacked layout, hero title scales to 2.5rem |

**Specific changes:**
- Home.vue: Hero section stacks vertically below 1024px (already present, but add 768px tier for console box)
- MainView.vue: Split panel becomes tabbed view below 768px
- Step3Simulation: Timeline cards become full-width below 768px (no left/right split)
- GraphPanel: Full-screen overlay mode on mobile with back button

**Traces to:** R15

### Behaviour 7.7: Loading and empty states

**Given** any component that fetches data asynchronously
**When** data is loading
**Then** a skeleton screen matching the expected layout is shown (not a spinner)
**And** skeleton uses subtle pulse animation (respects `prefers-reduced-motion`)

**When** data is empty
**Then** a clear empty state message is shown with:
- An SVG icon (not emoji)
- A short explanation
- A suggested action (button or link)

**Components needing empty states:**

| Component | Current | Target |
|-----------|---------|--------|
| GraphPanel (no graph) | "Waiting for ontology generation..." with ❖ | Skeleton → empty state with "Upload documents to generate a knowledge graph" |
| Step3Simulation (no actions) | "Waiting for agent actions..." with pulse ring | Skeleton timeline cards → "Start the simulation to see agent activity" |
| Step4Report (no report) | "Waiting for Report Agent..." with rings | Skeleton sections → "Run a simulation first, then generate a report" |
| Step5Interaction (no chat) | Unknown — needs empty state | "Ask a question about the simulation results" with suggested prompts |
| HistoryDatabase (no projects) | Implied by `no-projects` class | "No simulations yet. Upload documents to get started." |

**Traces to:** R15

### Behaviour 7.8: Toast notifications

**Given** any async action (start simulation, generate report, add triple)
**When** the action completes or fails
**Then** a toast notification appears at the top-right of the screen
**And** auto-dismisses after 4 seconds
**And** includes an icon (success: checkmark, error: X, info: info icon)
**And** uses `aria-live="polite"` for screen reader announcement
**And** does not steal focus

**Implementation:** Lightweight Vue composable `useToast()` — no library dependency. Single `<ToastContainer>` component mounted in `App.vue`.

**Traces to:** R15

### Behaviour 7.9: Simulation phase tracker enhancement

**Given** a running MiroClaw simulation
**When** the user views Step3Simulation
**Then** the MiroClaw phase tracker (currently a simple stepper with dots) is enhanced to show:

- **Phase progress bar** — continuous bar showing current phase position within the round
- **Round counter** — "Round X / Y" prominently displayed
- **Per-phase mini-metrics:**
  - Research: "X searches, Y reads" (from budget tracker)
  - Contribute: "X triples added"
  - Vote: "X votes cast, Y contested"
  - Curate: "X merged, Y pruned"
  - Oracle: "X forecasts, avg confidence Y%"
- **Triple feed** remains collapsible but adds:
  - Vote indicators (↑/↓ counts with colour coding)
  - Status badge (pending/accepted/contested/pruned)
  - Source URL as clickable link

**Traces to:** R14, R15

### Verification: Phase 7

| Check | Method | Expected |
|-------|--------|----------|
| Design tokens | Inspect `:root` CSS | All colours/spacing via custom properties |
| Dark mode toggle | Click theme switch | Entire UI switches, no raw hex artifacts |
| Dark mode persistence | Reload page | Theme persists from localStorage |
| Dark mode auto | Set OS to dark mode | MiroClaw loads in dark mode |
| Contrast ratios | Run axe-core audit | WCAG AA pass in both themes |
| No emoji icons | Search codebase for emoji chars | Zero emoji in template/style |
| Keyboard navigation | Tab through entire app | All interactive elements reachable, visible focus rings |
| Reduced motion | Enable `prefers-reduced-motion` | All animations disabled |
| ARIA audit | Run Lighthouse accessibility | Score ≥ 90 |
| Charts render | View report page after simulation | Dispute map, position drift, oracle time series, graph growth visible |
| Chart fallback | Disable JavaScript on charts | Data tables visible |
| Mobile layout | View at 375px width | Single column, no horizontal scroll, touch targets ≥44px |
| Skeleton loading | Trigger slow API response | Skeleton screens appear, no blank areas |
| Toast notifications | Start simulation | Toast appears: "Simulation started" |
| Phase tracker | View during simulation | Per-phase metrics update in real time |

### Files to modify

| File | Change |
|------|--------|
| New: `frontend/src/styles/tokens.css` | CSS custom properties for both themes |
| New: `frontend/src/styles/dark.css` | Dark theme token overrides |
| New: `frontend/src/composables/useTheme.js` | Theme toggle + localStorage + OS preference detection |
| New: `frontend/src/composables/useToast.js` | Toast notification composable |
| New: `frontend/src/components/ToastContainer.vue` | Toast rendering component |
| New: `frontend/src/components/charts/DisputeMap.vue` | Heatmap chart for contested triples |
| New: `frontend/src/components/charts/PositionDrift.vue` | Multi-line stance chart over rounds |
| New: `frontend/src/components/charts/OracleTimeSeries.vue` | Line chart with confidence bands |
| New: `frontend/src/components/charts/GraphGrowth.vue` | Stacked area chart for triple statuses |
| New: `frontend/src/components/charts/ProvenanceTrail.vue` | Agent provenance timeline list |
| New: `frontend/src/components/icons/` | Lucide SVG icon components |
| `frontend/src/App.vue` | Import tokens, dark.css, add ToastContainer, add `data-theme` attribute |
| `frontend/src/views/Home.vue` | Replace emoji, use tokens, add ARIA, add responsive tiers |
| `frontend/src/views/MainView.vue` | Use tokens, add theme toggle button in header, responsive tabs |
| `frontend/src/components/GraphPanel.vue` | Dark mode, ARIA on SVG, use tokens for all colours |
| `frontend/src/components/Step3Simulation.vue` | Enhanced phase tracker, replace emoji, use tokens, skeleton states |
| `frontend/src/components/Step4Report.vue` | Add analytics chart tabs, use tokens, skeleton states |
| `frontend/src/components/Step5Interaction.vue` | Empty state, use tokens |
| `frontend/src/components/HistoryDatabase.vue` | Replace ◇◈◆ with SVG icons, use tokens |
| `frontend/package.json` | Add `chart.js`, `vue-chartjs` dependencies |
| `frontend/index.html` | Ensure `<html lang="en">` |

---

## Appendix A: Architecture Decisions

### A.1 Browser Runtime — Camofox-Browser REST API

Camofox-browser (https://github.com/jo-inc/camofox-browser) provides a REST API for headless browser automation with anti-detection (Camoufox/Firefox fork). Per-agent session isolation via `userId`/`sessionKey`. Accessibility tree snapshots for content extraction. Search macros (`@wikipedia_search`, `@google_search`, etc.) for structured web search.

**Alternative considered:** Playwright via Python. Rejected because camofox-browser is purpose-built for AI agent use, has built-in anti-detection, accessibility tree extraction, search macros, and session isolation out of the box.

**Graceful degradation:** When camofox-browser is not running (default), ResearchTool returns empty results. No crash, no error — agents simply have no web research capability until camofox is started.

### A.2 Simulation Engine — CAMEL Workforce, not OASIS flat loop

OASIS is a thin wrapper around CAMEL's `ChatAgent` that adds social media action tools and a flat round-robin simulation loop. MiroClaw's phased rounds (Research -> Contribute -> Vote -> Curate -> Oracle) need richer coordination.

CAMEL's ecosystem provides the right primitives:

| CAMEL Module | MiroClaw Use |
|---|---|
| `societies/workforce/` | Phased rounds with task decomposition and worker assignment |
| `societies/role_playing.py` | Structured agent-agent dialogue for oracle consultation and deep debate |
| `agents/ChatAgent` | Base agent class — MiroClaw agents inherit directly, bypassing OASIS's SocialAgent |
| `toolkits/FunctionTool` | Agent action tools — research, graph write, vote |

OASIS is retained as one interaction surface (Twitter/Reddit databases, feed algorithms) but not as the simulation backbone.

### A.3 Agent Memory — Hybrid with Structured Compaction

`LongtermAgentMemory` solves retrieval (finding relevant past messages) but not narrative coherence. An agent in round 150 needs "I shifted from supportive to neutral at round 22 because of [evidence]" — that's a narrative arc, not a similarity match.

MiroClaw adds `CompactionBlock` alongside CAMEL's existing blocks. Why hybrid beats either alone:
1. Compaction alone preserves narrative arc but loses detail
2. Vector DB alone retrieves fragments but lacks narrative coherence
3. Both together give coherent self-narrative (compaction) plus on-demand evidence recall (vector DB)

**Cost model:** ~1 LLM call per agent per compaction event. At 70% threshold, fires roughly every 50 rounds. For 182 agents over 72 rounds, ~182 extra LLM calls — negligible vs ~26K for the simulation.

### A.4 CAMEL Ecosystem Strategy

| Project | MiroClaw Relationship |
|---|---|
| **CAMEL** (`camel-ai/camel`) | Foundation. Agents, memory, Workforce, RolePlaying |
| **OASIS** (`camel-ai/oasis`) | Interaction surface. Social platform databases retained as plugin |
| **OWL** (`camel-ai/owl`) | Pattern reference. MCP integration patterns for tool discovery |
| **CRAB** (`camel-ai/crab`) | Future evaluation. Graph-based benchmarking for measuring simulation quality |

### A.5 Oracle Model — OpenForecaster-8B

| Property | Detail |
|---|---|
| Base | Qwen3-8B, fine-tuned via GRPO (reinforcement learning) |
| Training objective | Joint reward: accuracy + Brier score calibration |
| Training data | OpenForesight — 52K+ forecasting questions |
| Performance | Outperforms 100B+ general-purpose models on FutureX benchmark |
| Licence | MIT |
| Size | 8B params — runnable on consumer hardware |

Critical property: **calibration**. OpenForecaster minimises Brier score, so its probability estimates are meaningful. General-purpose LLMs are not calibrated.

**Deployment:** llama.cpp / LM Studio on Mac (M-series with 32GB+ unified memory). ~5GB VRAM for Q4 quantisation. Oracle architecture is model-agnostic — any OpenAI-compatible endpoint works.

**Complementary frameworks:** BrierBench for evaluation (time-weighted Brier score). HoTPP for future time-to-event forecasting extension.

---

## Appendix B: Open Questions

All carried from the roadmap. Decision needed before or during the indicated phase.

| # | Question | Impact | Decision by |
|---|----------|--------|-------------|
| 1 | Should agents see each other's research queries? | Transparency vs strategic search. Affects simulation dynamics. | Phase 3 |
| 2 | How does the curator handle contradictory triples that are both well-sourced? | Core to contested-knowledge model. e.g., "zero fraud complaints" vs "3 compliance warnings" — both true, different scope. | Phase 2 |
| 3 | Should the research budget scale with simulation length? | 96 rounds x 80 agents = 7,680 triples. At 200 rounds = 16,000. Graph ceiling may need to be dynamic. | Phase 3 |
| 4 | How to handle paywalled or geo-restricted content? | Some evidence is unreachable. Accept limitation or need institutional access. | Phase 3 |
| 5 | Is the curator a fixed algorithm or an LLM agent? | Algorithm is deterministic and auditable. LLM is flexible but less predictable. Affects trust. | Phase 2 |
| 6 | How does epistemic flexibility interact with voting? | Should agents who shift re-vote on previously voted triples? Could flip contested status mid-simulation. | Phase 5 |
| 7 | CAMEL version pinning vs tracking HEAD? | OASIS pins older CAMEL. MiroClaw going CAMEL-native controls version directly. Pin to release, upgrade deliberately. | Phase 0 |

---

## Appendix C: Success Metrics

For the first MiroClaw simulation (target: Narcissist State framework test):

| Metric | Target | Why |
|---|---|---|
| Agent-added triples surviving curation | > 3,000 | Agents can find and distill real evidence |
| Contested triples | > 200 | Genuine factual disputes emerge |
| Triples with valid source URLs | > 90% | Evidence is real, not hallucinated |
| Agent types on both sides of contested | Framework-aligned AND alternative on each | Debate is two-sided |
| Post-sim graph used in report | Report cites agent-discovered evidence | Living graph feeds analysis |
| Oracle Brier score on resolvable questions | < 0.25 | Calibrated forecasting works |
| Oracle confidence drift correlates with evidence | Confidence moves with accumulating evidence | Oracles respond to growing graph |
| Oracle report vs general-purpose report | Blind evaluation prefers oracle report | Forecasting model produces better output |

---

## Appendix D: Epistemic Flexibility Model

### Distribution

| Range | Behaviour | Analogue | Population |
|---|---|---|---|
| 0.0-0.2 | Entrenched. Selective research, dismiss contradictions, double down. | True believers, institutional actors | ~20% |
| 0.3-0.5 | Resistant but persuadable. Needs strong repeated evidence. Slow drift. | Most people in most debates | ~50% |
| 0.6-0.8 | Open. Actively seeks disconfirming evidence. Visible evolution. | Journalists, researchers | ~25% |
| 0.9-1.0 | Hyper-flexible. Shifts easily. Canary: if these converge, evidence is strong. | Devil's advocates, undecided | ~5% |

### Mechanical Process

1. Agent's research in round N finds contradicting evidence
2. Roll against `epistemic_flexibility` — if roll < F, stance shifts
3. Shift is gradual: one step (supportive -> neutral, not supportive -> opposing)
4. Identity changelog updated with round, old stance, new stance, triggering evidence
5. If roll fails: agent acknowledges evidence internally, frames public posts to support existing position (realistic behaviour)

### Open design question

How does epistemic flexibility interact with voting? Should shifted agents re-vote on previously voted triples? This could cause contested triples to flip status mid-simulation — interesting dynamics but added complexity. (See Open Question #6.)
