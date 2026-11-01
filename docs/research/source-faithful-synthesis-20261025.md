<!-- Repository copy: source snapshot retained below. The requested deepseek/agent-harness URL was unavailable; research used the separately identified deepseek-ai/deepseek-harness repository. Claims below that all requested URLs were fetched are historical and do not supersede that qualification. The independent gate remains incomplete. -->

# DeepHarness-RSI Source-Faithful Comparative Synthesis

Date: 2026-10-25
Scope: eight bounded GitHub reports, fetched from the requested upstream URLs
through the existing local clones under `/linuxdata/Github`.

> **Review status correction (2026-11-01):** The historical review result below
> does not establish a source-complete, empty-boat gate. The saved final-review
> packet contains an abbreviated evidence index and a pointer, and the saved
> reviewer result reports unclear, wrapper-scaffolded requirement coverage.
> Treat the research conclusions as candidates pending a new source-complete
> adversarial review. Evidence: `AG_PHASE0_RESEARCH_GATE_EVIDENCE_GAP_20261101`
> in Memory Fabric and the original packet and result under the review path below.
>
> **Source correction (2026-11-01):** At DeepSeek revision
> `22ddee3792402c3e70ec5f86a63c3e3e895a2f60`, the JSONL session backend
> implements per-session cross-process single-writer ownership using kernel
> primitives, and the shared persistence contract snapshots and validates
> append batches and checks contiguous sequence numbers. The original
> selected-source report's statement that no concurrency model was visible
> does not describe this backend. This does not establish cross-host locking
> semantics or show that every session backend uses JSONL. Evidence:
> Memory Fabric `sm-500177d1-0222-4aa2-9faf-569e68a982e5`.
> A follow-up inspection found serialized appends, fsync before cursor
> advance, explicit rollback after write/sync failures, and torn-tail repair.
> These are candidates for measured fault-injection tests, not proof of
> cross-host durability or authorization to truncate production data. Evidence:
> `sm-d2684e40-b6a3-4bbc-896d-ce24fdd57d00`.

## Acceptance evidence

- Wave: `/usr/production/runtime/harness-research/dispatch-wave-20261025-source-faithful/`.
- Four sequential lanes, eight reports, all lane return codes zero.
- Every report used `source_ref=FETCH_HEAD`; every captured revision matched a
  fresh `git ls-remote URL HEAD` check.
- Every local path was under `/linuxdata/Github`; existing dirty worktrees were
  not reset, overwritten, or edited.
- Every report proved local routing (`x-inference-route=worker` with loopback
  upstream), `cloud_used=false`, and no queue timeouts, cancellations, or
  rejections. Final router state was idle at `0/4`.
- The research worker fail-closed on missing `FETCH_HEAD`. Its source-integrity
  repair removed blobless upstream fetches and set `GIT_NO_LAZY_FETCH=1` while
  reading evidence, preventing a partial clone from silently obtaining blobs
  from its configured `origin`.

## Historical review result (not a cleared gate)

The historical local review package recorded a no-block result for the worker,
launcher, tests, synthesis, and plan integration in
`/usr/production/runtime/harness-research/review-source-faithful-20261025-r3/result.json`.
All six SDLC lanes and Grumpy completed with
`no_blocking_defect_found`; failed, parse-failed, retried, and targeted-repair
lane counts were all zero. The final packet uses recognized reviewer fields,
one complete evidence index, and `FULL_ARTIFACTS` for verified pointer-backed
complete bytes. Eight regression tests pass, including stale-local-source
rejection, upstream-fetch fail-closed behavior, explicit URL/`FETCH_HEAD`
provenance, lazy-fetch suppression, local-only routing, and no duration-based
termination controls.

## Decision

Build DeepHarness-RSI as a Primus-owned orchestration layer. Adapt proven
coordination and isolation patterns, but keep the Primus contracts authoritative:
all substantive inference enters `127.0.0.1:11888`; Memory Fabric is the only
durable shared memory; skills and runner policy are universal and inherited by
intersection; evidence is task-scoped and bounded; slow live work is never
terminated solely by age or wall-clock duration; and promotion requires an
empty-boat gate.

