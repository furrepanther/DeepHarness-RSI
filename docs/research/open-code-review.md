# OpenCodeReview research report

## identity and provenance

- Repository: `https://github.com/alibaba/open-code-review.git`, Alibaba, public Go repository, default branch `main`.
- Local path: `/linuxdata/Github/open-code-review`.
- Checkout: `375f64cd6f67a48a135da83cfcf59c52669a09cb`; shallow clone; working tree clean; `origin/main` resolved to the same commit.
- HEAD: `fix(tool): report an empty code_comment batch instead of success (#1773)`, authored 2026-10-20. The preceding visible commit fixes MCP `tools/list` pagination.
- License: Apache-2.0 (`LICENSE`, `go.mod`, README). GitHub metadata describes a hybrid deterministic-pipeline plus LLM-agent reviewer with line-level comments and multi-language rules.
- GitHub REST `GET /repos/alibaba/open-code-review/security/advisories` returned HTTP 404 with `{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}`. This does not prove that no advisories exist. `.github/SECURITY.md` directs private vulnerability reports to GitHub Security Advisories and calls out crafted diffs/configs/LLM responses, credential leakage, path traversal, and exploitable dependencies.
- Scope: bounded static inspection of the shallow checkout and public GitHub metadata. No dependencies were installed; no build, test suite, or external/cloud inference was run.

## architecture

- Main flow is `ocr review` -> deterministic diff/input selection -> semantic file grouping -> isolated per-group plan/main review loops -> deterministic comment filtering and location -> immutable run manifest plus JSONL session history. `ocr scan` uses the same tool/agent machinery with a scan-specific template.
- Deterministic stages select changed files, exclude unsupported/secret/noise paths, freeze input identity, and create the coverage denominator before concurrent work starts. LLM stages generate candidate comments, but location and completion are tracked outside the model.
- Grouping is a divide-and-conquer stage. Bundles are isolated contexts and execute concurrently, with a default maximum of eight groups. Group-level token and timeout accounting bounds overrun to in-flight groups.
- Evidence is line-oriented: `code_comment` carries path, line/range, category/severity, existing code, suggestion, and optional reasoning. Resolution first uses the same-file diff, then deterministic cross-file relocation, then optional LLM re-location. Comments are accepted only after location/validation and can be removed by the review filter.
- Rules are embedded and layered: custom `--rule`, project `.opencodereview/rule.json`, global user rule, then embedded system rules. `CanonicalConfig` hashes effective rule text/order. `default_exclude_patterns.json` filters review noise; `default_secret_patterns.json` is an unconditional secret-path gate.
- Tooling is a frozen registry of built-ins (`file_read`, `file_find`, `file_read_diff`, `code_search`, `code_comment`, `task_done`) plus optional MCP tools. Reserved-name and duplicate-name checks prevent MCP shadowing of built-ins.

## state/memory/database model

- There is no relational run database in the reviewed path. Run state is a mutex-protected in-memory `SessionHistory`, persisted as append-only JSONL at `$HOME/.opencodereview/sessions/<encoded-repo-path>/<session-id>.jsonl` with directory mode 0700 and file mode 0600 (`internal/session/persist.go`).
- Records include session start/end, requests, responses, tool results, timing, failures, resume lineage, and a final `ocr.run-manifest/v1`. The stored request/message model can include source code, tool arguments, model responses, reasoning fields, and native provider payloads; optional raw capture adds more request/response material.
- `RunManifest` separates selected, completed, reused, failed, and waived coverage. Item identity is content-independent (operation/input mode/path); a separate diff fingerprint supports safe resume. Input commit SHAs and source artifact hashes are frozen in the manifest.
- Resume requires a parent manifest and only reuses parent completed/reused fingerprints; a stray checkpoint is not sufficient. Workspace resume is intentionally unsupported. Prompt compression is bounded in-memory state (frozen/summary/active zones), not durable semantic memory.
- Persistence is best-effort during a run: intermediate JSONL write/marshal failures are reported locally while execution can continue in memory; finalization has stronger explicit error handling. This is useful for resilience but should not be treated as evidence durability without an explicit fail-closed policy.

## agent/tool/subagent lifecycle

