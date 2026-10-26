# Ruflo harness research

## Identity and provenance

- Repository: `https://github.com/ruvnet/ruflo.git`; local path: `/linuxdata/Github/ruflo`.
- Inspected commit: `0396c4c20457340e006b50f023598874c6e7a5f8` (shallow, blob-filtered clone).
- License: MIT, copyright 2024-2026 ruvnet (`LICENSE`). Dependency licenses were not audited.
- The checkout fetched Git objects but did not complete checkout: several files under `plugins/ruflo-chatgpt-federation` and `plugins/ruflo-console` failed with `Operation not permitted`. No repository files were edited; evidence was read from Git objects with `git show`/`git grep`. Git status reported no tracked modifications.
- No dependencies, builds, tests, services, or inference were run. Claims marked as benchmarked are documentation claims, not independently verified here.

## Architecture

Ruflo is a large, plugin-oriented meta-harness with two overlapping surfaces:

- Root packaging identifies it as `claude-flow` 3.59.10 and exposes CLI, MCP, Claude Code plugin, Codex integration, and many optional plugins (`package.json`, `README.md`). The conceptual flow is CLI/MCP -> router -> swarm -> agents -> memory -> model providers.
- The V3 design is a TypeScript modular monorepo with security, memory, swarm, MCP, routing, federation, and shared-config packages (`v3/README.md`, `v3/@claude-flow/`). The CLI package is the most production-shaped path; `v3/src/` also contains a smaller domain/application design that is partly skeletal.
- The plugin catalog separates concerns into core, swarm, autopilot, AgentDB/RAG/RuVector/RVF, intelligence, federation, security, browser, and workflow plugins. Plugin readmes use smoke scripts as offline surface contracts; this is useful packaging discipline, but a passing smoke contract does not prove runtime behavior.
- The swarm plugin documents hierarchical, mesh, ring, star, and adaptive topologies, worktree isolation, Monitor streams, and consensus options (`plugins/ruflo-swarm/README.md`). Core MCP registration is broad: memory, AgentDB, embeddings, hooks, security, autopilot, browser, agent, swarm, workflow, and terminal families (`plugins/ruflo-core/README.md`).

## State, memory, and database model

- The mature CLI memory bridge is centered on AgentDB plus SQLite, with hybrid lexical/vector/graph retrieval, local 384-dimension embeddings, tiered caching, reasoning/causal controllers, mutation guards, attestation, and optional COW branches (`v3/@claude-flow/cli/src/memory/memory-bridge.ts`). It uses canonical per-database registry identity and async operation leases so shutdown does not close a database while awaited work is active.
- Persistent defaults are workspace-oriented: `.swarm/memory.db`, `.claude-flow/sessions`, and `.swarm/model-router-state.json`; when the main database is encrypted, the bridge may use a separate plaintext sibling `agentdb-memory.db` for AgentDB compatibility. `memory-initializer.ts` defines WAL mode, foreign keys, `memory_entries`, provenance, TTL/status, and pattern-history tables. `shared-sqlite.ts` deliberately reuses one `better-sqlite3` identity per process to avoid WAL sidecar corruption.
- `graph-edge-writer.ts` records a real operational trap: a sql.js whole-file write can corrupt a WAL-active database. The implementation uses the shared native SQLite driver, refuses encrypted/missing databases, and has bounded header probing. Its public graph-write helpers suppress errors internally, which is convenient for optional enrichment but dangerous for correctness unless callers have separate health/metrics.
- RVF is the portable session/memory container. `plugins/ruflo-rvf/README.md` documents AES-256-GCM at-rest session/database gates with legacy plaintext sniffing, but exported RVF bytes are not automatically encrypted for transport.
- The domain backends in `v3/src/memory/infrastructure/SQLiteBackend.ts` and `AgentDBBackend.ts` are not equivalent to the CLI bridge: both use in-memory `Map` storage; the AgentDB backend scans embeddings rather than using HNSW; the SQLite backend's vector search is empty. Treat those files as design scaffolding, not a production persistence guarantee.
- Namespaces are an explicit integration contract (`plugins/ruflo-agentdb/README.md`): `swarm-state`, `autopilot-patterns`, `rvf-sessions`, `federation`, `patterns`, `tasks`, and others. The documented warning that some AgentDB tool families ignore `namespace` is important: namespace isolation is not automatically universal.

## Agent, tool, and subagent lifecycle

