# DeepHarness-RSI

DeepHarness-RSI is a personal, public harness project in development. It is
initially based on research and code from the DeepSeek Harness ecosystem;
`RSI` means recursive self-improvement.

**This project is not production-ready and is not fully tested.** It is a
design and implementation workspace for people who want to adapt a harness to
their own systems. Do not install or activate it unchanged. Different hosts,
models, operating systems, transports, credentials, storage layers, and
security policies will require explicit configuration and testing.

## Purpose

The target design is a runner-neutral harness that can support two cooperating
systems without making either system a hidden dependency of the other. The
intended capabilities are:

- local-first inference through a policy-aware router;
- explicit, router-owned escalation when local inference reports that cloud
  reasoning is required;
- interchangeable runner adapters and model selection;
- shared skills, workflows, memory procedures, and review contracts;
- bounded evidence, durable provenance, and recoverable task state;
- adversarial review before code or policy promotion; and
- optional recursive self-improvement in an isolated, reviewable sandbox.

The two-system design is an architectural goal, not a claim that this public
repository currently works on any particular pair of hosts. Deployment
adapters, identity, network policy, model endpoints, secrets, and storage
locations must be supplied by the adopter.

## Current status

- Development only; APIs, directory layout, and runtime contracts may change.
- The DeepSeek Harness fork is the starting implementation substrate, not the
  finished DeepHarness-RSI product.
- Research is still being consolidated and functionality is being deduplicated
  rather than copied indiscriminately.
- Recursive self-improvement is not enabled by default and must not bypass
  review, isolation, authorization, or rollback requirements.
- No claim is made here that all listed integrations are complete or mutually
  compatible.

## Research and design sources

These repositories are being used as research inputs or implementation
references. Each is included for a specific reason; the project will retain
only the parts that survive compatibility, security, reliability, and
performance review.

| Repository | Role in the design |
| --- | --- |
| [furrepanther/deepseek-harness](https://github.com/furrepanther/deepseek-harness) | Initial harness substrate and the primary codebase being adapted into a personal fork. |
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | Upstream reference for the original harness concepts and evolution of the substrate. |
| [furrepanther/harness2](https://github.com/furrepanther/harness2) | Recursive harness design and self-improvement concepts; treated as experimental until independently validated. |
| [NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) | Self-evolution workflows, evaluation loops, and controlled improvement patterns. |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | Runner, tool, handoff, and agent-lifecycle patterns that may inform a runner-neutral adapter. |
| [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | Planning, delegation, subagent, and task decomposition patterns. |
| [bytedance/deer-flow](https://github.com/bytedance/deer-flow) | Long-running workflow, background execution, artifact, and human-in-the-loop ideas. |
| [ruvnet/ruflo](https://github.com/ruvnet/ruflo) | Multi-agent orchestration and coordination patterns to compare against simpler designs. |
| [alibaba/open-code-review](https://github.com/alibaba/open-code-review) | Automated code-review and quality-gate ideas, including independent validation before promotion. |
| [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) | Qwen-oriented tooling and model integration details relevant to the local model environment. |
| [furrepanther/codex](https://github.com/furrepanther/codex) | Codex UI and interaction patterns selected as the planned user-interface baseline. |
| [furrepanther/SimpleMem](https://github.com/furrepanther/SimpleMem) | Memory-fabric integration, semantic retrieval, durable records, and pointer-based context handling. |
| [rohitg00/agentmemory](https://github.com/rohitg00/agentmemory) | Agent memory storage patterns for comparison with the memory-fabric design. |
| [tursodatabase/agentfs](https://github.com/tursodatabase/agentfs) | Agent-oriented filesystem and SQLite storage concepts; beta software reserved for late, isolated evaluation. |
| [sunblaze-ucb/exploitgym](https://github.com/sunblaze-ucb/exploitgym) | Future post-review security and exploit-resistance research; not a production dependency. |

The local two-system environment also supplies non-GitHub contracts and
services, especially the inference router, Agent Mail, Memory Fabric, shared
skills, and adversarial review workflow. Those are integration dependencies,
not copied source, and must be represented by explicit adapters and contract
tests.

## Operating principles

1. Prefer local inference and local resources. Cloud use is an explicit router
   handoff, never a silent backend bypass.
2. Treat cross-system communication, shared memory, and model selection as
   versioned contracts with health checks and provenance.
3. Keep experimental self-improvement isolated from the production harness;
   require evidence, review, and an explicit promotion decision.
4. Use task-scoped, byte- and line-capped evidence. Do not treat elapsed time
   alone as proof that a job is hung or safe to terminate.
5. Test on the adopter's actual hardware, operating system, model runtime,
   credentials, and network policy before enabling any operational path.
6. Preserve upstream licenses and notices when adapting code, and document
   material changes in the fork.

## Adaptation checklist

Before use on another system, an adopter should at minimum:

- configure and verify local inference endpoints and model capabilities;
- define runner, user, filesystem, secret, and transport boundaries;
- map the local memory and artifact stores without assuming shared database
  files;
- run unit, integration, failure-recovery, concurrency, and adversarial tests;
- verify cloud handoff behavior independently from local-only behavior;
- inspect resource limits and tune concurrency for the actual hardware; and
- review every promotion, self-modification, and cross-host authorization
  decision.

## License and provenance

This repository is a personal project. Its eventual license and any bundled
code will be documented before release of reusable implementation code.
Upstream projects remain subject to their own licenses and notices. Research
references do not imply endorsement, compatibility, or code reuse.