- `internal/agent/agent.go` constructs a per-review runner with a session, tool registry, comment collector, optional comment worker pool, token budget, and frozen input metadata. Each semantic group runs as a bounded subtask; panic isolation turns group panics into typed item failures.
- Plan mode is threshold-driven by changed-line count. A failed plan is a soft continuation into main review (`executeGroupSubtask`), which preserves availability but can silently reduce review depth unless the manifest records the skipped phase as a quality signal.
- `internal/llmloop/loop.go` caps tool requests, aggregate tokens, review rounds, and empty-result rounds. It records request/response/tool evidence, retries no-tool responses, and provides a final grace round limited to `code_comment` and `task_done` after a review limit.
- Comment post-processing can run asynchronously with `context.WithoutCancel`; the caller receives success before the worker completes. `internal/llmloop/pool.go` recovers worker panics and prints them, but worker errors/panics are not promoted to the review result. This is a hidden partial-failure path for line-level evidence.
- MCP stdio servers are launched with `exec.Command` (no shell) and remain alive until closed; remote MCP uses Streamable HTTP with configured headers. Tool catalogs are paginated, filtered by an allowlist when supplied, and registered only after reserved/duplicate checks. The configured command and remote URL remain powerful operator trust boundaries.

## local model and routing fit

- `internal/llm` has adapters for OpenAI chat completions, OpenAI Responses, Anthropic, and Anthropic Bedrock, with custom base URLs, retries, request timeouts, model overrides, and provider-specific auth. This is a useful protocol abstraction for a router-backed client.
- The resolver accepts explicit provider config, OCR config, environment, and shell-derived auth. URL validation is syntactic; `cmd/opencodereview/provider_cmd.go` checks only `http`/`https` plus a host. The code contains no Primus local router endpoint enforcement and no `11888` reference.
- Consequently, the default path can send source and prompts directly to a configured cloud or arbitrary HTTP endpoint. MCP remote URLs are similarly configurable in `internal/mcp/client.go`. This does not fit Primus local-only inference policy without an adapter/policy gate that forces requests through `http://127.0.0.1:11888`, handles explicit router cloud-handoff signals, and rejects bypass endpoints.
- `api_key_cmd`/`auth_token_cmd` support user-configured command execution with a timeout. This is reasonable for a trusted operator configuration, but it is not a sandbox and must never be agent-controlled or accepted from untrusted repository configuration.

## reliability/security/performance findings

- Strong path boundary: `internal/tool/filereader.go` resolves workspace paths against the canonical repository root and checks `WithinBase` before and after symlink resolution. Range/commit reads use `git show --end-of-options`; search uses bounded `git grep`/fallback paths with `--` pathspec separation. The reviewed built-in file tool does not provide an obvious `../` or symlink escape.
- Read/search limits are explicit: file tool output is capped at 500 lines, search at 100 matches, and search/git-sniff operations have short timeouts. However, the lower-level `FileReader.Read` can materialize whole files, so prompt/memory pressure still depends on caller and scan path. The default secret gate is path-based and intentionally narrow (env families, SSH keys, netrc/npm/pypirc/docker credentials); it is not content scanning or a general secret detector.
- Prompt injection is incompletely handled. `main_task_system.md`, `main_task_user.md`, `grouping_task_system.md`, and the scan template interpolate diffs, file contents, rules, and background into model context without a consistent explicit rule that repository content is untrusted data rather than instructions. The QCA prompt at `plugins/open-code-review/qca/system-prompt.md` does contain that defense, but it is not evidence that the core embedded prompts have it. This is the highest-risk review-harness gap.
- Endpoint security is also incomplete for a local-only deployment: arbitrary custom model URLs, HTTP (not only HTTPS), custom headers/body fields, and remote MCP endpoints are accepted by configuration. TLS verification is not disabled in the reviewed code, but transport integrity alone does not enforce local routing or prevent deliberate policy bypass.
- Session JSONL is permission-restricted and the viewer has a Host-header allowlist, loopback controls, path-segment validation, CSP, and security headers. The viewer serves source code and LLM analysis by design; `internal/viewer/store.go` reads session records without a clear size cap, so a large/attacker-controlled local session can create memory pressure.
- The latest commit correctly makes an empty `code_comment` batch an error instead of success. Remaining asynchronous worker failures can still produce success-shaped partial results. Plan failure is another intentional soft-failure path and should be visible in harness quality accounting.
- Git execution is comparatively disciplined: hard-coded Git subprocesses, context cancellation, bounded concurrency, and option terminators reduce command injection risk from diffs. The MCP stdio command and `api_key_cmd` are separate, explicit execution boundaries that require trusted configuration.
- Recent public commit activity is active (latest visible commits dated 2026-10-20); public benchmark claims in README were not independently reproduced. The advisory API result is an availability/permission uncertainty, not a clean bill of health.

## reusable patterns

