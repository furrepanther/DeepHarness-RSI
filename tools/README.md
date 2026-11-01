# Staged checker candidate

`primus-adversarial-code-checker`, `primus_inference_mode.py`, and
`review_packet_identity.py` were copied from the personal Qwen-Harness-AG
checker worktree at commit `8c27b8b`. They are being reconciled into
DeepHarness-RSI and are not the deployed Primus or Datacube checker. The
candidate retains Primus-specific paths and requires `jsonschema` at runtime;
its integration, portable configuration, dependencies, and complete review
remain open.

The general review wrapper and Grumpy launcher are also staged from that
personal worktree. A structured router cloud-required response stops the
staged wrapper with exit code 16 and a `codex_handoff` result, before any
context retry or later lane. It does not invoke cloud inference; a parent must
handle the result. Full wrapper integration and receipt verification remain
unreviewed and are not production-ready.

The staged evidence gate rejects a no-block result when the reviewer reports
inaccessible, missing, partial, or truncated material, or fails to attest both
implementation and test material using the unique section IDs `DIFF_OR_FILES`
and `TESTS`. Packet presence alone no longer scaffolds a fully-reviewed status,
and an explicit reviewer block is not downgraded to no-block. A model's
attestation is not independent proof of
reviewer access: pointer retrieval, content delivery and receipt still need
their own verified transport contract before promotion. The checker does not
replace the existing review wrapper or establish a complete review gate.
Until a trusted receipt verifier is integrated, the CLI has no path to assert
verified receipt and therefore returns `insufficient_evidence` for any
otherwise no-block result. Explicit blocks remain blocks.

Custom output schemas validate the normalized result; they cannot bypass the
evidence or route policy. Schemas requiring a raw-model-only shape fail closed
until adapted to the normalized output contract.

Router length-recovery responses are not accepted as verified review routes:
the final generation may have used a different prompt, and the initial request
hash does not attest its evidence. This guard does not itself prove receipt for
ordinary responses.

The staged checker sends inference only to the loopback router. Direct cloud
mode is rejected by the shared launcher-mode helper, including when inherited
from the environment, and the retired caller-side fallback is rejected. A
router-provided cloud-required response remains visible as a handoff signal in the error
artifact; this candidate does not itself execute that handoff.
