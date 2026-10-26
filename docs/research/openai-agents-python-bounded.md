# OpenAI Agents Python bounded research view

- Upstream: `https://github.com/openai/openai-agents-python.git`; local commit
  `dca426eec17ec040dc8a8fe109869509fd2281e2`; MIT; local path
  `/linuxdata/Github/openai-agents-python`.
- Initial checkout was clean, but final verification found 873 externally
  modified entries. This task did not inspect, edit, or revert them. Official
  upstream main was observed at `64cd5dfc5a1579870dcbed0ea42b27aa84033fee`.
  Original report remains at `openai-agents-python.md`.
- `Model`/`ModelProvider` and custom-provider examples are a strong seam for
  a Primus local-router adapter. `Session` and `SQLiteSession` provide local
  history with WAL/thread-local persistence and atomic tail removal.
- Guardrails cover input/output and tool boundaries. Function tools have
  invocation timeouts. Runner termination is turn/tool/handoff/guardrail based,
  not global age-based termination, which fits Primus when task stop rules are
  explicit.
- Hosted MCP, hosted shell/container, computer, web/file search, code
  interpreter, and hosted patch tools are not local-only primitives.
- Defaults are cloud-oriented: bare model/provider selection, OpenAI Responses,
  tracing, sensitive-data inclusion, and an external trace exporter. Caller
  `OPENAI_BASE_URL` alone is not a fail-closed Primus policy.
- Local shell, stdio MCP, and caller executors remain host trust boundaries;
  Primus must own executable, argument, environment, filesystem, network,
  resource, and approval policy.
- Adapt: provider/session/guardrail interfaces, local SQLite session shape,
  structured tool errors, and no-global-age-termination runner semantics.
- Reject unchanged: default model/provider selection, hosted tools, default
  tracing/raw capture, server-managed cloud conversation state, and bare
  provider configuration as routing enforcement.
- Evidence: `src/agents/models/interface.py`,
  `src/agents/models/openai_chatcompletions.py`,
  `src/agents/memory/session.py`, `src/agents/memory/sqlite_session.py`,
  `src/agents/guardrail.py`, `src/agents/tool_guardrails.py`,
  `src/agents/run.py`, and `docs/tracing.md`.

Recommendation: adapt interfaces and guardrails only; do not adopt its hosted
runtime or cloud defaults.