- Make deterministic inventory and coverage the source of truth: pre-register the denominator, seal it before concurrency, use stable item IDs plus content fingerprints, and emit typed provider/timeout/cancel/budget/panic failures.
- Keep agent context isolated by semantic bundle while retaining a deterministic global manifest. This offers concurrency without letting one model context decide what was reviewed.
- Use a locator ladder: exact diff mapping, deterministic cross-file relocation, then an explicitly bounded model-assisted relocation. Store the final path/range and evidence separately from model prose.
- Expose tools with hard line/match/time limits, frozen registries, reserved names, JSON schemas, and structured tool-result records. Treat MCP as an extension boundary with explicit allowlists.
- Use rule precedence plus canonical effective-config hashing so a result can explain which policy produced it. Keep unconditional secret-path exclusions separate from review-noise exclusions.
- Persist append-only event history plus one immutable final manifest. Make resume depend on manifest-vouched completion rather than a single checkpoint line.
- Preserve provider-neutral adapter interfaces, but put the adapter behind the Primus router and propagate router metadata/handoff signals rather than selecting cloud/local backends inside review code.
- Make hostile review first-class: add a post-review adversarial pass that receives only bounded candidate evidence and diff context, can reject unsupported comments, and produces its own manifest item/failure state rather than silently mutating the primary result.

## rejected patterns

- Do not adopt the direct resolver/provider path unchanged for Primus: its arbitrary endpoint precedence and HTTP allowance bypass the local inference router.
- Do not rely on prompt wording alone when interpolating repository text, rules, or user background. Add explicit data/instruction separation, taint labels, delimiters, and tool-side scope checks; the QCA-only defense is insufficient.
- Do not let an agent choose the coverage denominator, mark a file complete, or decide that asynchronous comment work succeeded. Completion must be deterministic and fail closed on post-processing loss.
- Do not enable full conversation/raw capture by default in a harness handling source code. Gate it, redact it, cap it, and keep it out of normal user-visible evidence unless required.
- Do not treat path-based secret exclusions as comprehensive protection. Add configurable secret scanning or policy-deny behavior for sensitive content, while keeping false-positive handling explicit.
- Do not run configured shell credential helpers or MCP commands under repository/agent control. They belong to a trusted operator configuration with provenance and audit controls.

## exact evidence paths

- Provenance and threat model: `README.md`, `LICENSE`, `go.mod`, `ASSURANCE_CASE.md`, `.github/SECURITY.md`.
- Pipeline and grouping: `internal/agent/agent.go`, `internal/agent/grouping.go`, `internal/llmloop/loop.go`, `internal/llmloop/compression.go`, `internal/llmloop/pool.go`.
- Prompts/templates: `internal/config/template/task_template.json`, `internal/config/template/prompts/main_task_system.md`, `main_task_user.md`, `grouping_task_system.md`, `review_filter_task_system.md`, `internal/config/template/scan_template.json`.
- Rules/filters: `internal/config/rules/system_rules.go`, `internal/config/rules/sniffer.go`, `.opencodereview/rule.json`, `internal/config/allowlist/default_exclude_patterns.json`, `internal/config/allowlist/default_secret_patterns.json`, `internal/config/allowlist/secret_path.go`.
- Evidence tools and boundaries: `internal/tool/file_read.go`, `internal/tool/filereader.go`, `internal/tool/file_read_diff.go`, `internal/tool/file_find.go`, `internal/tool/code_search.go`, `internal/tool/code_comment.go`, `internal/tool/comment_collector.go`, `internal/pathutil/path.go`, `internal/gitcmd/runner.go`.
- State/resume/manifest: `internal/session/history.go`, `internal/session/persist.go`, `internal/session/manifest.go`, `internal/session/resume.go`.
- Models/routing: `internal/llm/resolver.go`, `internal/llm/client.go`, `internal/llm/responses_client.go`, `internal/llm/raw.go`, `internal/llm/keycmd.go`, `cmd/opencodereview/provider_cmd.go`.
- MCP and viewer: `internal/mcp/client.go`, `internal/mcp/provider.go`, `internal/viewer/hostguard.go`, `internal/viewer/server.go`, `internal/viewer/securityheaders.go`, `internal/viewer/store.go`.
- Existing injection-aware delegation prompt: `plugins/open-code-review/qca/system-prompt.md`; delegation shell-safety guidance: `skills/open-code-review-delegate/SKILL.md`.

## open uncertainties

- The checkout is shallow, so historical fixes, full release ancestry, and blame context were not available locally.
- The GitHub advisory endpoint returned 404; private advisories, unpublished issues, and endpoint permission behavior remain unknown.
- No build/tests/benchmark were run by design. README performance and precision claims are unverified here.
- Runtime behavior can change through user rule files, tool config, provider config, MCP server definitions, telemetry/raw-capture settings, and custom templates; this report covers checked-in defaults and the directly observed configuration surfaces.
- The exact acceptable Primus router contract, signed policy schema, and cloud-handoff header/error semantics must be supplied by the local runtime policy before implementation.

Recommendation: adapt - retain the deterministic manifest, bounded tools, line-evidence ladder, and protocol adapters, but route all model/MCP traffic through Primus policy and add explicit untrusted-content isolation plus fail-closed async/persistence accounting.
