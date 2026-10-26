# DeepAgents research report

Scope: read-only inspection of the existing checkout, bounded source reads, and public GitHub metadata. No dependencies, builds, or inference calls were needed; the source was sufficient for this assessment.

## Identity and provenance

- Repository: `DeepAgents`; requested URL: `https://github.com/langchain-ai/deepagents.git`; inspected directory: `/linuxdata/Github/deepagents`.
- Local checkout: branch `main`, commit `2fe80c74637d33ad16f7215b93ede675759bfeae` (`Initial Commit`, 2026-04-19). It has `origin` at `https://github.com/furrepanther/deepagents.git` and `upstream` at the requested LangChain URL.
- Live metadata: `upstream/HEAD` and `upstream/main` resolve to `7a7c4e3708981568f96eb7fbc86aaef696c03001`; the local checkout is therefore not the current upstream main.
- Read-only state check: no status lines were observed in the bounded status attempt and the transient `.git/index.lock` was gone at final inspection. A diff/status read also hit `Operation not permitted` while reading loose object `20aa83e7...`; cleanliness is not certified.
- License: MIT, `/linuxdata/Github/deepagents/LICENSE`.
- The checked-in threat model is useful but generated for a different commit (`e859077f`) than this checkout; treat it as supporting documentation, not exact current-head provenance.

## Architecture

