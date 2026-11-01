# Staged checker candidate

`primus-adversarial-code-checker`, `primus_inference_mode.py`, and
`review_packet_identity.py` were copied from the personal Qwen-Harness-AG
checker worktree at commit `8c27b8b`. They are being reconciled into
DeepHarness-RSI and are not the deployed Primus or Datacube checker. The
candidate retains Primus-specific paths and requires `jsonschema` at runtime;
its integration, portable configuration, dependencies, and complete review
remain open.

The staged evidence gate rejects a no-block result when the reviewer reports
inaccessible, missing, partial, or truncated material, or fails to attest both
implementation and test material using the unique section IDs `DIFF_OR_FILES`
and `TESTS`. Packet presence alone no longer scaffolds a fully-reviewed status,
and an explicit reviewer block is not downgraded to no-block. A model's
attestation is not independent proof of
reviewer access: pointer retrieval, content delivery and receipt still need
their own verified transport contract before promotion. The checker does not
replace the existing review wrapper or establish a complete review gate.

Custom output schemas validate the normalized result; they cannot bypass the
evidence or route policy. Schemas requiring a raw-model-only shape fail closed
until adapted to the normalized output contract.
