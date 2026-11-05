"""Shared canonical identity for reviewer packets and evidence pointers."""

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify_runtime_bundle(runtime_root: Path) -> None:
    """Verify every declared static review asset before it influences a gate."""
    root = Path(runtime_root).resolve()
    manifest_path = root / "review_runtime_bundle_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"review runtime bundle manifest is unavailable: {manifest_path}") from exc
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("artifacts"), list):
        raise RuntimeError("review runtime bundle manifest has an unsupported shape")
    for artifact in manifest["artifacts"]:
        if not isinstance(artifact, dict):
            raise RuntimeError("review runtime bundle manifest has a non-object artifact")
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
            raise RuntimeError("review runtime bundle manifest has an invalid artifact entry")
        parts = PurePosixPath(relative).parts
        if not parts or any(part in {"", ".", "..", "/"} for part in parts):
            raise RuntimeError(f"review runtime bundle artifact path is invalid: {relative}")
        candidate = root.joinpath(*parts)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise RuntimeError(
                f"review runtime bundle artifact escapes its root: {relative}"
            ) from exc
        if not resolved.is_file():
            raise RuntimeError(f"review runtime bundle artifact is unavailable: {relative}")
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"review runtime bundle artifact digest mismatch: {relative}")


def pointer_transport_status(pointer):
    required = ("memory_id", "content_sha256", "packet_sha256", "source_packet_sha256", "verified", "retention_verified", "purge_after_utc")
    if (any(pointer.get(field) in (None, "") for field in required)
            or pointer.get("verified") is not True
            or pointer.get("retention_verified") is not True):
        return "pointer=temporary_evidence_pointer;verified_fields=incomplete"
    return ("pointer=temporary_evidence_pointer;verified=true;retention=verified;"
            "authority=sole;fields=memory_id|content_sha256|packet_sha256|"
            "source_packet_sha256|purge_after_utc")


def packet_identity(packet):
    """Attach a stable identity while excluding only self-referential hashes."""
    provenance = packet["PROVENANCE"]
    pointer = provenance.get("temporary_evidence_pointer")
    if isinstance(pointer, dict):
        source_hash = str(pointer.get("source_packet_sha256") or pointer.get("packet_sha256") or "").strip()
        if source_hash:
            pointer["source_packet_sha256"] = source_hash
            pointer["source_packet_sha256_scope"] = "temporary_memory_record"
            pointer["packet_sha256_scope"] = "checker_normalized_envelope"
        provenance["temporary_evidence_pointer_status"] = pointer_transport_status(pointer)
        if pointer.get("verified") is True:
            provenance.setdefault("temporary_evidence_pointer_required", True)
            provenance.setdefault("review_field_integrity_scope", "temporary_memory_record_exact_bytes;lane_values_may_be_compact_previews")

    canonical = copy.deepcopy(packet)
    canonical["PROVENANCE"].pop("review_packet_hash", None)
    canonical_pointer = canonical["PROVENANCE"].get("temporary_evidence_pointer")
    if isinstance(canonical_pointer, dict):
        canonical_pointer.pop("review_packet_hash", None)
        source_hash = str(canonical_pointer.get("source_packet_sha256") or "").strip()
        if source_hash:
            canonical_pointer["packet_sha256"] = source_hash

    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    packet_id = str(provenance.get("review_packet_id") or "primus-checker-packet-" + digest(canonical)[:16])
    provenance["review_packet_id"] = packet_id
    canonical["PROVENANCE"]["review_packet_id"] = packet_id
    packet_hash = digest(canonical)
    provenance["review_packet_hash"] = packet_hash
    if isinstance(pointer, dict) and pointer.get("source_packet_sha256"):
        pointer["packet_sha256"] = packet_hash
        pointer["review_packet_hash"] = packet_hash
    return packet_id, packet_hash
