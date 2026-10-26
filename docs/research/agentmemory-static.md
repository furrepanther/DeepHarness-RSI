# AgentMemory static research report

## Identity and provenance

- Repository: `https://github.com/rohitg00/agentmemory.git`; local path:
  `/linuxdata/Github/agentmemory`.
- Inspected commit: `1c995081c45dd465877c4f6ecbf313490baa8820`.
- License: Apache-2.0 (`LICENSE`).
- Checkout: Git objects and HEAD are present, but SSHFS-backed working-tree
  checkout is incomplete with `Operation not permitted`; evidence below uses
  committed files through `git show`/`git grep`. No repository file was edited.
- Method: bounded static inspection. No dependencies, builds, tests, services,
  external provider calls, or cloud inference were run.

## Architecture and memory model

- AgentMemory is a local daemon built on the iii engine. The documented REST/MCP
  service uses port 3111, streams 3112, viewer 3113, and engine WebSocket 49134.
  Hooks and MCP adapters allow many agent clients to share one daemon.
- The core starts provider, embedding, hybrid-search, persistence, privacy,
  graph, session, hook, MCP, viewer, and maintenance functions from `src/index.ts`.
- Keyless operation is BM25-oriented. Optional local embeddings use
  `Xenova/all-MiniLM-L6-v2`; vector, graph, temporal, and session indexes add
  retrieval layers. Index persistence shards data, tracks generations, pending
  changes, vector dimensions, and replay markers.
- The design is an auxiliary memory service, not an authoritative canonical
  policy store. Its persisted KV/index legs do not provide Primus's SQLite /
  Chroma / Mem0 publication generation or signed Memory Fabric provenance.

## Lifecycle, tools, and local-router fit

- Hooks capture prompt, tool, session, subagent, failure, compaction, and task
  events. Event IDs, capture filtering, truncation, drain children, and write
  scrubbing are useful operational patterns.
- The MCP bridge explicitly says retrieved memories are evidence rather than
  instructions and defaults to loopback. Non-loopback authenticated URLs need
  HTTPS, but this is not Primus scope or gateway authorization.
- Provider code supports OpenAI, Anthropic, Gemini, OpenRouter, Minimax, and
  Agent SDK paths plus fallback chains. It has no enforced Primus local-router
  boundary, no `11888` policy, and no explicit cloud-handoff contract.
- Primus could reuse the daemon only behind a fail-closed Memory Fabric adapter:
  local gateway/MCP access, caller scope, generation pinning, byte/line caps,
  provenance-bearing writes, and no direct provider or fallback execution.

## Reliability, security, and performance findings

- Reusable strengths: deterministic event IDs, secret/private-tag scrubbing,
  bounded capture previews, BM25 plus vector/graph layering, local embeddings,
  pending index replay, vector dimension validation, and session/index
  maintenance hooks.
- Risk: provider fallback and optional LLM compression can send memory material
  to external providers unless Primus disables those paths or routes them only
  through the local router.
- Risk: `src/mcp/rest-proxy.ts` can fall back to an in-memory KV handle when the
  daemon probe fails. That is a convenience fallback, not acceptable as silent
  authoritative-memory degradation for Primus.
- Risk: hooks and capture are broad trust boundaries. Prompt/tool/reasoning
  content must remain outside diagnostics, and capture must be scoped to the
  task evidence policy before any reuse.
- Performance tradeoff: hybrid search and graph enrichment can improve recall,
  but in-process scans and index checkpoint work need bounded admission and
  generation-aware cache accounting in Primus.

## Reusable and rejected patterns

- Adapt: multi-client hook/MCP wiring, event-id deduplication, privacy scrubbing
  at write boundaries, local BM25/vector/graph retrieval as non-authoritative
  evidence, pending-log replay, dimension/index health checks, and local
  embedding seams.
- Reject unchanged: external provider selection, fallback chains, silent
  in-memory memory fallback, model-directed authority, broad prompt capture,
  and any daemon state treated as the Memory Fabric source of truth.

## Exact evidence paths and uncertainties

- `README.md`, `LICENSE`, `INSTALL_FOR_AGENTS.md`, `src/index.ts`.
- `src/state/index-persistence.ts`, `src/state/vector-index.ts`,
  `src/state/search-index.ts`, `src/state/graph-generation.ts`.
- `src/mcp/plugin-bridge.ts`, `src/mcp/rest-proxy.ts`, `src/mcp/server.ts`.
- `src/hooks/_capture.ts`, `src/hooks/_capture-filter.ts`,
  `src/functions/privacy.ts`, `src/providers/index.ts`.
- Runtime behavior, dependency freshness, index recovery under crash, and
  actual local-router integration were not exercised. The incomplete SSHFS
  checkout prevents a clean working-tree build claim.

Recommendation: adapt selected memory/index/privacy patterns only. Do not make
AgentMemory the Primus harness, Memory Fabric authority, or inference router.
