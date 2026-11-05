# Portable review runtime bundle

This directory is the source-controlled dependency bundle for the local-only
review wrapper. It replaces the former non-Git dependency on a host runtime
directory. Validate every digest in `review_runtime_bundle_manifest.json`
before using it as `PRIMUS_REVIEW_RUNTIME_ROOT`.

The wrapper itself remains in `tools/`. Use the bundle only with the wrapper's
explicit `--local` mode and WSL-native temporary state. Shared reviewer cards
use `shared-github://` identifiers and resolve through either host's canonical
GitHub view (`/mnt/linuxdata/Github` on Datacube or `/linuxdata/Github` on
Primus). A missing enabled card is an error, never a silent empty profile.