- `v3/src/task-execution/domain/Task.ts` models pending/in-progress/completed/failed/cancelled states, dependency checks, priority ordering, topological sorting, circular-dependency rejection, and rollback hooks.
- `v3/src/task-execution/application/WorkflowEngine.ts` persists task-start/task-complete events and workflow snapshots, supports pause/cancel, dependency order, and reverse-order rollback. Its parallel/distributed paths use `Promise.all` without a shared concurrency bound; this is unsafe as a default for a high-volume harness.
- `v3/src/coordination/application/SwarmCoordinator.ts` assigns by priority and least load, tracks metrics, returns structured failures, and supports topology/scale operations. Its concurrent execution is also `Promise.all`; its consensus method is explicitly simulated with random approvals, not a usable consensus implementation.
- The reusable CLI service `v3/@claude-flow/cli/src/services/bounded-worker-pool.ts` is substantially better: fixed worker count, unique task IDs, deterministic result order, peak-concurrency reporting, cooperative abort, and caller-visible timeout even when a task ignores its signal. This is the strongest concurrency pattern to adapt.
- MCP `v3/@claude-flow/mcp/src/task-manager.ts` provides a sound lifecycle: bounded slots, pending/running/terminal states, per-task AbortController, timeout, progress events, terminal-state ownership during late cancellation, event-driven wait, retention cleanup, and orderly destroy. It is process-local and therefore needs a durable task ledger for crash recovery.
- `worker-queue.ts` specifies priority, retry/backoff, timeout, heartbeat, visibility timeout, result TTL, and dead-letter behavior, but the checked-in implementation uses `InMemoryStore`; its Redis URL is configuration, not proof of a distributed queue. `getStats` is explicitly simplified. Use the state machine, not the implementation, as the reusable idea.
- `headless-worker-executor.ts` adds useful production controls: process-pool limits, sandbox modes, budget denial before execution, repository-head/worker-type deduplication, timeouts, structured errors, and subprocess cleanup. It is tightly coupled to Claude Code and must not be copied as the model boundary.
- `tool-registry.ts` gives O(1) tool lookup, schema validation, optional authorization, structured MCP errors, and execution metrics. `session-manager.ts` and MCP server start/stop code add bounded sessions, cleanup, transport rollback on partial startup, and orderly shutdown.

## Local model and routing fit

Fit is mixed and requires an adapter.

- `v3/@claude-flow/cli/src/ruvector/model-router.ts` has a useful local decision layer: lexical task-complexity bucketing, Thompson-style priors, circuit-breaker/uncertainty handling, persisted router state, and optional neural routing. It is mostly local arithmetic and can be retained as policy metadata.
- `v3/@claude-flow/cli/src/mcp-tools/agent-execute-core.ts` directly calls Anthropic, OpenRouter, or Ollama-compatible endpoints. This violates a local-only Primus deployment if used unchanged: it chooses providers and performs network requests itself instead of routing through the Primus local inference router.
- `plugins/ruflo-ruvllm/README.md` describes local WASM/ONNX-oriented adaptation, SONA/MicroLoRA, and a small HNSW pattern router. It is a useful local-learning component, but optional dependencies and the small pattern cap make it unsuitable as the sole execution router.
- `plugins/ruflo-mods/hooks/route/route-task.ts` is a deterministic keyword router. It is cheap and inspectable, but first-match semantics and a coder default create false-positive and misrouting risk.
- Adaptation rule for Primus: preserve Ruflo's model-tier/circuit-breaker/evaluation ideas behind a provider interface whose only execution target is `http://127.0.0.1:11888`; fail fast when that router is unavailable and honor its explicit cloud-handoff signal rather than bypassing it. No Ruflo cloud endpoint was called during this research.

## Reliability, security, and performance findings

Strengths worth carrying forward:

- Bounded worker execution and MCP task terminal-state ownership prevent the most common fan-out and cancellation races.
- Checkpoint/rollback support (`v3/@claude-flow/cli/src/services/checkpoint-gate.ts`) and session/RVF persistence provide useful recovery shapes. The checkpoint gate must be changed to fail closed: its documented degraded paths can run unguarded when the optional guard, kill switch, or memory path is unavailable.
- Memory path canonicalization and traversal checks, SQLite WAL guards, data-version cache invalidation, schema migration, provenance, and append-only/conditional-write controls are strong local durability patterns.
- MCP transport has bearer authentication, timing-safe token comparison, JSON/request-size limits, request timeout handling, CORS restrictions, rate limiting, session validation, and structured errors (`v3/@claude-flow/mcp/src/transport/http.ts`, `rate-limiter.ts`, `server.ts`).
- Security policy has observe/enforce modes, approval/budget checks, signed/chained receipts, anchoring requirements, and fail-closed metering behavior (`v3/@claude-flow/security/src/policy/engine.ts`). Federation adds trust levels, HMAC envelopes, PII gates, hop/token/USD budgets, breaker states, and audit records (`v3/@claude-flow/plugin-agent-federation/`, `plugins/ruflo-federation/README.md`).

Risks and traps:

- Several similarly named layers disagree in maturity: in-memory domain backends, in-memory MCP task state, simulated consensus, and a nominal Redis queue can create false durability/recovery confidence.
- Unbounded `Promise.all` in workflow/swarm application code can exhaust model, file, or process capacity even though a bounded worker service exists elsewhere.
- Optional native/WASM/database packages create installation-dependent behavior. Plugin compatibility is pinned around `@claude-flow/cli` v3.6 while the root package reports 3.59.10; verify the actual resolved entrypoint before adopting contracts.
- Root README warns that mods run with account permissions and are not sandboxed. The swarm mod can call `process.run`; federation/WireGuard integration can emit shell-ready commands. Keep these behind explicit capability, validation, and operator approval gates.
- Direct provider calls, static keyword routing, fail-open checkpoint degradation, suppressed graph-write errors, and unbounded remote delegation are unacceptable defaults for a local reliability harness.
- HNSW speed/recall figures in the RAG plugin are useful capacity hints, but they are repository claims and were not reproduced. Benchmark the actual local model, embedding runtime, database size, and recovery path.

