# DeepHarness-RSI Implementation Roadmap

Status: research complete; engineering and production promotion remain gated.

Every checkpoint is empty-boat: no warnings, errors, stale provenance,
unknown ownership, direct-provider route, missing receipt, or unresolved
adversarial finding may pass.

## Gate 1 - Freeze contracts

- Define the runner-neutral task, policy, capability, lease, receipt, and
  evidence schemas.
- Prove that child policy is an intersection of the parent policy and cannot
  widen tools, namespaces, network, concurrency, depth, or expiry.
- Add static rejection tests for direct provider calls, hidden cloud routes,
  unbounded reads, and duration-only termination.

## Gate 2 - Admission and execution ledger

- Implement immutable task identity, idempotency keys, leases, fencing,
  heartbeat evidence, and terminal-state ownership.
- Test duplicate delivery, cancellation, restart, stale lease, replay safety,
  model/schema mismatch, and partial settlement.
- Use task-scoped progress and terminal evidence; elapsed duration is telemetry,
  never the kill condition.

## Gate 3 - Evidence and temporary storage

- Implement one compact complete evidence packet plus a verified temporary
  pointer for overflow.
- Use explicit byte, line, record, and retention bounds; never read whole logs
  or split structured entries into sequential fragments.
- Test missing, stale, over-cap, out-of-order, digest-mismatched, and partially
  purged pointers. Clean up by exact ID only after lineage and active-reader
  checks.

## Gate 4 - Universal runners and skills

- Provide one runner-neutral skill/workflow contract for Codex, Claude,
  Gemini, Cline, Qwen Code, Qwen-Harness-AG, and future runners.
- Prove shared registry accessibility and identical policy interpretation on
  both cooperating systems.
- Keep runner-specific behavior in thin adapters; do not fork the contract.

## Gate 5 - Router, classifier, and model modes

- Implement the local-router adapter first, then deterministic prompt/intent
  classification and model-mode selection behind it.
- Test the DavidAU mode/help matrix, dynamic reasoning shifts, context budgets,
  retries, local-only behavior, and explicit cloud-handoff behavior.
- Keep model-specific tuning inside the adapter/policy layer. Do not permit a
  runner to select a direct provider or silently bypass the router.

## Gate 6 - Harness2 recursive supervisor

- Evaluate recursive proposal/probe/compose behavior in an isolated sandbox.
- Require immutable parent policy, bounded recursion, evidence-backed changes,
  Red-Team-Gate, Solid Snake, SDLC, security, performance, and rollback proof.
- Never allow generated code or policy to self-promote.

## Gate 7 - Integration and promotion

- Run selective unit, integration, failure-injection, concurrency, Nebula,
  and two-system canary tests against the actual hardware and router.
- Verify recovery from process loss, transport loss, partial writes, stale
  claims, and peer restart.
- Promote only with complete receipts, manifests, rollback proof, and an
  independent adversarial review whose final state is empty-boat.

## Cleanup at every gate

At the end of each gate, remove or archive only truly temporary artifacts by
exact validated identity. Scratch belongs in the host temporary review area;
durable design decisions belong in this repository and Memory Fabric; durable
system backups belong in their approved backup location. No scratch or raw
telemetry is committed as a substitute for provenance.