- The SDK is a Python 3.11+ monorepo package under `/linuxdata/Github/deepagents/libs/deepagents`. The core assembly point is `deepagents/graph.py`: it resolves a LangChain chat model, builds middleware, and returns a compiled LangGraph agent through `create_agent`.
- The default stack is composable middleware: todo planning, optional skills, filesystem, subagents, summarization, patch-tool-call repair, optional async subagents, caller middleware, provider/model profiles, tool exclusion, prompt caching, optional memory, human-in-the-loop, and permissions last. Ordering is intentional because later middleware can constrain earlier tools.
- Built-in capabilities are `write_todos`, filesystem tools (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`), optional `execute`, and `task`. The root README describes the package as a harness rather than a new model/runtime.
- Backends separate file/state persistence from execution: `StateBackend`, `StoreBackend`, `FilesystemBackend`, `LocalShellBackend`, sandbox backends, and `CompositeBackend`. `CompositeBackend` routes path prefixes to different backends.
- MCP is not a core dependency or runtime subsystem. The SDK accepts arbitrary tools; MCP wiring is supplied by `langchain-mcp-adapters`, the CLI, or deployment/examples. The CLI and deployment packages are materially broader than the SDK threat-model scope and must not be mistaken for core guarantees.

## State, memory, and database model

- `StateBackend` is ephemeral per LangGraph thread and writes are queued until a graph boundary. Cross-thread persistence requires a LangGraph checkpointer. `StoreBackend` uses a caller-supplied LangGraph `BaseStore` for persistent, namespaced files and requires `store=` when used.
- `create_deep_agent` passes `checkpointer`, `store`, `context_schema`, and `cache` through to LangChain/LangGraph. The core package does not select or create a SQLite/Postgres database; tests use in-memory saver/store implementations. Persistence policy is consequently an integration concern.
- `MemoryMiddleware` loads `AGENTS.md`-style files into the system prompt once per agent run and instructs the model to edit memory when it learns a durable preference. This is model-directed mutable memory, not an immutable context or signed evidence source. It has no visible content-size, integrity, or sensitivity boundary beyond prompt text such as “do not store credentials.”
- Summarization uses model-generated summaries and may offload older messages to `/conversation_history/{thread_id}.md`. It has useful token thresholds and recent-message retention, but if offload fails it logs/warns and continues with a summary whose older source may be unrecoverable. Async offload and summary generation are performed concurrently.
- Best ContextPack seam: `context_schema` gives the caller run-scoped structured context, while custom middleware can inject a read-only representation. DeepAgents itself does not enforce immutability, provenance, byte caps, or append-only evidence, so those guarantees need a wrapper/backend outside the core.

## Agent, tool, and subagent lifecycle

- `create_deep_agent` resolves the parent model, constructs middleware, then compiles a LangGraph agent. A supplied model can be a `BaseChatModel` or a provider/model string.
- Inline subagents are configured with a name, description, prompt, optional tools/model/middleware/skills/permissions, and are exposed through one structured `task` tool. The child receives a fresh task message and filtered runtime state; parent `messages`, todos, structured response, skill metadata, and memory contents are explicitly excluded to reduce leakage. The parent receives the child result as a tool message, not the child transcript.
- A general-purpose subagent is added by default when none is supplied. It may inherit parent tools, which is convenient but can broaden the execution surface unexpectedly. The core task tool is synchronous from the parent perspective; it does not itself provide bounded parallel scheduling.
- `AsyncSubAgentMiddleware` is a separate Agent Protocol integration. It creates remote threads/runs, stores task IDs and statuses in state, supports check/update/cancel/list, and can survive compaction/checkpointing. It depends on remote LangGraph SDK endpoints and authentication; cached status can be stale when live status fetches fail.
- Filesystem tool results are paginated and oversized tool/human messages can be evicted to artifact files with a preview and path reference. This is a good bounded-context pattern, but its limits are configurable and not an immutable evidence contract.
- `LocalShellBackend` invokes `subprocess.run(..., shell=True)` on the host. Its timeout and 100 KB output cap are operational limits, not sandboxing. `FilesystemBackend` virtual mode constrains paths but does not isolate processes or network access. `FilesystemPermission` applies ordered path rules and defaults to permissive when unmatched; execute permission is not implemented as a normal filesystem operation.

## Local model and routing fit

- Core model abstraction is provider-neutral at the LangChain boundary: `_models.py` accepts an existing `BaseChatModel` or calls `init_chat_model` for a string. Harness profiles customize provider/model initialization, prompts, tool descriptions, and middleware.
- The default graph model is `ChatAnthropic(model_name="claude-sonnet-4-6")`, requiring `ANTHROPIC_API_KEY`. OpenAI provider strings use the Responses API by default, with `store=False` available as a caller privacy option. These are external-provider behaviors, not local routing.
- No core reference to Primus router `http://127.0.0.1:11888`, llama.cpp, vLLM, or a fail-closed local-only policy was found. A caller could adapt a local-router-backed `BaseChatModel` or compatible endpoint, but DeepAgents does not enforce that adapter, detect router handoff signals, or fail closed when it is unavailable.
- Examples reinforce the distinction: `examples/nvidia_deep_agent/src/agent.py` uses direct `ChatNVIDIA`/`init_chat_model`, and deployment examples use provider model IDs and LangSmith sandbox configuration. These are not evidence of local-only SDK support.

## Reliability, security, and performance findings

- Positive: state writes have graph-boundary semantics; store namespaces are validated; filesystem reads support offsets/limits; shell output is capped; execution has a maximum timeout; large messages are moved to artifacts; subagent state filtering limits accidental parent-context leakage; provider profiles avoid scattered model-specific conditionals.
- High risk for this harness: host shell execution is explicitly unrestricted, has no OS isolation/resource limits, and can inherit environment variables. Direct host filesystem mode is similarly unsafe for untrusted tools. Neither is compatible with an immutable, local-only evidence boundary without a separate sandbox.
- The default `recursion_limit=9999` is a very loose loop bound. There is no core task budget, evidence-line budget, deterministic provenance ledger, or mandatory stop condition suitable for bounded research jobs.
- Permission middleware is last and useful for path constraints, but its own validation rejects execution-capable backends unless path routing is scoped; it does not provide a complete execute authorization model. Unmatched permission rules are permissive.
- Memory and summarization are convenience features, not trustworthy evidence stores: the model can edit memory files, loaded memory is prompt-visible, summaries can lose source history after offload failure, and there is no signature/immutability requirement.
- Async subagents add network/authentication, remote retention, stale-cache, and cancellation-state complexity. The included async server example is explicitly demonstration-only and uses in-memory SQLite, fire-and-forget execution, and no auth/rate limiting.
- Performance is thoughtfully addressed at the message layer (token thresholds, argument truncation, artifact offload, concurrent async offload/summary), but concurrency, retry, queue fairness, and resource accounting are integration responsibilities. The model can still create many sequential subagent calls.

## Reusable patterns

- Adopt the middleware assembly model and explicit ordering, with a final hardening middleware that enforces local routing, ContextPack read-only access, evidence caps, and authorization.
- Adapt the backend protocol and `CompositeBackend` idea to separate immutable ContextPack reads, append-only evidence writes, durable checkpoints, and any execution sandbox by namespace/path.
- Reuse offset/limit file reads, token-aware truncation, and large-result artifact references as bounded evidence transport. Add hard byte/line caps and content hashes at the harness boundary.
- Reuse subagent state-key exclusions and the one-result return shape to prevent parent memory/todo/context leakage. Add explicit task IDs, budgets, deadlines, and structured evidence references.
- Reuse the model-profile seam for provider-specific tool/prompt quirks only after the router adapter has been installed; keep routing policy outside provider profiles.
- Use `context_schema` as the typed ContextPack injection seam, with an immutable object and validation performed before graph execution.

## Rejected patterns

- Reject direct provider model construction/default Anthropic and direct OpenAI Responses use for Primus runtime paths; all inference must go through the local router and fail closed if unavailable.
- Reject `LocalShellBackend`, unrestricted `FilesystemBackend`, and any `shell=True` host execution for untrusted or research-agent work. Use a separately governed sandbox with explicit network, filesystem, process, and resource controls.
- Reject model-editable `AGENTS.md` memory as the source of truth for immutable ContextPack or evidence. Treat it, at most, as an untrusted optional hint.
- Reject default permissive path rules, implicit tool inheritance to general-purpose subagents, and a recursion limit of 9999 without harness-level budgets.
- Reject remote `AsyncSubAgentMiddleware` for local-only execution unless replaced by an approved local task service with bounded state, authenticated calls, and explicit evidence retention.
- Reject “warn and continue” when offloaded evidence becomes unrecoverable in a best-in-class harness; surface a typed failure or preserve a verified fallback artifact.

## Exact evidence paths

- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/graph.py:218-237,281-357,429-642` - public factory, middleware ordering, backend/checkpointer/store/context wiring, and graph compilation.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/_models.py:13-45` and `profiles/_harness_profiles.py` - model abstraction and profile customization.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/backends/state.py:38-141` - ephemeral thread state and graph-boundary semantics.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/backends/store.py:112-205` - namespace validation and persistent `BaseStore` integration.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/middleware/memory.py:82-160,256-347` - prompt-loaded, model-editable memory behavior.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/middleware/summarization.py:170-311,930-1070` - thresholds, history offload, overflow fallback, and unrecoverable-history warning path.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/middleware/filesystem.py:522-632,709-810,1053-1417` - filesystem/execute tools, pagination, timeouts, and large-message artifact eviction.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/backends/filesystem.py:43-182` and `backends/local_shell.py:1-82,104-356` - direct host filesystem and unrestricted shell warnings/implementation.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/middleware/permissions.py:44-90,230-253` - ordered path permissions, permissive unmatched rules, and execution limitation.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/middleware/subagents.py:166-178,371-475,526-605` - child-state exclusions, task lifecycle, and default general-purpose subagent.
- `/linuxdata/Github/deepagents/libs/deepagents/deepagents/middleware/async_subagents.py:71-126,273-361,435-723,862-950` - remote task state and check/update/cancel/list behavior.
- `/linuxdata/Github/deepagents/libs/deepagents/THREAT_MODEL.md` - useful stated trust/data model; generated for stale commit `e859077f` and explicitly excludes CLI/examples/tests.
- `/linuxdata/Github/deepagents/libs/deepagents/pyproject.toml` - core dependency boundary; no MCP adapter or local-router dependency.
- `/linuxdata/Github/deepagents/README.md` and `/linuxdata/Github/deepagents/examples/nvidia_deep_agent/src/agent.py` - advertised capabilities versus direct-provider example behavior.
- `/linuxdata/Github/deepagents/examples/async-subagent-server/README.md` and `server.py` - demonstration Agent Protocol server, in-memory SQLite, fire-and-forget execution, and no-auth caveat.

## Open uncertainties

- The inspected checkout is behind the live upstream main SHA, so behavior changed after `2fe80c7` is not covered. A fresh read-only clone at `7a7c4e3` would be needed for current-head confirmation.
- Git cleanliness could not be certified because a bounded diff/status read encountered a loose-object permission error; no destructive repair or fetch was attempted because the target directory was required to remain read-only.
- The exact guarantees of any LangChain/LangGraph checkpointer, store implementation, sandbox backend, MCP adapter, or deployment service are outside this repository and were not inferred from examples.
- Whether a local-router-backed LangChain `BaseChatModel` can preserve all required tool-call/structured-output semantics needs a focused adapter test against the Primus router. No such runtime probe was performed.
- The report does not claim that CLI/deployment packages share the SDK threat model; they require separate security and lifecycle review.

Recommendation: adapt.
