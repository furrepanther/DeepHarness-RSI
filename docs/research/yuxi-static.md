# Yuxi static research report

## Identity and provenance

- Repository: `https://github.com/xerrors/Yuxi.git`; local path:
  `/linuxdata/Github/Yuxi`.
- Inspected commit: `1d66405280631d30c8dd006703d9f270606d45a1`.
- License: MIT (`LICENSE`).
- Checkout: Git objects and HEAD are present, but SSHFS-backed working-tree
  checkout is incomplete with `Operation not permitted`; evidence below uses
  committed files through `git show`/`git grep`. No repository file was edited.
- Method: bounded static inspection. No dependencies, builds, tests, services,
  external provider calls, or cloud inference were run.

## Architecture and state model

- Yuxi is a FastAPI/LangGraph agent application with PostgreSQL as business,
  request, Run, message, configuration, and checkpoint authority; Redis carries
  ARQ delivery, events, cancellation hints, and caches; MinIO owns selected
  objects. The frontend consumes request and Run SSE streams.
- The request path commits the durable request and Run state before enqueueing
  work. FIFO queue policies, per-thread active-run checks, and recovery scans
  separate admission from execution.
- Workers claim a Run with an identity and attempt token, heartbeat the lease,
  reconcile stale ownership, and write terminal state under ownership rules.
  AgentRun manifests are write-once canonical JSON with SHA-256 fingerprints;
  stable operation IDs reconcile terminal output.
- Middleware composes context, model input, skills, tools, summaries, token
  usage, approvals, subagents, retries, and tool-error handling. Knowledge-base
  and sandbox capabilities are explicit extensions.

## Local-router fit

- `yuxi.models.chat` loads a provider/model record and constructs ChatOpenAI,
  ChatAnthropic, or Gemini adapters from the configured `base_url`. Built-in
  provider records include OpenAI, DeepSeek, OpenRouter, DashScope, and other
  external endpoints. This is flexible but direct-provider capable.
- No Primus `11888` enforcement, signed router policy, explicit cloud-handoff
  propagation, or caller-independent local/cloud decision boundary was found in
  the inspected paths. A Primus adapter must accept only the local-agent router
  endpoint and fail closed when it is unavailable.
- Network retry middleware, tool/sandbox request timeouts, and SSE observer
  limits are operation/liveness controls. They must be mapped carefully so none
  becomes age-based termination of a task under Primus's no-duration-cap rule.

## Reliability, security, and performance findings

- Strong patterns: database-before-queue ordering, FIFO admission, unique Run
  ownership, heartbeats and lease expiry, durable terminal reconciliation,
  PostgreSQL/Redis authority separation, write-once execution manifests, stable
  operation IDs, and explicit scope/workdir boundaries.
- Strong performance shape: Redis handles transient events while PostgreSQL
  avoids treating client observations as historical facts; middleware keeps
  context and tool capabilities composable; lazy sandbox creation avoids
  paying for unused execution resources.
- Risk: built-in external providers and user-configured base URLs can bypass
  Primus routing. The sandbox has command and request timeout controls but is a
  host trust boundary until wrapped with Primus execution policy.
- Risk: external observability, broad provider configuration, and knowledge/
  object-store connectors expand data and availability surfaces. Redis must
  remain non-authoritative, and provider/model cache records need provenance and
  local endpoint validation.
- Risk: the application is broad and infrastructure-heavy. Adopting it whole
  would duplicate Primus gateway, Memory Fabric, Agent Mail, router, and
  evidence policy and would increase operational surface.

## Reusable and rejected patterns

- Adapt: database-before-queue admission, FIFO queue state, lease/heartbeat /
  attempt ownership, write-once manifest fingerprints, operation-ID terminal
  reconciliation, Redis-as-ephemeral-event transport, explicit middleware and
  capability boundaries, and durable stale-run recovery.
- Reject unchanged: direct external provider records, arbitrary base URLs,
  broad Yuxi infrastructure, SSE duration limits as job limits, model/provider
  cache as a routing authority, and any silent fallback on lease, persistence,
  or router failure.

## Exact evidence paths and uncertainties

- `README.en.md`, `ARCHITECTURE.md`, `LICENSE`,
  `backend/package/pyproject.toml`.
- `backend/package/yuxi/services/agent_request_queue_service.py`,
  `backend/package/yuxi/services/agent_run_manifest_service.py`.
- `backend/package/yuxi/models/chat.py`,
  `backend/package/yuxi/models/providers/builtin.py`,
  `backend/package/yuxi/models/providers/cache.py`.
- `backend/package/yuxi/storage/postgres/models_business.py`,
  `backend/package/yuxi/agents/middlewares/`, and
  `backend/package/yuxi/agents/backends/sandbox/backend.py`.
- Runtime leases, migrations, provider behavior, and crash recovery were not
  exercised. The incomplete SSHFS checkout prevents a clean build claim.

Recommendation: adapt the durable queue/lease/manifest patterns only. Do not
adopt Yuxi as the Primus harness or provider/router authority.