## Adopt or adapt

1. Lease-based ownership with heartbeat, fencing, and idempotency keys. A missed
   heartbeat is evidence for investigation, not a duration-only kill signal.
   Recovery requires an explicit lease/revocation transition and safe-boundary
   re-dispatch. Ruflo's `workspace-lease.ts` is advisory: its time-based
   expiry, host-local PID check, and error-to-empty behavior cannot establish
   cross-host write ownership. Source evidence: Memory Fabric
   `sm-9327ee06-58e9-4276-be89-805541d2cb88`.
2. Isolated subagent context and deterministic file/evidence bundling. Each
   worker receives a manifest and cannot read outside it. Write leases prevent
   two writers from sharing a worktree; read-only workers may share a checkout.
3. Versioned append-only session/coordination state with additive-only schema
   migrations. Coordination records are records, not side effects; replay is
   idempotent; completed steps are not re-executed after resume.
4. Policy-decreasing delegation. A child can lose tools, namespaces, network,
   concurrency, depth, or expiry, but can never widen the parent envelope.
5. Progressive-disclosure skills with a read-only reviewer, signed/versioned
   manifests, and separate contributor/CI versus runtime skill classes.
6. Deterministic tiering before model dispatch: satisfy deterministic work
   without an LLM, then use the least expensive suitable local-router mode;
   every model-using tier still goes through the same router.
7. Narrowest-escalation sandbox recovery, path validation at the owning
   filesystem boundary, and local Unix/Docker backends. Hosted sandbox and
   arbitrary remote execution are not initial runtime dependencies.
8. Local observability: trace IDs, token counts, state transitions, receipts,
   and redacted error metadata. Do not export prompts, hidden reasoning, tool
   payloads, or external LLM traces. Model-visible state must be reconstructable
   from the local session record without making that record a second durable
   memory fabric.
9. Context compaction and task-scoped spill/pointer records. Keep the complete
   evidence in a temporary, bounded store; carry one compact complete packet and
   an exact verified pointer through constrained review lanes; purge by exact ID
   only after lineage and receipt checks pass.
10. Evaluate DeerFlow's tool-call history repair as a model-facing projection.
    Preserve original events and receipts; a missing result does not establish
    whether a side effect occurred. Never replay ambiguous side effects without
    claim and idempotency evidence. Source and limits: Memory Fabric
    `sm-ab44d2a0-898f-49b7-a568-e2ffbb66f58c`.
11. Evaluate open-code-review's sealed pre-dispatch selection and coverage
    manifest, but separately account for every task-scope artifact. Its selected
    denominator excludes deleted, filtered, and oversized files; those need an
    explicit disposition before our gate can claim complete coverage. Source:
    Memory Fabric `sm-58279c35-ef30-4c6d-8edc-38e38de6852a`.
12. Evaluate AgentMemory's weighted reciprocal-rank fusion with explicit
    per-stream provenance. Its per-query active-stream normalization changes
    the scale when streams differ, and expanded queries share graph cancellation;
    neither behavior should be adopted without local quality and lifecycle
    tests. Source: Memory Fabric `sm-e0326e99-0ec7-46e4-8219-457c8caacc06`.

## Reject

- Direct Anthropic/OpenAI/AWS/DeepSeek/provider SDK calls, arbitrary `api_base`
  overrides, and provider-specific environment escape paths.
- Standalone competing durable-memory systems such as AgentMemory, DeerMem,
  AgentDB/RuVector, or a harness-owned persistent state fabric. A per-task
  temporary SQLite store may exist only as an explicitly bounded execution
  ledger; durable cross-task truth remains Memory Fabric.
- External LangSmith/Langfuse/Monocle/OTel prompt tracing and any telemetry
  path that can capture hidden reasoning or private tool payloads.
- Unbounded "read the full repository" review behavior, whole-log reads,
  fragment sequencing, and delegation that hands model/provider choice to an
  uncontrolled external coding agent.
