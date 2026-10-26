# Research Evidence Snapshots

These files are bounded, static research snapshots copied from the Primus
research workspace into the canonical DeepHarness-RSI repository. They are
evidence for design decisions, not runtime dependencies and not claims of
production compatibility.

- Source workspace: `/usr/production/runtime/harness-research`.
- Source checkouts: `/linuxdata/Github` at the revisions recorded in
  `../RESEARCH-MANIFEST.json`.
- Scope: repository/document inspection only; no candidate repository was
  edited, built, installed, promoted, or used as a provider.
- Routing: substantive worker inference used the Primus local router at
  `http://127.0.0.1:11888`; cloud inference was disabled for the dispatch.
- The requested `deepseek/agent-harness` URL was verified unavailable. The
  public DeepSeek source used for evidence is
  `deepseek-ai/deepseek-harness`.
- Upstream HEAD observations are recorded separately in
  `20261026-upstream-head-refresh.md`; they do not change the analyzed
  revisions or authorize a pull into a dirty research checkout.

The parent repository is the only authoring location for DeepHarness-RSI.
Research clones remain read-only inputs. Pushes to the personal `origin`
remote require explicit operator approval.
