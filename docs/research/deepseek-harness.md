# DeepSeek Harness research report

Research date: 2026-10-21. Scope was read-only inspection of the existing checkout; no dependency install, build, inference call, or repository edit was performed.

## Identity and provenance

- Repository: `https://github.com/deepseek-ai/deepseek-harness.git`
- Local candidate: `/linuxdata/Github/deepseek-harness` (already present; no clone performed).
- HEAD: `47f943859bef60e4160492346772ded9b24f765a`; latest commit `Merge pull request #2519 from deepseek-harness/feat/npm-public`, dated `2026-08-13T19:38:46+08:00`.
- License: MIT, `/linuxdata/Github/deepseek-harness/LICENSE:1-21`, copyright DeepSeek 2026.
- Git state: dirty. `git status --short --branch --untracked-files=no` reported `master...origin/master [behind 10102]` and extensive tracked modifications/deletions. The checkout is not a clean reproducibility baseline; findings below use committed HEAD where possible and call out missing/working-tree-dependent evidence.

### Current worktree reconciliation - 2026-10-23

- The historical report above remains bound to source revision `47f9438`; it is
  not being rewritten as if it inspected the later personal-fork tree.
- The current checkout is `8581e8ab1f323a1ded5801a68f31900ac6b7ca4d` on
  `master`, with 8,416 tracked changed paths. The changes predate this program
  and were preserved without reset, merge, or edit.
- The recovery artifact at
  `/mnt/w/Backups/deepseek-harness-fork-20261022T031500Z` passed direct
  Windows-side verification against its own `SHA256SUMS` (`11` files,
  `BACKUP_CHECKSUM=PASS`). Full evidence is in
  `/usr/production/runtime/harness-research/20261023/h0-deepseek-provenance.md`.

## Architecture

- Cordis is the microkernel: plugins contribute services, typed events, and reversible effects. The model adapter, tool registry, session log, and agent loop are all replaceable plugins (`docs/architecture.md:7-9`).
- Composition is explicit and patchable: ordered bundle layers, profile patch, `$DSH_HOME/cordis.patch.yml`, then `--patch` overlays; later rows replace earlier rows (`docs/architecture.md:13-27`, `apps/cli/profile-boot.ts:212-235`). `dsh-base` supplies LLM, tools, persistence, sandbox/approval, settings, credentials, and telemetry (`docs/architecture.md:23`; `packages/bundle/base/cordis.patch.yml:34-232`).
- Core seams are `ctx.llm`, `ctx.sessions`, `ctx.systemPrompt`, `ctx.tools`, `ctx.agents`, `ctx.agentLoop`, `ctx.subagents`, and `ctx.jobs`. The capability table explicitly points providers to those registrations (`docs/architecture.md:140-162`).
- Request flow is event-driven: claim input, `agent/pre-step`, prepare request, append system/user/context events, freeze the model-visible history, stream through `llm/stream`, append assistant message/attempt, execute tools, then continue or end. The session log is the reconstruction source; “model-visible means logged” (`docs/architecture.md:110-124`).
- Best Primus insertion point is a base-profile row replacement plus a boot validator. Do not patch individual callers: replace/deny direct provider rows centrally and keep all policy at the `ctx.llm`/composition seam.

## State/memory/database model

- `Session` is an append-only `SessionEvent` log with validated, deep-frozen boundaries. Header state includes session id, absolute cwd, parent session, seed length, origin, delegation depth, and active agent preset (`packages/core/session/src/types.ts:56-99`).
- Durable context is JSONL through `@deepseek-ai/dsh-session-persistence-jsonl`; the physical backend owns framing, generations, repair, and publication. The base profile uses `$DSH_HOME/sessions` (`packages/session/session-persistence-jsonl/src/index.ts`; `packages/bundle/base/cordis.patch.yml:138-141`).
- SQLite is an optional projection/query capability, not the canonical log. Base config uses an in-memory session query database with `openAt: never` (`packages/bundle/base/cordis.patch.yml:157-161`; `apps/cli/reference/README.md:129`).
- Live agent streams are transient; durable `session/event` records drive replay, forks, telemetry, and persistence (`docs/agent-lifecycle.md`; `docs/architecture.md:120-124`).
- There is no native Memory Fabric or Agent Mail package in the inspected tree. For Primus, memory retrieval/writes and mail must be host-controlled services or tightly scoped local adapters, not hidden prompt mutation or unrestricted model tools.

## Agent/tool/subagent lifecycle