- Upstream repository edits, automatic promotion, or a second unreviewed
  harness/runtime port.

## Deferred or gated candidates

- Harness2's recursive Propose-Probe-Compose/self-improvement loop is a Phase 5
  supervisor candidate only. It must run in an isolated sandbox, use immutable
  parent policy, require evidence-backed proposals, and never self-promote.
  Its clock/timeout behavior is a safety-versus-liveness study item; it is not
  suppressed until that study is complete.
- AgentFS remains a late compatibility/performance experiment because it is beta,
  adds a filesystem/storage boundary, and its pinned tree did not provide a
  verified root license file. It is not a current memory or runtime dependency.
- Yuxi's PostgreSQL/Redis/VM architecture supplies useful lease, queue,
  checkpoint, sandbox, and path-validation patterns but is not transplanted as
  a second Primus control plane.

## Implementation checkpoints

Each checkpoint is empty-boat: no warnings, failed tests, stale provenance,
unknown ownership, direct-provider route, missing receipt, or unresolved
adversarial finding may pass.

1. Freeze the canonical contracts and capability matrix; reject direct routes
   statically and prove child-policy intersection with synthetic fixtures.
2. Implement the local-router adapter, admission/lease ledger, idempotency
   keys, and liveness evidence; test duplicate delivery, cancellation,
   restart, stale lease, and model/schema mismatch without duration-only kills.
3. Implement task-scoped evidence packets, temporary pointer storage,
   compaction, exact-ID cleanup, and lineage/backup proofs; test truncation,
   missing pointer, stale pointer, and partial purge failure.
4. Add universal skills/runners and sandbox boundaries; test Codex, Claude,
   Gemini, Cline, Qwen Code, and DeepHarness-RSI inheritance without child
   widening or direct inference bypass.
5. Add the deterministic prompt/intent classifier and mode selector only after
   the router contract is green; measure false routing, fallback, and context
   budget behavior with the DavidAU mode/help matrix. Keep llama.cpp K/V at
   `q8_0/q8_0`; never use K `q4_0` for long-context production because the
   observed accuracy-loss risk can reach roughly 50 percent.
6. Evaluate Harness2 as a bounded, review-only self-improvement supervisor;
   require Red-Team-Gate, Solid Snake, SDLC, performance, security, and
   rollback evidence before any generated change can be staged.
7. Run shadow/canary tests, Nebula selectively, cross-system Datacube boundary
   checks, and a controlled rollback. Promote only after all receipts and
   manifests are complete and the old release remains restorable.

## Provenance

| Repository | Upstream revision | Report SHA-256 prefix |
|---|---|---|
| `bytedance/deer-flow` | `a1b89d0432de4e45adc59f512cb25bb386ea1e51` | `0cf2f2d6cc823158` |
| `ruvnet/ruflo` | `31f554c7b290153119e6f58869e1f849e1f2acd4` | `8d2ec21fa29bc37e` |
| `deepseek-ai/deepseek-harness` | `22ddee3792402c3e70ec5f86a63c3e3e895a2f60` | `1334f05cdeb451ac` |
| `alibaba/open-code-review` | `375f64cd6f67a48a135da83cfcf59c52669a09cb` | `d09294b3da87f5f8` |
| `langchain-ai/deepagents` | `e9e03f7c1a373f458170c898001fa9759c411889` | `c1bc666ff6434cdb` |
| `openai/openai-agents-python` | `0dc4cf152bff1f50bdc0e41f28808563406545b2` | `bacebaae53426425` |
| `rohitg00/agentmemory` | `3a6758ac8d21172e727f97910800865d3d07cb28` | `217a3255b38fe7f7` |
| `xerrors/Yuxi` | `a5ac16dd11fd2eed7381960f7130321782eea206` | `32b8e831d2f57cc8` |

Research limitation: reports are bounded to selected upstream documentation and
safe files, not full source builds or runtime compatibility tests. The next
phase must inspect implementation seams for any candidate selected for adoption.
