# DeerFlow bounded research view

- Upstream: `https://github.com/bytedance/deer-flow.git`; commit
  `8f9409bccc0fbcb995864f0e66375dbbb52f7fa7`; MIT; local path
  `/linuxdata/Github/deer-flow`.
- SSHFS checkout was incomplete with `Operation not permitted`; committed Git
  evidence was used. Original report remains at `deer-flow.md`; this view is
  the <=120-line manifest artifact.
- Harness package owns LangGraph agent construction, middleware, ThreadState,
  checkpointers, run/event persistence, sandbox, MCP, skills, memory, tools,
  subagents, tracing, and runtime policy. The app lifespan and product gateway
  are broader than the reusable harness.
- Checkpoint providers cover in-memory, SQLite, and PostgreSQL. Event stores,
  runs, SSE replay, and application records are separated. Retention guidance
  is lineage-aware: parent ancestry, pending writes, and resume targets matter.
- DeerMem uses scoped canonical JSON/Markdown memory, SQLite FTS5/BM25, WAL,
  atomic fact updates, debounced writes, and bounded shutdown flush. Memory
  adapters are backend-neutral and expose capability flags.
- Subagent registry/capacity/executor provide FIFO admission, leases,
  heartbeats, first-terminal-wins transitions, cleanup, bounded evidence, and
  acceptance results. Large artifacts are referenced by hash/path rather than
  copied into checkpoints.
- Local router fit is partial: provider abstraction permits a Primus
  OpenAI-compatible base URL but does not enforce `11888`, cloud handoff, or
  intent-based routing. Default/example web and hosted sandbox integrations
  must be removed for local-only use.
- Local host sandbox is not a production isolation boundary. Tracing and
  memory LLM hooks need Primus policy, redaction, and local-router ownership.
- Adapt: factory/state/checkpointer seams, lineage retention, scoped atomic
  memory, admission/lease/heartbeat/acceptance patterns, content-addressed
  evidence, and one trace identity with system-logger telemetry.
- Reject unchanged: DeerFlow app/deployment surface, direct provider choice,
  implicit fallback memory, bare age/size checkpoint trimming, and host sandbox
  as isolation.
- Evidence: `backend/packages/harness/deerflow/agents/thread_state.py`,
  `goal_state.py`, `runtime/checkpointer/`, `runtime/events/store/`,
  `agents/memory/`, `subagents/`, `sandbox/local/local_sandbox.py`, and
  `backend/docs/checkpoint-retention-contract.md`.

Recommendation: adapt selected contracts only; do not adopt the full app or
make its provider/memory policy authoritative.