- Agent creation is scoped and transactional. `CreateAgentOptions` records caller/session/cwd/parent/seed/delegation metadata; setup composes the scoped world before publication and rolls back on failure (`packages/core/agent/src/index.ts:74-132`). Disposal stops the loop, drains work, unregisters the agent, removes its session, and unwinds its scope.
- The loop factory injects agents, sessions, LLM, tools, system prompt, and projections, then starts configured agents or resumes sessions (`packages/core/agent-loop/src/index.ts:295-355,549-569`).
- Subagents have a capability-negotiated provider API. Child depth is derived from persisted parent metadata; child options inherit parent provider/model/max tokens unless overridden; child session metadata records cwd, parent, origin, seed length, and delegation depth (`packages/subagent/subagent/src/types.ts:100-151,288-323`; `packages/subagent/subagent/src/child-agent.ts:1-220`).
- Child composition joins the parent preset, adds delegation prompt/persona/tool restrictions, and records delegated sandbox/approval overrides in the child log. Continuable children have one live activation; cold resume uses the logged suffix (`packages/subagent/subagent/src/child-agent.ts`; `packages/subagent/subagent/src/lifecycle.ts`; `docs/subsystems/subagent.md`).
- Tools are scoped registrations. MCP tools are exposed as deterministic `mcp__<server>__<raw>` names, with atomic generation replacement and rollback (`packages/mcp/mcp-client/src/tools.ts:100-169,219-250`).
- Jobs are owner-relative records. `ctx.jobs.wait(id, timeoutMs)` bounds observation, not the job itself; explicit kill/cancel and owner/context teardown are the termination paths (`packages/jobs/jobs/src/types.ts:1-100`; `packages/jobs/jobs/src/index.ts:74-133`; `packages/jobs/jobs-local/src/index.ts:220-279,466-529`).
- The repeat-tool guard is a useful advisory pattern: scoped per agent, canonicalizes arguments, caps previews, counts rejected calls, and emits logged model-visible reminders without silently vetoing or killing work (`packages/guard/repeat-tool-reminder/src/index.ts:1-30,151-229`).

## Local model and routing fit

Current fit is partial and requires an explicit Primus adapter/policy layer.

- `ctx.llm` has the right seam: provider adapter registration, configurable provider directory, route replacement, and an `llm/stream` waterfall (`packages/llm/llm/src/index.ts:48-64,282-354,431-474,911-923`).
- The native DeepSeek adapter registers `deepseek-official`, resolves `DEEPSEEK_BASE_URL` or defaults to `https://api.deepseek.com`, then directly calls `${baseURL}/chat/completions` with a bearer key (`packages/llm/llm-deepseek/src/index.ts:47,65,104-107,251-256`; `packages/llm/llm-deepseek/src/adapter.ts:214-305`). This bypasses the Primus router at `http://127.0.0.1:11888`.
- `llm-pi-ai` supports arbitrary provider profiles, base URLs, headers, API-key environments, request timeout, and stream-idle timeout (`packages/llm/llm-pi-ai/src/config.ts:64-140,294-371`; `packages/llm/llm-pi-ai/src/adapter.ts:276-357`). It is flexible enough to target a router but also makes direct-route bypass easy.
- Stream-idle watchdogs and provider request timeouts are liveness protections, not job-duration caps. They must remain distinct from the Primus no-duration-cap policy.

Exact Primus changes needed:

1. Add a first-class `primus-local-router` LLM adapter/service at `ctx.llm`. It must translate the harness provider-neutral request and stream chunks to/from `127.0.0.1:11888`, preserve `AbortSignal`, session/agent attribution, and reconstructable request events, and handle the router's explicit cloud handoff signal without retrying local or bypassing the router.
2. In the Primus base profile, replace or disable `llm-deepseek` and arbitrary direct `llm-pi-ai` provider rows. Add a boot-time fail-closed validator for missing router policy, direct external base URLs, pinned direct routes, or an active adapter not owned by the router. Callers must not choose local versus cloud; the router owns escalation.
3. Add policy tests at the composition boundary: every model request reaches the local router, direct bearer requests are impossible, router cloud handoff is returned through the same interface, and cancellation does not append uncommitted model input.
4. Add a Memory Fabric service bound to the session/agent scope. Retrieve through the Primus MCP bridge/API before prompt assembly, with explicit byte/line caps and project/session ownership; represent model-visible retrieved context as logged session events. Write durable notes only through the provenance-bearing memory contract after stable results, never read/write the remote database directly, and never use Memory Fabric for lifecycle telemetry or secrets.
5. Add a host-owned Agent Mail service wrapper around `/usr/production/agent-mail-link`. Require identity/preflight health, target only authenticated Agent Mail identities, enforce bounded bodies and attachments, and record send/ack/provenance events. Datacube implementation, review, advice, or active consideration must use the formal remote-work-order lane; do not expose arbitrary recipient/send/route primitives as generic model tools.
6. Make the Primus profile privacy-minimal: remove or disable `session-log-deepseek`, set OTel to `DISABLED` unless an explicit local collector and redactor are configured, reject non-local export endpoints, and ensure system prompts, tool args/results, workspace paths, and feedback text are redacted before any authorized export. Keep credentials outside session events and scrub ambient MCP environment/headers.
7. Add a Primus task-scoped evidence contract around `ctx.jobs` (or extend `JobStart`/`JobSnapshot`) with task id, purpose, owner, explicit stop condition, byte and line caps, and tail-only reads. Preserve `wait(timeoutMs)` as observation only; never auto-kill by age or elapsed time. Any explicit termination must carry a reason and validate exact PID/command/parent/owner/role, with lifecycle telemetry sent to the Primus system logger rather than Memory Fabric.

