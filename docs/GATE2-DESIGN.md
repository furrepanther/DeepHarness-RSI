# Gate 2: Admission and Execution Ledger

Status: local implementation in progress; no production adapter or promotion.

The Gate 2 ledger is a task-scoped SQLite component in
`src/deepharness_rsi/ledger.py`. It is not a second Memory Fabric authority,
not an Agent Mail queue, and not a provider/runtime adapter. It stores only
identity, bounded state, digests, leases, transition evidence, and terminal
receipts.

## Authority and invariants

- Admission stores one immutable identity tuple: task ID, revision, payload
  digest, policy digest, owner session, task kind, evidence budget, inference
  route, schema version, creation epoch, and idempotency key.
- Repeating the exact identity is idempotent. Reusing a task ID or idempotency
  key with different immutable data fails closed.
- A task has at most one current lease. Every claim creates a new attempt,
  claim ID, and fencing token inside one `BEGIN IMMEDIATE` transaction.
- A worker must present the current claim ID, owner, revision, schema version,
  and fencing token for every mutation. A stale worker cannot heartbeat,
  settle, or cancel after revocation or replacement.
- Heartbeats require consecutive sequence numbers and a full evidence digest.
  Duplicate delivery of the same sequence and digest is idempotent; gaps and
  conflicting replays fail closed.
- Lease revocation is explicit and records actor, reason, and evidence digest.
  The task enters `reconciling`; a new claim is forbidden until an explicit
  reconciliation transition completes. No lease is revoked because of age or
  elapsed duration.
- Settlement inserts the complete typed receipt and terminal task state in one
  transaction. Replaying the identical receipt is safe; a different receipt
  cannot overwrite terminal truth.
- Transition history is append-only and read through a task-scoped tail with
  explicit record, byte, and line caps. A newest record that cannot fit is
  reported as an error rather than silently truncated. The ledger never reads
  whole logs or stores prompts/reasoning.

## State machine

```text
admitted -> claimed -> running -> complete|failed|blocked|cancelled|unknown
                         |
                         +-> reconciling -> admitted (after explicit proof)
```

`claimed -> running` is idempotent for the same fenced lease. Terminal states
are immutable. A restarted process reopens the same SQLite file and reconciles
from durable rows; it does not infer stale ownership from elapsed time.

## Gate 2 acceptance evidence

`tests/test_gate2_ledger.py` proves duplicate admission, idempotency conflict,
lease exclusivity, revision/schema mismatch, heartbeat ordering, fencing,
atomic settlement, duplicate terminal replay, explicit cancellation, restart
recovery, revocation/reconciliation, and capped task-scoped event reads.

Production integration, router execution, Agent Mail handoff, cross-host
fencing, load/chaos testing, and promotion remain later gates. No origin push
is implied by this design or its local commits.
