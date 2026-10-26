# DeepHarness-RSI Architecture

Status: design and research baseline; not production-ready.

DeepHarness-RSI is a Primus-native harness for two cooperating systems. It
borrows useful patterns from other projects, but it does not make any
research repository, provider SDK, second memory authority, or remote host a
hidden runtime dependency.

## Authoritative boundaries

The harness is organized around thin adapters with one owner for each
responsibility:

1. **Runner facade** accepts a task, records its identity, and exposes a
   runner-neutral lifecycle to Codex, Claude, Gemini, Cline, Qwen Code, and
   other supported runners.
2. **Router model adapter** sends substantive inference only to the local
   inference router. The adapter preserves request IDs, streaming terminal
   states, route evidence, and explicit cloud-handoff signals. It never calls
   a provider SDK directly and never chooses a cloud backend itself.
3. **Memory Fabric adapter** owns durable shared memory and compact
   provenance records. Candidate memory stores are optional adapters or
   bounded temporary stores, never competing durable authorities.
4. **Agent Mail execution adapter** handles cross-system work orders and
   accepted/running/terminal state transitions. Hints are advisory; the
   authoritative message and execution claim remain the source of truth.
5. **Sandbox and capability adapter** scopes filesystem, process, network,
   tool, and model permissions. A working-directory setting or tool filter is
   not treated as a security boundary by itself.
6. **Evidence and task ledger** records immutable task identity, leases,
   fencing, idempotency keys, state transitions, receipts, and bounded
   evidence pointers.

## Lifecycle and recovery

The intended lifecycle is:

`admit -> claim -> execute -> settle -> publish -> terminal`

Admission validates the task, policy envelope, source revision, and required
capabilities. A claim is unique to a runner session. Execution may be retried
only when the failure class and replay safety permit it. Settlement records
the outcome before derived views or notifications are updated. Publication is
idempotent and cannot turn an unknown or failed state into success.

Leases, heartbeats, fencing tokens, and terminal-state ownership protect
against duplicate workers and stale writers. A missing heartbeat is evidence
for investigation; it is not permission to terminate a job solely because it
is old or slow. Recovery requires an explicit lease/revocation transition,
reconciliation of side effects, and a safe-boundary re-dispatch.

## Memory and database design

Memory Fabric remains the durable shared-memory authority. A task-scoped
temporary database may be used for high-volume intermediate state, evidence
indexes, or retry bookkeeping when it has:

- an explicit owner, task ID, schema version, and retention deadline;
- WAL-aware single-authority access and bounded concurrency;
- idempotency keys, lineage, and exact-record cleanup;
- backup or reconstructability proof before destructive cleanup; and
- a post-cleanup check showing no active pointer or live reader remains.

Temporary stores improve locality and throughput; they do not become a second
cross-task memory fabric. Large evidence is carried through one compact,
complete packet plus an exact verified pointer, not through sequential
fragments or whole-log reads.

## Inference and model control

Deterministic work is handled without an LLM where possible. Model-using work
goes through the local router, which owns model selection, local capacity,
retry policy, and an explicit cloud handoff when local inference reports that
cloud reasoning is required. A caller must not bypass the router or silently
retry a failed local request against a provider.

Prompt classification and model-mode selection are policy modules behind the
router, not responsibilities scattered across runners. They must preserve
the model's explicit mode/help syntax and be tested against false routing,
context-budget, retry, and handoff cases before promotion.

## Recursive self-improvement

Harness2-style recursive self-improvement is an optional supervisor, not the
default execution path. It runs in an isolated sandbox with an immutable
parent policy, bounded task scope, explicit proposal/probe/compose records,
adversarial review, rollback, and operator-controlled promotion. Generated
changes cannot self-promote or widen their own capabilities.

## Two-system operation

Primus and Datacube share contracts, skills, runner definitions, and
provenance through their approved shared paths. Each system owns its local
processes and credentials. Cross-system actions use authenticated Agent Mail
work orders and the established control transport; filesystem sharing is not
treated as the control plane. A peer can advise or review, but it cannot
silently edit the other system's production source.

## Non-negotiable promotion evidence

Every implementation checkpoint must prove source provenance, local-router
use, bounded reads, concurrency ownership, crash/recovery behavior, privacy
boundaries, deterministic tests, cleanup, and rollback. Structural validator
success is not promotion approval. Any warning, error, unknown owner, missing
receipt, direct-provider route, or unresolved adversarial finding keeps the
checkpoint blocked.