## Reliability/security/performance findings

- Strong reliability patterns: atomic adapter registration and last-good live config (`packages/llm/llm/src/index.ts`; `packages/llm/llm-deepseek/src/index.ts:200-256`), immutable request snapshots, append-only session generations, child depth limits, scoped disposal, MCP backoff with atomic tool swaps, and owner isolation for jobs.
- Privacy risk: the base composition references `session-log-deepseek` and documents default-on complete session-log suffix upload for official-model requests (`packages/bundle/base/cordis.patch.yml:43-45`; `apps/cli/reference/README.md:137-141`), but that package is absent from committed HEAD. Verify the clean upstream state before relying on this behavior.
- OTel is structurally safer but still sensitive: the source plugin defaults to `DISABLED`, while upload modes can export full message/tool/system-prompt/schema/path payloads and have no built-in redaction (`packages/session/session-telemetry-otel/src/index.ts:43-72,141-253`; `packages/session/session-telemetry-otel/README.md:22-38`). Primus must mount `DISABLED`, remove upload rows, or restrict to a local collector plus an explicit redactor; never inherit the base feedback/upload policy by accident.
- MCP stdio runs trusted executable code outside the agent sandbox; HTTP headers and environment are configuration-controlled. Default startup is non-fatal, calls default to 60 seconds, reconnect uses bounded exponential attempts, and task-based MCP execution is unsupported (`packages/mcp/mcp-client/README.md:38-50,64-71,113`; `packages/mcp/mcp-client/src/transport.ts`). Use only explicitly allowlisted servers and do not use MCP as the Memory Fabric or Agent Mail trust boundary.
- The committed tree contains `mcp-client` but no `packages/mcp/mcp-resources`; docs and the base patch reference `mcp-resources` (`packages/mcp/README.md`; `packages/bundle/base/cordis.patch.yml:492-493`; `apps/cli/composition.md:189,296`). Treat resource support as unverified.
- Local jobs are in-memory and have byte output limits but no task-scoped line cap, evidence provenance, or persisted owner/task contract (`packages/jobs/jobs/src/types.ts`; `packages/jobs/jobs-local/src/index.ts`). Teardown can await a non-settling producer. Add task id, purpose, owner, byte/line caps, tail-only reads, and explicit stop reason; use the Primus system logger for lifecycle telemetry.
- No-duration-cap enforcement needed: never auto-kill by age or elapsed time. A wait timeout may return a live snapshot only. Termination must be explicit and task-scoped, with exact PID/command/parent/owner/role validation before any process action; elapsed time may be evidence, never the kill predicate.
- Privacy changes needed: disable direct DeepSeek/session uploads, reject non-local telemetry endpoints, scrub MCP ambient environment and headers, make Memory Fabric records provenance-bearing and secret-free, and route Agent Mail only through authenticated `/usr/production/agent-mail-link` host policy. Mail send/remote work-order actions must not be arbitrary model-callable tools.
- Performance considerations: JSONL is the durable source and SQLite is optional indexing; MCP schema tokens are paid on every request; telemetry capture is on the session-event hot path but enqueues non-blockingly. Memory retrieval and evidence reads need explicit byte/line caps and should not block the agent loop.

## Reusable patterns

- Cordis service-definition seams with effect-scoped disposal and typed events.
- Session-event sourcing with “model-visible means logged,” immutable request snapshots, replayable assistant messages, and separate transient live streams.
- Provider-neutral `LlmAdapter` plus registry and `llm/stream` interception for routing/retry/policy.
- Parent-scoped child composition with persisted lineage, depth limits, tool filters, persona shadowing, and explicit disposal.
- Atomic MCP generation replacement, deterministic names, rollback on partial registration, bounded reconnect, and visible state transitions.
- Owner-relative jobs and advisory, model-visible guards that preserve control-flow transparency.
- Profile/bundle patch layers as the right deployment seam for Primus-specific policy without forking core loops.

