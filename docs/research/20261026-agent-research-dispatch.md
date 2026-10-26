# Local Research Dispatch - 2026-10-26

Status: `complete`; this is a research record, not a runtime dependency or
production-promotion approval.

The parent repository for DeepHarness-RSI is
`/linuxdata/Github/DeepHarness-RSI`. It is the only authoring location and the
working backup-of-record. Candidate checkouts under `/linuxdata/Github` are
read-only research inputs. No candidate checkout may be repaired, restored,
staged, or pushed as part of this dispatch. Pushes from the parent repository's
personal `origin` remain operator-gated.

## Dispatched lanes

Four local subagents were dispatched with `fork_context=false`, read-only
scope, local-inference-only instructions, and disjoint checkout pairs:

| Agent | Read-only scope | Required output |
| --- | --- | --- |
| `Archimedes` (`01a1798e-106c-7153-88b1-2e51eb411c70`) | `/linuxdata/Github/deer-flow`; verified DeepSeek mapping `/linuxdata/Github/deepseek-harness` | Exact revision/path evidence; adapt/adopt/reject recommendations |
| `Peirce` (`01a1798e-10ee-75a1-b099-bb63c4df66f1`) | `/linuxdata/Github/ruflo`; `/linuxdata/Github/open-code-review` | Orchestration, review, security, and bounded-execution findings |
| `McClintock` (`01a1798e-114a-75a3-88b2-cc667c87f6ce`) | `/linuxdata/Github/deepagents`; `/linuxdata/Github/openai-agents-python` | Runner, lifecycle, tool, handoff, and persistence findings |
| `Harvey` (`01a1798e-11a3-7270-bc4d-9396a81c6b2d`) | `/linuxdata/Github/agentmemory`; `/linuxdata/Github/Yuxi` | Memory, authority, fencing, duplicate-suppression, and recovery findings |

## Integrity constraints

- The requested literal `deepseek/agent-harness` remains represented by the
  verified `deepseek-ai/deepseek-harness` source; this mapping is not silently
  changed.
- `deer-flow` and `agentmemory` reported pre-existing dirty worktrees during
  dispatch. Those lanes were explicitly directed to use committed Git objects
  only and to record the caveat. Dirty worktrees are not repaired or silently
  treated as clean; no cleanup or destructive recovery is allowed.
- Agent reports are not complete until exact commit/path evidence, limitations,
  and adopt/adapt/reject decisions are returned. A live dispatch is not a
  research conclusion.
- Returned findings will be synthesized into this parent repository, tested,
  and reviewed before any implementation or promotion decision. No origin push
  is authorized by this record.

## Research synthesis

All four lanes completed locally against committed Git objects. No candidate
checkout, runtime service, inference route, or origin repository was modified.
The findings below are design guidance for DeepHarness-RSI, not a claim of
production compatibility.

### Archimedes - DeerFlow and DeepSeek

- Source evidence: DeerFlow `8f9409b...`; DeepSeek verified source
  `deepseek-ai/deepseek-harness` at `47f943859...`; the local checkout also
  exposed `8581e8ab...` as a pinned ancestor. Dirty-worktree caveats remain.
- Adopt bounded completed-run evidence: owner/scope cursors, retention
  revisions, redaction, SHA-256 digests, byte/event limits, explicit
  `LIMIT_EXCEEDED`, capacity admission, leases, and checkpoint-retention
  contracts.
- Adapt DeepSeek's composition substrate, JSONL torn-tail/fsync and revision
  reads, atomic generation swaps, bounded child depth, policy, and lineage
  behind the local router at `http://127.0.0.1:11888`.
- Reject direct provider URLs/API keys/custom endpoints, DeerMem or a session
  store as Memory Fabric authority, and host-native sandbox/transport paths.

### Peirce - Ruflo and Open Code Review

- Adopt deterministic agent selection and frozen coverage manifests from
  Open Code Review, resumability, bounded ACP, pure resource admission, path
  validation, SafeGit, retrieval guards, and lock recovery.
- Adapt security checks to fail closed on task/session identity and require
  stable task/source/policy/router digests, deterministic complete selection,
  explicit partial/cancelled/blocked/failed/complete states, and bounded
  evidence.
- Reject direct provider/cloud paths, permissive or unverified authorization,
  simulated consensus, duration-only termination, non-cancelling timeout
  races, silent task drops, and unbounded file reads. Relevant reviewed paths
  included Open Code Review `internal/agent/selection.go`,
  `internal/session/manifest.go`, `internal/agent/agent.go`,
  `resume_identity.go`, `grouping.go`, `types.go`, `runner.go`, and
  `internal/llm/providers.go`, plus Ruflo's resource-admission,
  path-validator, SafeGit, identity, propagation, retrieval-guard, and lock
  guard modules.

### McClintock - DeepAgents and OpenAI Agents Python

- Adopt middleware layering, checkpointer/store separation, permissions-last
  ordering, context-managed cleanup/restart tests, strict schemas and
  approvals, bounded SQLite retries, and resumable run state.
- Adapt asynchronous task state into a harness-owned append-only receipt
  ledger with immutable IDs and digests. Required receipt fields include
  work-order/revision/event/owner/claim identifiers, idempotency key,
  input/output/evidence digests, router request ID, route, adapter, host/peer,
  attempt, and terminal status.
- Reject direct provider defaults, cached status or final messages as proof of
  completion, conversation history as the receipt authority, broad search as
  a second authority, silently skipped corrupt rows, and unverified sandbox or
  built-in-tool trust paths. Proof cases must cover router-unavailable,
  cloud-handoff, unknown receipt, duplicate/idempotency, crash, wrong-owner,
  and digest-mismatch scenarios.

### Harvey - AgentMemory and Yuxi

- AgentMemory evidence exposed process-local five-minute deduplication,
  truncated hashing, local-only locks/leases, event-ID reuse without payload
  digest comparison, mtime-only stale claims, crash windows, swallowed
  exceptions, and snapshot-unblock risk.
- Adopt Yuxi's durable row-lock/owner-token/recheck model, immutable attempt
  history, commit-before-enqueue with recovery scanning, manifest
  fingerprints, and explicit memory authorization/advisory locking.
- Adapt shared compare-and-swap lease fencing with a generation token and the
  identity tuple `scope + operation + payload_digest + schema`. Keep Memory
  Fabric canonical. Reject process-local maps/mutexes, direct database access,
  mtime-only reclaim, ACK-as-acceptance, blind retry, and silent catches.

### Cross-cutting baseline

DeepHarness-RSI should use one authoritative durable ledger plus Memory Fabric
for durable shared knowledge, with notifications treated as projections rather
than truth. Every operation needs stable task, revision, payload, policy, and
router digests; a fenced owner/claim; bounded task-scoped evidence; explicit
unknown and reconciled states; local-router-first inference; and no
duration-only termination. Candidate research repositories remain read-only
inputs. Any future implementation belongs in this parent repository (or a
personal fork created here), is locally reviewed and tested, and remains
unpromoted until separately authorized. Origin pushes remain explicitly
operator-gated.
