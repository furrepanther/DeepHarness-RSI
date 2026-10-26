# Provenance and Backup Contract

This file defines what the DeepHarness-RSI repository backs up and how to
recover it. It is intentionally public-safe: it contains no credentials,
tokens, prompts, hidden reasoning, raw logs, or private host configuration.

## Canonical records

- `furrepanther/DeepHarness-RSI` is the public, cloud-backed record for the
  DeepHarness-RSI design, durable research findings, implementation roadmap,
  and future integrated harness source.
- The local checkout of that repository is the canonical working copy for
  those files. Changes are committed locally first; a push to the personal
  `origin` remote is a separate operator-controlled backup/release action.
- All implementation work for this harness is conducted in this checkout or
  its personal-fork worktree. Production trees and upstream research clones
  are inputs or deployment targets, not alternate authoring locations.
- The personal `furrepanther/deepseek-harness` fork remains the backup and
  source lineage for the initial DeepSeek substrate. It is not silently
  replaced by an upstream checkout and is not modified through this repository
  without a separate reviewed change.
- Operational databases, secrets, raw diagnostics, temporary review packets,
  and host recovery archives have separate owners and backup policies. They
  are not copied into this public code repository.

## What is currently backed up here

- the project identity, status, and research source list in `README.md`;
- the synthesized Primus-native architecture in `docs/ARCHITECTURE.md`;
- the comparative adopt/adapt/reject decisions in
  `docs/RESEARCH-DECISIONS.md`;
- the pinned source and license provenance in
  `docs/RESEARCH-MANIFEST.json`; and
- the gated implementation sequence in `docs/IMPLEMENTATION-ROADMAP.md`.

The repository currently contains design and research artifacts, not a claim
that a production runtime has been implemented. When code is added, its
source revision, tests, review receipt, and rollback target must be recorded
in this provenance file or a linked release record.

## Backup procedure

1. Keep edits in the personal fork or this personal repository; never edit an
   upstream research repository for local needs.
2. Review the exact diff and preserve unrelated dirty work. Do not use a hard
   reset or force overwrite to make a checkout appear clean.
3. Run the repository's applicable tests and the local adversarial review
   before promotion. A green structural check is not a promotion decision.
4. Commit durable source and findings with a specific message.
5. Push the commit to the personal GitHub `origin` only after the operator
   explicitly requests or approves that push, then verify the remote commit
   ID. The push is the cloud backup proof.
6. For release-worthy code, add a signed or otherwise verified tag and a
   checksum manifest after the review gate is empty-boat.

## Recovery procedure

Clone the public repository, verify the expected remote and commit, inspect
the provenance and roadmap, then restore any separate operational data from
its own verified backup. Do not infer that a code repository contains memory
databases, credentials, model files, or runtime state.

## Current boundary

No runtime source was copied into this repository during the research phase.
That is deliberate: the source substrate remains in its personal fork until
the first DeepHarness-RSI integration slice has a defined ownership boundary,
tests, review packet, and rollback plan. This repository is nevertheless the
authoritative backup for the durable design and research work already done.