## Rejected patterns

- Direct DeepSeek or arbitrary `pi-ai` HTTP from the harness: violates Primus local-router-only routing and permits silent cloud/provider bypass.
- Hidden Memory Fabric prompt injection: violates reconstructability and makes replay/privacy auditing impossible.
- Exposing Memory Fabric writes or Agent Mail/Datacube actions as unrestricted MCP/model tools: wrong trust boundary; use host-owned, authenticated, scoped services.
- Default external session-log/OTel export or raw telemetry without a Primus redactor and local-only endpoint policy.
- Age-based cleanup, elapsed-time kill, or treating `wait(timeoutMs)` as cancellation. This conflicts with the no-duration-cap evidence contract.
- Treating the current MCP bridge as resource/prompt/task-complete: committed evidence covers tools only; resources/prompts are not present in this checkout.
- Treating the dirty checkout as a runnable compatibility baseline without first obtaining a clean, pinned revision.
## Exact evidence paths

- Composition and invariants: `docs/architecture.md`, `docs/agent-lifecycle.md`, `docs/subsystems/subagent.md`, `docs/subsystems/llm-streaming.md`, `apps/cli/profile-boot.ts`, `apps/cli/composition.md`.
- Base profile: `packages/bundle/base/cordis.patch.yml`, `packages/bundle/headless/cordis.patch.yml`, `apps/cli/reference/README.md`.
- LLM seam/adapters: `packages/llm/llm/src/index.ts`, `packages/llm/llm/src/types.ts`, `packages/llm/llm-deepseek/src/index.ts`, `packages/llm/llm-deepseek/src/adapter.ts`, `packages/llm/llm-pi-ai/src/config.ts`, `packages/llm/llm-pi-ai/src/provider.ts`, `packages/llm/llm-pi-ai/src/adapter.ts`.
- Session/state: `packages/core/session/src/types.ts`, `packages/core/session/src/index.ts`, `packages/session/session-persistence-jsonl/src/index.ts`, `packages/storage/storage-sqlite/src/schema.ts`.
- Agent/subagent: `packages/core/agent/src/index.ts`, `packages/core/agent-loop/src/index.ts`, `packages/subagent/subagent/src/types.ts`, `packages/subagent/subagent/src/child-agent.ts`, `packages/subagent/subagent/src/lifecycle.ts`, `packages/subagent/subagent-spawn-in-process/src/index.ts`.
- MCP: `packages/mcp/mcp-client/src/index.ts`, `packages/mcp/mcp-client/src/transport.ts`, `packages/mcp/mcp-client/src/connection.ts`, `packages/mcp/mcp-client/src/tools.ts`, `packages/mcp/mcp-client/README.md`.
- Jobs/guards: `packages/jobs/jobs/src/types.ts`, `packages/jobs/jobs/src/index.ts`, `packages/jobs/jobs-local/src/index.ts`, `packages/guard/repeat-tool-reminder/src/index.ts`.
- Privacy/telemetry: `packages/session/session-telemetry/src/index.ts`, `packages/session/session-telemetry-otel/src/index.ts`, `packages/session/session-telemetry-otel/README.md`, `apps/cli/reference/README.md`.
- Provenance: `/linuxdata/Github/deepseek-harness/LICENSE`, `git rev-parse HEAD`, `git log -1`, and `git status --short --branch --untracked-files=no` from the checkout.
## Open uncertainties

- The checkout is massively dirty and 10,102 commits behind its configured remote. Deleted/absent packages may be a partial working-tree state, a branch mismatch, or generated/source skew; no runtime conclusion should be based on them until a clean clone or clean pinned checkout is available.
- `session-log-deepseek` and `mcp-resources` are referenced by docs/base composition but absent from committed HEAD paths inspected. Their current implementation, privacy defaults, and resource semantics remain unverified.
- Base configuration and package defaults may differ: OTel source defaults to `DISABLED`, while base documentation/config describes feedback-gated upload; the effective Primus composition must be checked after clean resolution.
- The exact Primus router request/stream schema and cloud-handoff headers were not inferred or guessed. Implement the adapter against the signed local router policy and runtime contract.
- No live Memory Fabric, Agent Mail, or router integration was exercised; this is intentional static repository research under the task constraints.
Recommendation: adapt — reuse the Cordis composition, event-sourced session, adapter, scoped subagent, MCP generation, and owner-job seams, but replace direct model/upload/control paths with Primus-owned fail-closed policy adapters before adoption.
