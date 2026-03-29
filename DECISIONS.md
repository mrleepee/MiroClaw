# MiroClaw Implementation Decisions

## D1: Curator is algorithmic, not LLM-based
**Decision:** The curator agent uses deterministic algorithms (cosine similarity, vote thresholds) rather than LLM calls.
**Why:** Spec Open Question #5. Algorithmic is deterministic, auditable, and cheaper. LLM is flexible but unpredictable. Trust matters more than flexibility for curation.
**How:** Curator uses fixed thresholds for merge, prune, and flag operations. No LLM calls in the curation path.

## D2: FAISS for local dev, Qdrant for production
**Decision:** Use FAISS as the default VectorDB backend for local development.
**Why:** FAISS requires no server, is fast locally, and matches the single-user local deployment scope. Can upgrade to Qdrant later.
**How:** VectorDBBlock uses FAISS via CAMEL's abstraction. Storage path is deterministic from agent identity.

## D3: Phase enforcement via tool registration
**Decision:** Tools are conditionally registered based on the current phase, not globally available with runtime checks.
**Why:** Cleaner separation - agents literally cannot invoke tools outside their phase. Simpler than checking phase in every tool call.
**How:** Round orchestrator swaps tool sets between phases. Tools are added/removed from agent's tool list at phase boundaries.

## D4: Epistemic flexibility distribution via LLM
**Decision:** The profile generator assigns epistemic_flexibility values based on entity type analysis by the LLM.
**Why:** The LLM already understands entity context from the graph. A simple random distribution wouldn't respect entity types (e.g., institutional actors should be more entrenched).
**How:** Added to the profile generation prompt; falls back to the statistical distribution if LLM doesn't provide a value.