## Reusable patterns

1. Adapt `bounded-worker-pool.ts` as the single execution primitive; require explicit concurrency, timeout, abort, deterministic result ordering, and peak-utilization evidence.
2. Adapt MCP `task-manager.ts` terminal ownership and progress semantics, backed by a durable task ledger with lease/heartbeat/recovery fields.
3. Use one authoritative SQLite driver/path per process, WAL-aware writes, schema/provenance/version checks, and fail-closed corruption/encryption gates.
4. Keep namespaces and capability scopes explicit; validate tool schemas before authorization and record structured receipts for state-changing operations.
5. Use hop and spend budgets, circuit breakers, deduplication, retry caps, and a dead-letter state for recursive or remote work.
6. Treat routing experiments as shadow/evaluation data with bounded, rotated logs and explicit redaction; promote a new route only after quality/cost/latency gates.

## Rejected patterns

- Do not adopt direct Anthropic/OpenRouter/Ollama calls or provider selection inside agents.
- Do not treat `v3/src` in-memory backends, simulated consensus, or the current `InMemoryStore` as production implementations.
- Do not use unbounded `Promise.all` for swarm/workflow fan-out.
- Do not fail open when checkpointing, persistence, authorization, or the local inference router is unavailable.
- Do not assume an AgentDB namespace filters every tool family; enforce scope at the storage and authorization layers.
- Do not enable account-permission mods or shell-ready federation commands without capability isolation, command validation, and audit.

## Exact evidence paths

- Identity/package: `README.md`, `LICENSE`, `package.json`, `v3/README.md`, `v3/@claude-flow/cli/package.json`.
- Orchestration: `v3/src/task-execution/domain/Task.ts`, `v3/src/task-execution/application/WorkflowEngine.ts`, `v3/src/coordination/application/SwarmCoordinator.ts`, `v3/src/agent-lifecycle/domain/Agent.ts`.
- Concurrency/recovery: `v3/@claude-flow/cli/src/services/bounded-worker-pool.ts`, `worker-queue.ts`, `headless-worker-executor.ts`, `checkpoint-gate.ts`, `worker-daemon.ts`, `swarm-memory-branches.ts`.
- MCP lifecycle: `v3/@claude-flow/mcp/src/task-manager.ts`, `server.ts`, `session-manager.ts`, `tool-registry.ts`, `rate-limiter.ts`, `transport/http.ts`.
- Memory/database/graph: `v3/@claude-flow/cli/src/memory/memory-bridge.ts`, `memory-initializer.ts`, `shared-sqlite.ts`, `graph-edge-writer.ts`, `hybrid-retrieval.ts`, `v3/src/memory/infrastructure/SQLiteBackend.ts`, `AgentDBBackend.ts`, `HybridBackend.ts`.
- Routing/local execution: `v3/@claude-flow/cli/src/ruvector/model-router.ts`, `router-parallel-recorder.ts`, `v3/@claude-flow/cli/src/mcp-tools/agent-execute-core.ts`, `plugins/ruflo-ruvllm/README.md`, `plugins/ruflo-mods/hooks/route/route-task.ts`.
- Security/federation: `v3/@claude-flow/security/src/policy/engine.ts`, `safe-executor.ts`, `path-validator.ts`, `tool-output-guardrail.ts`, `v3/@claude-flow/plugin-agent-federation/src/application/federation-coordinator.ts`, `policy-engine.ts`, `trust-evaluator.ts`, `domain/services/handshake-service.ts`, `plugins/ruflo-federation/README.md`.
- Plugin contracts: `plugins/ruflo-core/README.md`, `plugins/ruflo-swarm/README.md`, `plugins/ruflo-agentdb/README.md`, `plugins/ruflo-rag-memory/README.md`, `plugins/ruflo-rvf/README.md`, `plugins/ruflo-autopilot/README.md`.

## Open uncertainties

- Checkout permissions prevented direct inspection of all tracked files; Git-object reads covered the requested architecture, but the working tree is not a runnable checkout.
- Optional AgentDB/RuVector/WASM/native modules were not installed or executed, so actual persistence, HNSW, encryption, and controller behavior remains unverified.
- The repository contains overlapping root, V3 domain, CLI, and plugin contracts; the runtime entrypoint selected by a real installation may differ from the paths reviewed here.
- Federation, daemon, and worktree/process isolation paths were inspected selectively, not exercised against live peers or crash/restart scenarios.
- No load, failure-injection, security, or recovery benchmark was run.

Recommendation: ADAPT - reuse Ruflo's bounded lifecycle, WAL-aware memory, explicit policy, budget, and audit patterns behind Primus's local inference router; reject its direct-provider and fail-open/in-memory defaults.
