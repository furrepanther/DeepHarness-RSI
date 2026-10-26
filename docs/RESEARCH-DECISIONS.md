# Comparative Harness Research Decisions

Observed and synthesized: 2026-10-26. This is a bounded, read-only research
record. No candidate repository was promoted as a runtime dependency.

The objective is functional synthesis, not repository accumulation. Each
candidate is classified by what can safely be reused behind the Primus
contracts and what must be rejected.

## Decisions by repository

### bytedance/deer-flow - adapt selectively

Reuse the strict harness/application boundary, pure-argument model factory,
first-terminal-wins evidence handling, durable leases, bounded subagent
evidence, and lineage-aware retention. Adapt its memory behind Memory Fabric.
Reject direct provider configuration, self-owned DeerMem as durable authority,
and development-oriented sandbox assumptions as production isolation.

### deepseek-ai/deepseek-harness - adapt as the initial substrate

Reuse capability composition, immutable request admission, reversible effects,
settlement-based recovery, a provider-neutral model seam, atomic route
replacement, torn-tail recovery, write leases, scoped resources, and bounded
reconnect/close barriers. The personal fork is the initial code substrate.
Reject native direct-provider transports, provider-facing session logging,
and treating its local session store as the shared Memory Fabric.

The requested literal `deepseek/agent-harness` repository was not available;
the verified source is `deepseek-ai/deepseek-harness`.

### ruvnet/ruflo - adapt patterns only

Reuse the bounded worker pool, terminal task semantics, policy/provenance
receipts, path validation, WAL-aware persistence, and memory-provenance ideas.
Reject unbounded `Promise.all` fan-out, process-local queues presented as
distributed durability, simulated consensus, fail-open checkpoint behavior,
and direct provider calls. The refresh lane encountered an upstream shallow
fetch error, so its static Git-object report is evidence of design patterns,
not a runtime validation.

### alibaba/open-code-review - adopt contracts, harden the edges

Reuse immutable input identity, pure selection, sealed coverage manifests,
typed terminal failures, bounded process execution, workspace-root checks, and
symlink validation. Adapt durable journaling, fsync recovery, leases/fencing,
byte caps, secret handling, local-router calls, and a capability-scoped MCP
broker. Reject permissive repair as acceptance, raw body capture, direct
provider endpoints, remote tracing, and unlimited timeout defaults.

### langchain-ai/deepagents - adapt interfaces and local persistence

Reuse backend/middleware composition, SQLite indexing, local file-lock/token
fencing, bounded retries, and two-phase context offload/settlement ideas.
Upgrade local locks to distributed fencing where state crosses processes or
hosts. Reject direct provider construction and unrestricted host shell access.

### openai/openai-agents-python - adapt typed workflow contracts

Reuse typed output and guardrail results, handoffs versus nested agents,
approval/resume state, replay-safe retry classification, lifecycle cleanup,
and deterministic scripted-model tests. Adapt global tool/MCP concurrency,
pagination, evidence budgets, distributed session fencing, local-router model
calls, and local-only tracing. Reject default provider paths, cloud tracing,
`cwd` as a sandbox, unbounded tool execution, and LLM-as-judge as the only
acceptance mechanism.

### rohitg00/agentmemory - adapt bounded capture and retrieval

Reuse event identity, duplicate suppression, bounded spool/dead-letter flow,
hybrid retrieval, and revision recovery. Adapt storage to Memory Fabric and
make repair-lock acquisition and degradation visible. Reject a standalone
memory authority, broad implicit capture, direct-provider fallback chains, and
provider choice inside memory code.

### xerrors/Yuxi - adapt authority and fencing patterns

Reuse scoped receipts, intent hashes, leases, heartbeats, immutable attempts,
manifests, audit identities, owner checks, authorization refresh, and no-follow
atomic file operations. Reject transplanting its PostgreSQL/Redis/ARQ topology,
Redis as durable truth, and `always_trust` defaults.

## Synthesized baseline

The first DeepHarness-RSI implementation should combine:

1. Open Code Review's immutable identity and sealed coverage manifest.
2. OpenAI's typed state, output contracts, approval/resume, and reconciliation.
3. DeepSeek's admission, settlement, torn-tail, route-replacement, and lease
   seams.
4. DeerFlow's first-terminal-wins evidence, leases, and lineage retention.
5. Ruflo's bounded execution and policy receipts, with all unbounded fan-out
   removed.
6. DeepAgents' local indexing and offload settlement, upgraded with fencing.
7. Yuxi and AgentMemory's intent, receipt, duplicate-suppression, and recovery
   patterns behind the Primus and Memory Fabric authorities.

## Rejected common assumptions

The labels below were not accepted at face value during review:

- `distributed queue` can still mean a process-local in-memory queue;
- `sandbox` can still mean a shared working directory or tool filter;
- `guardrail` and `timeout` can be cooperative rather than veto authority;
- `persistent memory` can be a second store rather than shared durable truth;
- `tracing redaction` can protect one exporter while another sees raw data; and
- `evaluator` or `judge` examples are not deterministic acceptance contracts.

## Research limitations

The reports are bounded to selected source, documentation, and Git-object
evidence. They do not prove production compatibility, load capacity, crash
recovery, sandbox escape resistance, or measured throughput. Those are explicit
engineering gates, not silently waived findings.
