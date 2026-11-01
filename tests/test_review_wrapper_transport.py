"""Regression tests for the verified review-evidence pointer contract."""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
STAGED_ROOT = Path(__file__).resolve().parent
WRAPPER_CANDIDATES = (
    ROOT / "tools" / "primus-general-code-review",
    ROOT / "primus-general-code-review",
    STAGED_ROOT / "primus-general-code-review",
)
WRAPPER = next((candidate for candidate in WRAPPER_CANDIDATES if candidate.is_file()), WRAPPER_CANDIDATES[0])


def load_wrapper():
    tools_root = str(WRAPPER.parent)
    if tools_root not in sys.path:
        sys.path.insert(0, tools_root)
    production_root = "/usr/production"
    if production_root not in sys.path:
        sys.path.append(production_root)
    loader = SourceFileLoader("primus_general_code_review", str(WRAPPER))
    spec = spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"cannot create review-wrapper spec: {WRAPPER}")
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_checker():
    tools_root = str(ROOT / "tools")
    if tools_root not in sys.path:
        sys.path.insert(0, tools_root)
    loader = SourceFileLoader("primus_adversarial_code_checker", str(ROOT / "tools" / "primus-adversarial-code-checker"))
    spec = spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("cannot create checker spec")
    module = module_from_spec(spec)
    loader.exec_module(module)
    return module


def pointer() -> dict[str, object]:
    return {
        "memory_id": "12345678-1234-1234-1234-123456789012",
        "entry_id": "entry-1",
        "record_kind": "temporary_review_evidence",
        "verified": True,
        "canonical": False,
        "retention_verified": True,
        "content_sha256": "a" * 64,
        "packet_sha256": "b" * 64,
        "source_packet_sha256": "b" * 64,
        "purge_after_utc": "2026-11-01T00:00:00Z",
    }


class ReviewWrapperTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper = load_wrapper()
        cls.checker = load_checker()

    def test_cloud_handoff_stops_context_retry_and_writes_typed_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.json"
            output = root / "result.json"
            error = {"error_type": "cloud_fallback_required", "router_action": "codex_handoff", "message": "context size exceeded"}
            raw.write_text(json.dumps(error))
            proc = subprocess.CompletedProcess(["checker"], 10, stdout="", stderr=json.dumps(error))
            self.assertFalse(self.wrapper.is_context_failure(proc, raw))
            self.assertTrue(self.wrapper.write_cloud_handoff(proc, raw, output, "lane-one"))
            result = json.loads(output.read_text())
            self.assertEqual(result["status"], "cloud_required")
            self.assertEqual(result["router_action"], "codex_handoff")
            self.assertEqual(result["lane_id"], "lane-one")

    def test_genuine_context_failure_remains_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = subprocess.CompletedProcess(["checker"], 10, stdout="", stderr="context size exceeded")
            self.assertTrue(self.wrapper.is_context_failure(proc, Path(directory) / "missing"))

    def test_oversized_error_is_not_retried_as_context_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = subprocess.CompletedProcess(["checker"], 10, stdout="", stderr="context size exceeded" + "x" * 65536)
            self.assertFalse(self.wrapper.is_context_failure(proc, Path(directory) / "missing"))

    def test_review_launchers_reject_explicit_and_inherited_cloud_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launchers = [
                (ROOT / "tools" / "primus-general-code-review", ["--input", str(root / "missing"), "--output", str(root / "out"), "--raw-dir", str(root / "raw")]),
                (ROOT / "tools" / "primus-grumpy-reviewer", ["--input", str(root / "missing")]),
            ]
            for launcher, args in launchers:
                for explicit in (True, False):
                    with self.subTest(launcher=launcher.name, explicit=explicit):
                        env = dict(os.environ, PRIMUS_INFERENCE_MODE="local" if explicit else "cloud")
                        cmd = [sys.executable, str(launcher), *args, *(["--cloud"] if explicit else [])]
                        result = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("must be local for review workers", result.stderr)
                        self.assertFalse((root / "out").exists())

    def test_legacy_structured_handoff_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw.json"
            raw.write_text(json.dumps({"headers": {"X-Primus-Route": "cloud_required"}}))
            proc = subprocess.CompletedProcess(["checker"], 10, stdout="", stderr="")
            self.assertTrue(self.wrapper.cloud_handoff_required(proc, raw))

    def test_wrapper_stops_all_lanes_on_router_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path, config_path, output_path = root / "packet.json", root / "config.json", root / "result.json"
            packet_path.write_text(json.dumps(self.packet()))
            config_path.write_text("{}")
            error = {"error_type": "cloud_fallback_required", "router_action": "codex_handoff", "message": "context size exceeded"}
            proc = subprocess.CompletedProcess(["fake-checker"], 10, stdout="", stderr=json.dumps(error))
            argv = ["wrapper", "--local", "--disable-auto-superpowers", "--input", str(packet_path), "--config", str(config_path), "--output", str(output_path), "--raw-dir", str(root / "raw")]
            with patch.object(sys, "argv", argv), \
                 patch.object(self.wrapper, "ensure_temporary_evidence_pointer", side_effect=lambda packet, budget: packet), \
                 patch.object(self.wrapper, "base_prompt_for_config", return_value=root / "prompt"), \
                 patch.object(self.wrapper, "sdlc_lanes", return_value=[{"id": "first"}, {"id": "second"}]), \
                 patch.object(self.wrapper, "lane_packets_for_budget", side_effect=lambda packet, *args, **kwargs: [packet]), \
                 patch.object(self.wrapper, "checker_user_content_chars", return_value=1), \
                 patch.object(self.wrapper, "verify_checker_payload"), \
                 patch.object(self.wrapper, "lane_command", return_value=["fake-checker"]), \
                 patch.object(self.wrapper, "child_mode_args", return_value=[]), \
                 patch.object(self.wrapper.subprocess, "run", return_value=proc) as run:
                self.assertEqual(self.wrapper.main(), 16)
            self.assertEqual(run.call_count, 1)
            result = json.loads(output_path.read_text())
            self.assertEqual(result["router_action"], "codex_handoff")
            self.assertEqual(json.loads(Path(result["diagnostic_path"]).read_text())["error_type"], "cloud_fallback_required")

    def packet(self) -> dict[str, object]:
        current = pointer()
        return {
            "TASK": "transport regression",
            "ACCEPTANCE_CRITERIA": "pointer survives normalization",
            "DIFF_OR_FILES": "review evidence",
            "TESTS": "pass",
            "KNOWN_CONSTRAINTS": "local only",
            "OUT_OF_SCOPE": "runtime changes",
            "PROVENANCE": {
                "provenance_verified": True,
                "complete_packet": True,
                "repo_or_scope": "review-wrapper-transport",
                "base_revision": "d" * 40,
                "artifact_refs": ["tools/primus-general-code-review"],
                "gate_state": "production_gate=separate_authority; full_artifacts=pointer_backed",
                "evidence_compaction": {"prior": "metadata"},
                "review_field_integrity": {
                    "ACCEPTANCE_CRITERIA": {
                        "complete": True,
                        "chars": 30,
                        "sha256": "aab07ab36f33edc794150575fd719ae905553fc7e68ec8dbb323547d508cf56c",
                    },
                    "DIFF_OR_FILES": {
                        "complete": True,
                        "chars": 15,
                        "sha256": "db87a7f561833951e5044f3cdc91a599e2f13687661eabfdbb7016a7e5dd0577",
                    },
                    "TESTS": {
                        "complete": True,
                        "chars": 4,
                        "sha256": "d74ff0ee8da3b9806b18c877dbf29bbde50b5bd8e4dad7a3a725000feb82e8f1",
                    },
                },
                "full_artifacts_transport": {
                    "transport": "pointer_backed_complete_bytes",
                    "complete_bytes_stored": True,
                    "inline_bytes_in_lane": False,
                },
                "temporary_evidence_pointer": current,
            },
        }

    def test_normalization_keeps_one_authoritative_pointer(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        provenance = normalized["PROVENANCE"]
        transport = provenance["full_artifacts_transport"]
        current = provenance["temporary_evidence_pointer"]
        self.assertEqual(current["source_packet_sha256"], "b" * 64)
        self.assertNotEqual(current["packet_sha256"], current["source_packet_sha256"])
        self.assertTrue(current["retention_verified"])
        self.assertNotIn("verified_temporary_evidence_pointer", transport)
        self.assertEqual(
            set(transport),
            {"transport", "complete_bytes_stored", "inline_bytes_in_lane"},
        )

    def test_verified_pointer_contract_asserts_all_authoritative_fields(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        current = normalized["PROVENANCE"]["temporary_evidence_pointer"]
        for field in (
            "memory_id",
            "content_sha256",
            "packet_sha256",
            "source_packet_sha256",
            "verified",
            "retention_verified",
            "purge_after_utc",
        ):
            self.assertIn(field, current)
        self.assertEqual(current["memory_id"], "12345678-1234-1234-1234-123456789012")
        self.assertEqual(current["content_sha256"], "a" * 64)
        self.assertEqual(current["source_packet_sha256"], "b" * 64)
        self.assertTrue(current["verified"])
        self.assertTrue(current["retention_verified"])
        self.assertEqual(current["purge_after_utc"], "2026-11-01T00:00:00Z")

    def test_pointer_status_does_not_report_unverified_retention_as_verified(self) -> None:
        value = pointer()
        value["retention_verified"] = False
        self.assertEqual(self.wrapper.pointer_transport_status(value), "pointer=temporary_evidence_pointer;verified_fields=incomplete")
        packet = self.packet()
        packet["PROVENANCE"]["temporary_evidence_pointer"] = value
        packet["PROVENANCE"]["temporary_evidence_pointer_status"] = "verified=true;retention=verified"
        normalized, _, _ = self.wrapper.checker_normalized_packet(packet)
        self.assertEqual(normalized["PROVENANCE"]["temporary_evidence_pointer_status"], "pointer=temporary_evidence_pointer;verified_fields=incomplete")

    def test_grumpy_packet_preserves_tests_and_exposes_lane_coverage(self) -> None:
        lanes = [
            {
                "lane_id": "lane-a",
                "dimension": "adversarial",
                "status": "ok",
                "decision": "no_blocking_defect_found",
                "blocking_findings": 0,
                "repair": {"attempts": 0, "final_status": "not_needed"},
            },
            {
                "lane_id": "lane-b",
                "dimension": "testing",
                "status": "ok",
                "decision": "no_blocking_defect_found",
                "blocking_findings": 0,
                "repair": {"attempts": 0, "final_status": "not_needed"},
            },
        ]
        grumpy_packet = self.wrapper.build_grumpy_packet(
            self.packet(),
            lanes,
            7000,
            7000,
            7000,
        )
        self.assertEqual(grumpy_packet["TESTS"], self.packet()["TESTS"])
        coverage = grumpy_packet["SDLC_REVIEW_EVIDENCE"]["coverage"]
        self.assertEqual(coverage["completed_lanes"], ["lane-a", "lane-b"])
        self.assertEqual(coverage["failed_lanes"], [])
        checker_packet = self.checker.normalize_input(grumpy_packet, Path("fixture"))
        self.assertEqual(checker_packet["SDLC_REVIEW_EVIDENCE"], grumpy_packet["SDLC_REVIEW_EVIDENCE"])
        content = json.loads(self.checker.build_user_content(checker_packet, "fixture", "fixture"))
        self.assertEqual(content["review_packet"]["SDLC_REVIEW_EVIDENCE"], grumpy_packet["SDLC_REVIEW_EVIDENCE"])

    def test_verified_pointer_gets_explicit_lane_status(self) -> None:
        packet = self.packet()
        packet["PROVENANCE"]["require_temporary_evidence_pointer"] = True
        with patch.object(self.wrapper, "verify_temporary_evidence_pointer"):
            prepared = self.wrapper.ensure_temporary_evidence_pointer(packet, 7000)
        status = prepared["PROVENANCE"]["temporary_evidence_pointer_status"]
        self.assertIn("pointer=temporary_evidence_pointer", status)
        self.assertIn("verified=true", status)
        self.assertIn("authority=sole", status)

    def test_verified_packet_preserves_missing_pointer_claim(self) -> None:
        packet, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        result = {
            "merge_decision": {"decision": "block", "reason": "pointer missing"},
            "findings": [
                {
                    "id": "F1",
                    "severity": "Critical",
                    "blocking": True,
                    "location": "PROVENANCE",
                    "observed_evidence": "temporary_evidence_pointer is absent",
                    "required_fix": "Add the verified pointer",
                }
            ],
        }
        reconciled, records = self.wrapper.reconcile_verified_packet_findings(result, packet)
        self.assertIsNotNone(reconciled)
        assert reconciled is not None
        self.assertEqual(reconciled, result)
        self.assertEqual(records, [])

    def test_verified_packet_preserves_missing_tests_claim(self) -> None:
        packet, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        result = {
            "merge_decision": {"decision": "block", "reason": "required field absent"},
            "findings": [
                {
                    "id": "F1",
                    "severity": "High",
                    "blocking": True,
                    "location": "review_packet.TESTS",
                    "observed_evidence": "TESTS key is not present",
                    "required_fix": "Add the TESTS field",
                }
            ],
        }
        reconciled, records = self.wrapper.reconcile_verified_packet_findings(result, packet)
        self.assertIsNotNone(reconciled)
        assert reconciled is not None
        self.assertEqual(reconciled, result)
        self.assertEqual(records, [])

    def test_verified_pointer_does_not_reconcile_source_visibility_claim(self) -> None:
        packet, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        result = {
            "merge_decision": {"decision": "no_blocking_defect_found"},
            "findings": [
                {
                    "id": "F1",
                    "severity": "Medium",
                    "blocking": False,
                    "location": "tools/primus-general-code-review",
                    "observed_evidence": "The packet provides no code or test evidence",
                    "required_fix": "Provide code or test evidence",
                }
            ],
        }
        reconciled, records = self.wrapper.reconcile_verified_packet_findings(result, packet)
        self.assertIsNotNone(reconciled)
        assert reconciled is not None
        self.assertEqual(reconciled["findings"], result["findings"])
        self.assertEqual(records, [])

    def test_verified_pointer_does_not_remove_blocking_source_visibility_claim(self) -> None:
        packet, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        result = {
            "merge_decision": {"decision": "block", "reason": "source not visible"},
            "findings": [{
                "severity": "High", "blocking": True, "location": "fixture.py",
                "observed_evidence": "The packet provides no source evidence",
                "required_fix": "Provide actual source bytes inline",
            }],
        }
        reconciled, records = self.wrapper.reconcile_verified_packet_findings(result, packet)
        self.assertEqual(reconciled, result)
        self.assertEqual(records, [])

    def test_pointer_mention_does_not_hide_missing_source(self) -> None:
        packet, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        result = {
            "merge_decision": {"decision": "block", "reason": "source not visible"},
            "findings": [{
                "severity": "High", "blocking": True, "location": "fixture.py",
                "observed_evidence": "temporary_evidence_pointer exists but no source evidence is visible",
                "required_fix": "Provide actual source bytes inline",
            }],
        }
        reconciled, records = self.wrapper.reconcile_verified_packet_findings(result, packet)
        self.assertEqual(reconciled, result)
        self.assertEqual(records, [])
        self.assertEqual(self.wrapper.targeted_repair_reason(result, "", packet, 0), "")

    def test_reviewer_prompts_do_not_equate_a_pointer_with_visible_source(self) -> None:
        contract = " ".join(self.wrapper.POINTER_TRANSPORT_PRECEDENCE_CONTRACT.split())
        self.assertIn("does not prove", contract)
        self.assertIn("insufficient evidence", contract)
        with tempfile.TemporaryDirectory() as directory:
            prompt = " ".join(self.wrapper.write_compact_grumpy_prompt(Path(directory)).read_text().split())
        self.assertIn("does not establish", prompt)
        self.assertIn("insufficient evidence", prompt)

    def test_visible_section_guard_rejects_each_modified_required_field(self) -> None:
        source = self.packet()
        self.wrapper.require_visible_review_sections(source, source)
        for field in ("TASK", "ACCEPTANCE_CRITERIA", "DIFF_OR_FILES", "TESTS", "KNOWN_CONSTRAINTS", "OUT_OF_SCOPE"):
            with self.subTest(field=field):
                candidate = dict(source)
                candidate[field] = "sha256=fixture; head=partial"
                with self.assertRaisesRegex(ValueError, field):
                    self.wrapper.require_visible_review_sections(source, candidate)

    def test_grumpy_required_sections_reach_checker_user_content_unchanged(self) -> None:
        original = self.packet()
        lanes = [{"lane_id": "lane-a", "status": "ok", "decision": "no_blocking_defect_found"}]
        emitted = self.wrapper.build_grumpy_packet(original, lanes, 7000, 7000, 7000)
        emitted = self.wrapper.fit_grumpy_packet_to_budget(emitted, 12000)
        self.wrapper.require_visible_review_sections(original, emitted)
        checker_packet = self.checker.normalize_input(emitted, Path("fixture"))
        content = json.loads(self.checker.build_user_content(checker_packet, "fixture", "fixture"))
        for field in ("TASK", "ACCEPTANCE_CRITERIA", "DIFF_OR_FILES", "TESTS", "KNOWN_CONSTRAINTS", "OUT_OF_SCOPE"):
            with self.subTest(field=field):
                self.assertEqual(content["review_packet"][field], original[field])
        self.assertEqual(content["review_packet"]["SDLC_REVIEW_EVIDENCE"], emitted["SDLC_REVIEW_EVIDENCE"])

    def test_selected_checker_probe_accepts_candidate_and_rejects_legacy(self) -> None:
        packet = self.packet()
        packet["PROVENANCE"].pop("temporary_evidence_pointer")
        packet["SDLC_REVIEW_EVIDENCE"] = {"coverage": {"completed_lanes": ["lane-a"]}}
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(packet))
            self.wrapper.verify_checker_payload(ROOT / "tools" / "primus-adversarial-code-checker", packet_path, packet)
            env = {**os.environ, "PRIMUS_REVIEW_CHECKER": str(ROOT / "tools" / "primus-adversarial-code-checker")}
            self.wrapper.verify_checker_payload(ROOT / "tools" / "primus-grumpy-reviewer", packet_path, packet, env=env)
            modified = dict(packet)
            modified["TESTS"] = "changed after packet was written"
            with self.assertRaisesRegex(ValueError, "changes reviewer-visible evidence"):
                self.wrapper.verify_checker_payload(ROOT / "tools" / "primus-adversarial-code-checker", packet_path, modified)
            modified = dict(packet)
            modified["PROVENANCE"] = {**packet["PROVENANCE"], "provenance_verified": False}
            with self.assertRaisesRegex(ValueError, "changes reviewer-visible evidence"):
                self.wrapper.verify_checker_payload(ROOT / "tools" / "primus-adversarial-code-checker", packet_path, modified)
            legacy = Path(directory) / "legacy-checker"
            legacy.write_text('#!/bin/sh\nprintf "{}\\n"\n')
            legacy.chmod(0o700)
            with self.assertRaisesRegex(ValueError, "changes reviewer-visible evidence"):
                self.wrapper.verify_checker_payload(legacy, packet_path, packet)

    def test_pointer_packet_identity_matches_checker_and_is_stable(self) -> None:
        packet, packet_id, packet_hash = self.wrapper.checker_normalized_packet(self.packet())
        normalized_again, next_id, next_hash = self.wrapper.checker_normalized_packet(packet)
        self.assertEqual((next_id, next_hash), (packet_id, packet_hash))
        self.assertEqual(normalized_again, packet)
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            packet_path.write_text(json.dumps(packet))
            self.wrapper.verify_checker_payload(ROOT / "tools" / "primus-adversarial-code-checker", packet_path, packet)
            changed = json.loads(json.dumps(packet))
            changed["PROVENANCE"]["temporary_evidence_pointer"]["source_packet_sha256"] = "c" * 64
            with self.assertRaisesRegex(ValueError, "changes reviewer-visible evidence"):
                self.wrapper.verify_checker_payload(ROOT / "tools" / "primus-adversarial-code-checker", packet_path, changed)

    def test_packet_identity_binds_review_sections_and_pointer_source(self) -> None:
        packet = self.packet()
        packet["SDLC_REVIEW_EVIDENCE"] = {"lanes": [{"lane_id": "lane-a", "decision": "block"}]}
        normalized, _, original_hash = self.wrapper.checker_normalized_packet(packet)
        mutations = {
            "TASK": lambda value: value + " changed",
            "ACCEPTANCE_CRITERIA": lambda value: value + " changed",
            "DIFF_OR_FILES": lambda value: value + " changed",
            "TESTS": lambda value: value + " changed",
            "KNOWN_CONSTRAINTS": lambda value: value + " changed",
            "OUT_OF_SCOPE": lambda value: value + " changed",
            "SDLC_REVIEW_EVIDENCE": lambda value: {"lanes": [{"lane_id": "lane-a", "decision": "pass"}]},
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                changed = json.loads(json.dumps(normalized))
                changed[field] = mutate(changed[field])
                self.assertNotEqual(self.wrapper.checker_normalized_packet(changed)[2], original_hash)
        changed = json.loads(json.dumps(normalized))
        changed["PROVENANCE"]["temporary_evidence_pointer"]["source_packet_sha256"] = "c" * 64
        self.assertNotEqual(self.wrapper.checker_normalized_packet(changed)[2], original_hash)

    def test_verified_packet_keeps_substantive_nonblocking_finding(self) -> None:
        packet, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        result = {
            "merge_decision": {"decision": "no_blocking_defect_found"},
            "findings": [
                {
                    "id": "F1",
                    "severity": "Medium",
                    "blocking": False,
                    "location": "tools/primus-general-code-review",
                    "observed_evidence": "A race can lose an update",
                    "required_fix": "Serialize the shared state update",
                }
            ],
        }
        reconciled, records = self.wrapper.reconcile_verified_packet_findings(result, packet)
        self.assertEqual(records, [])
        self.assertEqual(reconciled["findings"], result["findings"])

    def test_changed_source_contracts_are_explicitly_asserted(self) -> None:
        changed_sources = {
            "wrapper": ROOT / "tools" / "primus-general-code-review",
            "grumpy": ROOT / "tools" / "primus-grumpy-reviewer",
            "checker": ROOT / "tools" / "primus-adversarial-code-checker",
            "mode_helper": ROOT / "tools" / "primus_inference_mode.py",
            "tests": Path(__file__),
        }
        for label, path in changed_sources.items():
            self.assertTrue(path.is_file(), f"missing changed source: {label}: {path}")
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.strip(), f"empty changed source: {label}: {path}")
        wrapper_source = changed_sources["wrapper"].read_text(encoding="utf-8")
        checker_source = changed_sources["checker"].read_text(encoding="utf-8")
        grumpy_source = changed_sources["grumpy"].read_text(encoding="utf-8")
        test_source = changed_sources["tests"].read_text(encoding="utf-8")
        for marker in (
            "def verify_temporary_evidence_pointer",
            "def verify_review_field_integrity",
            "def normalize_common_mcp_health",
            "def reconcile_verified_packet_findings",
            "pointer_backed_complete_bytes",
            "complete_evidence_index=yes",
        ):
            self.assertIn(marker, wrapper_source)
        for marker in ("wait_for_local_capacity", "queue_ok"):
            self.assertIn(marker, checker_source)
        self.assertIn("--schema-file", grumpy_source)
        for marker in (
            "test_pointer_verification_rejects_unverified_pointer",
            "test_pointer_verification_rejects_mismatched_record_digests",
        ):
            self.assertIn(marker, test_source)

    def test_checker_coerce_result_injects_router_owned_route_evidence(self) -> None:
        packet = self.packet()
        router_route = {
            "router_url": self.checker.DEFAULT_ROUTER_BASE,
            "request_id": "router-request-123",
            "route": "worker",
            "model_alias": self.checker.DEFAULT_MODEL,
            "adapter_id": self.checker.EXPECTED_LOCAL_ROUTER_ADAPTER_ID,
            "adapter_version": self.checker.EXPECTED_LOCAL_ROUTER_ADAPTER_VERSION,
            "direct_backend_used": False,
            "cloud_used": False,
            "truncated": False,
            "timed_out": False,
            "request_hash": "a" * 64,
            "response_hash": "b" * 64,
            "evidence_ref": "local-router:test",
            "route_header_consistent": True,
            "adapter_identity_verified": True,
            "route_evidence_verified": True,
            "model_had_merge_decision": True,
        }
        model_supplied_route = {
            "router_url": "https://attacker.invalid/v1",
            "request_id": "model-invented-request",
            "cloud_used": True,
            "route_evidence_verified": True,
        }
        result = {
            "route_evidence": model_supplied_route,
            "merge_decision": {
                "decision": "no_blocking_defect_found",
                "reason": "router evidence is source-owned",
            },
            "findings": [],
            "adversarial_checks_performed": {
                "why_no_block_is_justified": "route evidence is verified from the router response"
            },
        }

        coerced = self.checker.coerce_result(
            result,
            packet=packet,
            packet_id="packet-123",
            packet_hash="c" * 64,
            route=router_route,
            finish_reason="stop",
        )

        self.assertEqual(coerced["route_evidence"], router_route)
        self.assertNotEqual(coerced["route_evidence"], model_supplied_route)
        self.assertFalse(coerced["route_evidence"]["cloud_used"])
        self.assertEqual(
            coerced["route_evidence"]["request_id"],
            "router-request-123",
        )
        repeated = self.checker.coerce_result(
            {
                "route_evidence": coerced["route_evidence"],
                "merge_decision": {
                    "decision": "no_blocking_defect_found",
                    "reason": "router evidence is source-owned",
                },
                "findings": [],
                "adversarial_checks_performed": {
                    "why_no_block_is_justified": "route evidence is verified from the router response"
                },
            },
            packet=packet,
            packet_id="packet-123",
            packet_hash="c" * 64,
            route=router_route,
            finish_reason="stop",
        )
        self.assertEqual(repeated["route_evidence"], router_route)

    def test_review_field_integrity_rejects_stale_attestation(self) -> None:
        packet = self.packet()
        self.wrapper.verify_review_field_integrity(packet)
        packet["TESTS"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "review_field_integrity TESTS character count mismatch"):
            self.wrapper.verify_review_field_integrity(packet)

    def test_compact_tests_evidence_preserves_status_and_proof_summary(self) -> None:
        tests = (
            "TESTS_STATUS=pass; Primus full suite: 45 passed; Datacube focused suite: 37 passed; "
            "assertions=route_evidence_test=router_owned_injection_overwrites_model_route; "
            "files_dict_test=complete_index_preserves_paths_and_full_digests; "
            "raw_integrity_test=review_field_integrity_checks_A_D_T_chars_and_sha256."
        )
        compacted = self.wrapper.compact_tests_evidence(tests, 500)
        self.assertIn("TESTS_STATUS=pass", compacted)
        self.assertTrue(
            "counts=45 passed,37 passed" in compacted
            or "Primus full suite: 45 passed; Datacube focused suite: 37 passed" in compacted
        )
        self.assertIn("route_evidence_test=router_owned_injection_overwrites_model_route", compacted)
        self.assertIn("files_dict_test=complete_index_preserves_paths_and_full_digests", compacted)
        self.assertIn("raw_integrity_test=review_field_integrity_checks_A_D_T_chars_and_sha256", compacted)

    def test_common_mcp_health_normalizes_datacube_ready_contract(self) -> None:
        payload = {
            "status": "ok",
            "upstream_count": 15,
            "connected_count": 15,
            "backend_mcp_count": 15,
            "backend_mcp_connected_count": 15,
            "backend_error": None,
            "upstreams": [
                {"name": "antigravity_local", "connected": True, "last_error": None},
            ],
        }
        normalized = self.wrapper.normalize_common_mcp_health(payload, status=200)
        self.assertTrue(normalized["ok"])
        self.assertTrue(normalized["ready"])
        self.assertTrue(normalized["required_connected"])
        self.assertEqual(normalized["upstream_error"], "")

    def test_common_mcp_health_fails_closed_without_required_upstream(self) -> None:
        payload = {
            "status": "ok",
            "upstream_count": 15,
            "connected_count": 15,
            "backend_mcp_count": 15,
            "backend_mcp_connected_count": 15,
            "backend_error": None,
            "upstreams": [
                {"name": "other_upstream", "connected": True, "last_error": None},
            ],
        }
        normalized = self.wrapper.normalize_common_mcp_health(payload, status=200)
        self.assertTrue(normalized["ok"])
        self.assertFalse(normalized["ready"])
        self.assertFalse(normalized["required_connected"])

    def test_complete_evidence_index_preserves_atomic_rows_and_full_digests(self) -> None:
        diff = {
            "changed_files": ["tools/a.py", "tests/test_a.py"],
            "change_summary": "atomic files_dict evidence index",
            "files": [
                {"path": "tools/a.py", "summary": "source proof"},
                {"path": "tests/test_a.py", "summary": "test proof"},
            ],
        }
        compacted = self.wrapper.compact_complete_evidence_packet(diff, 1200)
        self.assertIn("complete_evidence_index=yes;", compacted)
        self.assertIn("mode=files_dict", compacted)
        self.assertIn("changed_files=tools/a.py,tests/test_a.py", compacted)
        rows = [line for line in compacted.splitlines() if line.startswith("[")]
        self.assertEqual(len(rows), 2)
        for path in ("tools/a.py", "tests/test_a.py"):
            row = next(line for line in rows if f"path={path} " in line)
            self.assertRegex(row, r"entry_sha256_full=[0-9a-f]{64} entry_sha256_full_len=64")

    def test_pointer_verification_rejects_unverified_pointer(self) -> None:
        candidate = pointer()
        candidate["verified"] = False
        with patch.object(self.wrapper, "_memory_exact_result") as exact_result:
            with self.assertRaisesRegex(RuntimeError, "missing required verification fields"):
                self.wrapper.verify_temporary_evidence_pointer(candidate)
        exact_result.assert_not_called()

    def test_pointer_verification_rejects_missing_retention_proof(self) -> None:
        candidate = pointer()
        candidate["retention_verified"] = False
        with patch.object(self.wrapper, "_memory_exact_result") as exact_result:
            with self.assertRaisesRegex(RuntimeError, "missing required verification fields"):
                self.wrapper.verify_temporary_evidence_pointer(candidate)
        exact_result.assert_not_called()

    def test_pointer_verification_rejects_mismatched_record_digests(self) -> None:
        candidate = pointer()
        metadata = {
            "temporary": True,
            "canonical": False,
            "retention_verified": True,
            "content_sha256": candidate["content_sha256"],
            "packet_sha256": candidate["source_packet_sha256"],
            "purge_after_utc": candidate["purge_after_utc"],
        }
        for field in ("content_sha256", "packet_sha256", "purge_after_utc"):
            mismatched = dict(metadata)
            mismatched[field] = "mismatched"
            with self.subTest(field=field), patch.object(
                self.wrapper, "_memory_exact_result", return_value={"metadata": mismatched}
            ):
                with self.assertRaisesRegex(RuntimeError, f"failed {field} verification"):
                    self.wrapper.verify_temporary_evidence_pointer(candidate)

    def test_capacity_wait_uses_queue_evidence_and_returns_when_admitted(self) -> None:
        full = {
            "health_ok": True,
            "queue_ok": True,
            "slots_ok": True,
            "metrics_ok": False,
            "resident_slots": 4,
            "user_max_in_flight": 4,
            "active_global": 4,
            "active_user": 4,
            "queued_global": 1,
            "queued_user": 1,
        }
        available = {**full, "active_global": 0, "active_user": 0, "queued_global": 0, "queued_user": 0}
        with patch.object(self.checker, "collect_review_evidence", side_effect=[full, available]), patch.object(
            self.checker.time, "sleep"
        ) as sleep:
            admitted = self.checker.wait_for_local_capacity("http://127.0.0.1:11888/v1", 0.25)
        self.assertEqual(admitted["active_global"], 0)
        sleep.assert_called_once_with(0.25)

    def test_capacity_wait_fails_closed_when_queue_evidence_stays_missing(self) -> None:
        missing = {
            "health_ok": True,
            "queue_ok": False,
            "slots_ok": True,
            "metrics_ok": False,
            "resident_slots": 4,
            "user_max_in_flight": 4,
            "active_global": 0,
            "active_user": 0,
            "queued_global": 0,
            "queued_user": 0,
        }
        with patch.object(self.checker, "collect_review_evidence", return_value=missing), patch.object(
            self.checker.time, "sleep"
        ):
            with self.assertRaises(self.checker.ReviewEvidenceFailure) as raised:
                self.checker.wait_for_local_capacity("http://127.0.0.1:11888/v1", 0.01)
        self.assertEqual(raised.exception.reason, "capacity_evidence_unavailable")

    def test_queue_timeout_detection_restores_bounded_error_body(self) -> None:
        body = b'{"detail":"inference router queue timeout waiting for user capacity"}'
        error = urllib.error.HTTPError(
            "http://127.0.0.1:11888/v1/chat/completions",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(body),
        )
        self.assertTrue(self.checker.http_error_is_queue_timeout(error))
        report = self.checker.explain_http_error(error, b"request", 1.5)
        self.assertEqual(report["body"]["detail"], "inference router queue timeout waiting for user capacity")
        error.close()

    def test_memory_gateway_readiness_waits_for_required_upstream(self) -> None:
        degraded = {
            "ok": True,
            "ready": False,
            "required_connected": False,
            "upstream_error": "ClosedResourceError",
        }
        ready = {"ok": True, "ready": True, "required_connected": True, "upstream_error": ""}
        with patch.object(self.wrapper, "_probe_common_mcp_health", side_effect=[degraded, ready]), patch.object(
            self.wrapper.time, "sleep"
        ) as sleep:
            result = self.wrapper.wait_for_common_mcp_ready()
        self.assertEqual(result, ready)
        sleep.assert_called_once_with(self.wrapper.MEMORY_ASYNC_POLL_INTERVAL_S)

    def test_memory_write_waits_for_mcp_readiness_before_submission(self) -> None:
        packet = self.packet()
        events: list[str] = []
        state: dict[str, object] = {}

        def write_mock(**kwargs: object) -> tuple[str, str]:
            events.append("write")
            state["metadata"] = kwargs["metadata"]
            return "memory-ready-order", "entry-ready-order"

        def exact_mock(*args: object, **kwargs: object) -> dict[str, object]:
            return {"metadata": state["metadata"]}

        with (
            patch.object(self.wrapper, "_find_temporary_evidence_by_packet", return_value=None),
            patch.object(self.wrapper, "wait_for_common_mcp_ready", side_effect=lambda: events.append("ready")),
            patch.object(self.wrapper, "_write_temporary_evidence_via_async_mcp", side_effect=write_mock),
            patch.object(self.wrapper, "_memory_exact_result", side_effect=exact_mock),
        ):
            pointer = self.wrapper.write_temporary_evidence_record(packet)

        self.assertEqual(events[:2], ["ready", "write"])
        self.assertEqual(pointer["memory_id"], "memory-ready-order")

    def test_lane_packet_keeps_one_authoritative_pointer(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        lane = self.wrapper.lane_packets_for_budget(
            normalized, 3500, pointer_already_verified=True
        )[0]
        provenance = lane["PROVENANCE"]
        self.assertEqual(
            list(provenance).count("temporary_evidence_pointer"),
            1,
        )
        self.assertNotIn(
            "verified_temporary_evidence_pointer",
            provenance["full_artifacts_transport"],
        )
        self.assertIn(
            "pointer=temporary_evidence_pointer",
            provenance["temporary_evidence_pointer_status"],
        )
        self.assertTrue(provenance["temporary_evidence_pointer_required"])
        self.assertIn(
            "temporary_memory_record_exact_bytes",
            provenance["review_field_integrity_scope"],
        )

    def test_lane_rejects_other_compacted_fields_even_when_test_manifest_fits(self) -> None:
        packet = self.packet()
        packet["TASK"] = (
            "Review the pointer-backed wrapper contract and preserve the full "
            "test manifest at the measured child budget."
        )
        packet["ACCEPTANCE_CRITERIA"] = (
            "The verified pointer remains sole authority; readiness, queue admission, "
            "raw field digests, and complete evidence transport are proven. "
            + ("acceptance detail " * 100)
        )[:1732]
        packet["DIFF_OR_FILES"] = (
            "changed_files=tools/primus-general-code-review;"
            "tools/primus-adversarial-code-checker;tests/test_review_wrapper_transport.py;"
            + ("bounded evidence detail " * 45)
        )[:1062]
        required_tests = (
            "test_memory_gateway_readiness_waits_for_required_upstream",
            "test_memory_write_waits_for_mcp_readiness_before_submission",
            "test_capacity_wait_fails_closed_when_queue_evidence_stays_missing",
            "test_compaction_850_budget_preserves_authoritative_pointer",
            "test_compaction_849_budget_preserves_authoritative_pointer",
        )
        packet["TESTS"] = (
            "TESTS_COMPLETE=true; Primus full suite: 33 tests passed; "
            "Datacube focused suite: 25 tests passed; test functions: "
            + ", ".join(required_tests)
            + "; "
            + ("proof assertion " * 260)
        )[:3565]
        pointer_value = packet["PROVENANCE"]["temporary_evidence_pointer"]
        assert isinstance(pointer_value, dict)
        pointer_value.update(
            {
                "packet_sha256_scope": "checker_normalized_envelope",
                "source_packet_sha256_scope": "temporary_memory_record",
            }
        )
        packet["PROVENANCE"].update(
            {
                "temporary_evidence_pointer_required": True,
                "temporary_evidence_pointer_status": (
                    "pointer=temporary_evidence_pointer;verified=true;retention=verified;"
                    "authority=sole;fields=memory_id|content_sha256|packet_sha256|"
                    "source_packet_sha256|purge_after_utc"
                ),
                "review_field_integrity_scope": (
                    "temporary_memory_record_exact_bytes;lane_values_may_be_compact_previews"
                ),
            }
        )

        normalized, _, _ = self.wrapper.checker_normalized_packet(packet)
        with self.assertRaisesRegex(ValueError, "reviewer-visible evidence differs from source"):
            self.wrapper.lane_packets_for_budget(normalized, 7000, pointer_already_verified=True)
        for test_name in required_tests:
            self.assertIn(test_name, normalized["TESTS"])

    def test_compaction_does_not_create_secondary_pointer(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        for budget in (850, 849):
            compacted = self.wrapper.compact_packet_section_for_key(
                "PROVENANCE", normalized["PROVENANCE"], budget
            )
            self.assertNotIn(
                "verified_temporary_evidence_pointer",
                compacted["full_artifacts_transport"],
            )
            self.assertIn("temporary_evidence_pointer", compacted)

    def test_compaction_preserves_authoritative_sibling_at_boundaries(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        current = normalized["PROVENANCE"]["temporary_evidence_pointer"]
        for budget in (850, 849):
            compacted = self.wrapper.compact_packet_section_for_key(
                "PROVENANCE", normalized["PROVENANCE"], budget
            )
            serialized = json.dumps(compacted, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            sibling = compacted["temporary_evidence_pointer"]
            self.assertLessEqual(len(serialized), budget)
            self.assertTrue(compacted["provenance_verified"], budget)
            self.assertTrue(compacted["complete_packet"], budget)
            self.assertEqual(sibling["memory_id"], current["memory_id"])
            self.assertEqual(sibling["content_sha256"], "a" * 64)
            self.assertEqual(sibling["packet_sha256"], current["packet_sha256"])
            self.assertTrue(sibling["retention_verified"])
            transport = compacted["full_artifacts_transport"]
            self.assertTrue(transport["complete_bytes_stored"])
            self.assertFalse(transport["inline_bytes_in_lane"])

    def test_compaction_850_budget_preserves_authoritative_pointer(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        compaction_budget = 850
        compacted = None
        for budget in (compaction_budget, compaction_budget - 1):
            candidate = self.wrapper.compact_packet_section_for_key(
                "PROVENANCE", normalized["PROVENANCE"], budget
            )
            serialized = json.dumps(candidate, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            self.assertLessEqual(len(serialized), budget)
            self.assertTrue(candidate["provenance_verified"], budget)
            self.assertTrue(candidate["complete_packet"], budget)
            if budget == compaction_budget:
                compacted = candidate
        self.assertIsNotNone(compacted)
        assert compacted is not None
        self.assertTrue(compacted["provenance_verified"])
        self.assertTrue(compacted["complete_packet"])
        serialized_at_850 = json.dumps(
            compacted, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        self.assertLessEqual(len(serialized_at_850), 850)
        current = normalized["PROVENANCE"]["temporary_evidence_pointer"]
        compacted_pointer = compacted["temporary_evidence_pointer"]
        required_pointer_fields = {
            "memory_id",
            "content_sha256",
            "packet_sha256",
            "source_packet_sha256",
            "retention_verified",
            "purge_after_utc",
        }
        self.assertTrue(required_pointer_fields.issubset(compacted_pointer))
        self.assertEqual(compacted_pointer["memory_id"], current["memory_id"])
        self.assertEqual(compacted_pointer["content_sha256"], "a" * 64)
        self.assertEqual(compacted_pointer["packet_sha256"], current["packet_sha256"])
        self.assertEqual(compacted_pointer["source_packet_sha256"], "b" * 64)
        self.assertEqual(compacted_pointer["purge_after_utc"], "2026-11-01T00:00:00Z")
        self.assertTrue(compacted_pointer["retention_verified"])
        self.assertTrue(compacted["complete_packet"])
        self.assertNotIn(
            "verified_temporary_evidence_pointer",
            compacted["full_artifacts_transport"],
        )
        self.assertTrue(compacted["full_artifacts_transport"]["complete_bytes_stored"])
        self.assertFalse(compacted["full_artifacts_transport"]["inline_bytes_in_lane"])

    def test_compaction_849_budget_preserves_authoritative_pointer(self) -> None:
        normalized, _, _ = self.wrapper.checker_normalized_packet(self.packet())
        compacted = self.wrapper.compact_packet_section_for_key(
            "PROVENANCE", normalized["PROVENANCE"], 849
        )
        serialized = json.dumps(compacted, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        self.assertLessEqual(len(serialized), 849)
        self.assertTrue(compacted["provenance_verified"])
        self.assertTrue(compacted["complete_packet"])
        current = normalized["PROVENANCE"]["temporary_evidence_pointer"]
        pointer_value = compacted["temporary_evidence_pointer"]
        self.assertEqual(pointer_value["memory_id"], pointer()["memory_id"])
        self.assertEqual(pointer_value["content_sha256"], "a" * 64)
        self.assertEqual(pointer_value["packet_sha256"], current["packet_sha256"])
        self.assertEqual(pointer_value["source_packet_sha256"], "b" * 64)
        self.assertEqual(pointer_value["purge_after_utc"], "2026-11-01T00:00:00Z")
        self.assertTrue(pointer_value["retention_verified"])
        self.assertEqual(
            compacted["review_field_integrity"],
            "A30:aab07ab36f33edc794150575fd719ae905553fc7e68ec8dbb323547d508cf56c;"
            "D15:db87a7f561833951e5044f3cdc91a599e2f13687661eabfdbb7016a7e5dd0577;"
            "T4:d74ff0ee8da3b9806b18c877dbf29bbde50b5bd8e4dad7a3a725000feb82e8f1",
        )

    def test_complete_evidence_index_has_no_pointer_metadata(self) -> None:
        compacted = self.wrapper.compact_complete_evidence_packet(
            "opaque evidence " * 200, 700
        )
        header = compacted.splitlines()[0]
        self.assertIn("complete_evidence_index=yes", header)
        self.assertIn("evidence=", compacted)
        self.assertNotIn("memory_pointer=", header)
        self.assertNotIn("content_sha256=", header)
        self.assertNotIn("purge_after_utc=", header)

    def test_extract_changed_paths_reads_manifest_declared_paths(self) -> None:
        diff = {
            "changed_files": [
                "tools/primus-general-code-review",
                "tests/test_review_wrapper_transport.py",
            ],
            "files": [
                {
                    "path": "review-manifest-v42.md",
                    "summary": "complete changed-file manifest",
                }
            ],
        }
        self.assertEqual(
            self.wrapper.extract_changed_paths(diff),
            [
                "tools/primus-general-code-review",
                "tests/test_review_wrapper_transport.py",
                "review-manifest-v42.md",
            ],
        )

    def test_compact_evidence_index_preserves_declared_paths(self) -> None:
        diff = {
            "changed_files": [
                "tools/primus-general-code-review",
                "tools/primus-grumpy-reviewer",
                "tests/test_review_wrapper_transport.py",
            ],
            "change_summary": "verified pointer transport, atomic evidence index, queue/readiness guards, deterministic visibility reconciliation, and negative pointer tests",
            "files": [{"path": "review-manifest-v44.md", "summary": "complete manifest"}],
        }
        compacted = self.wrapper.compact_complete_evidence_packet(diff, 700)
        self.assertIn("changed_files=tools/primus-general-code-review,tools/primus-grumpy-reviewer,tests/test_review_wrapper_transport.py", compacted.splitlines()[0])
        self.assertIn("change_summary=verified pointer transport", compacted.splitlines()[0])
        self.assertEqual(
            self.wrapper.extract_changed_paths(compacted),
            [
                "tools/primus-general-code-review",
                "tools/primus-grumpy-reviewer",
                "tests/test_review_wrapper_transport.py",
                "review-manifest-v44.md",
            ],
        )

    def test_compact_required_field_hashes_raw_string_and_counts_raw_chars(self) -> None:
        value = "raw field text with exact characters " * 10
        compacted = self.wrapper.compact_required_field(value, 120)
        self.assertIn(
            f"sha256={self.wrapper.hashlib.sha256(value.encode()).hexdigest()}",
            compacted,
        )
        self.assertIn(f"chars={len(value)}", compacted)
        self.assertNotIn("evidence=", compacted)

    def test_portable_grumpy_launcher_help_uses_bundled_mode_helper(self) -> None:
        launcher = WRAPPER.parent / "primus-grumpy-reviewer"
        completed = subprocess.run(
            [sys.executable, str(launcher), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--local", completed.stdout)
        launcher_source = launcher.read_text(encoding="utf-8")
        self.assertIn('"--schema-file"', launcher_source)
        self.assertIn("PRIMUS_REVIEW_CHECKER_SCHEMA", launcher_source)

    def test_missing_bundled_helper_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            launcher = Path(temp_dir) / "primus-grumpy-reviewer"
            shutil.copy2(WRAPPER.parent / "primus-grumpy-reviewer", launcher)
            completed = subprocess.run(
                [sys.executable, str(launcher), "--help"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("missing bundled inference helper", completed.stderr)

    def test_runtime_root_schema_is_explicit_and_passed_to_lane(self) -> None:
        runtime_root = Path("/tmp/datacube-review-runtime")
        expected_schema = runtime_root / "next-tasks" / "adversarial_code_checker_result_schema_v1_draft.json"
        self.assertEqual(self.wrapper.checker_schema_for_runtime_root(runtime_root), expected_schema)
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            prompt = directory / "prompt.md"
            prompt.write_text("review", encoding="utf-8")
            command = self.wrapper.lane_command(
                checker=Path("/tmp/checker"),
                base_prompt=prompt,
                lane={"id": "test"},
                input_path=directory / "input.json",
                lane_output=directory / "output.json",
                lane_raw=directory / "raw.txt",
                evidence_poll_s=1.0,
                directory=directory,
                max_tokens=128,
                max_review_chars=7000,
                profile_char_budget=1000,
                schema_file=expected_schema,
            )
        schema_index = command.index("--schema-file")
        self.assertEqual(command[schema_index + 1], str(expected_schema))

    def test_explicit_base_prompt_override_precedes_copied_config_path(self) -> None:
        with patch.dict(
            self.wrapper.os.environ,
            {"PRIMUS_REVIEW_BASE_PROMPT": "/tmp/datacube-review-runtime/prompt.md"},
            clear=False,
        ):
            resolved = self.wrapper.base_prompt_for_config(
                {"base_prompt": "/usr/production/next-tasks/old-prompt.md"}
            )
        self.assertEqual(resolved, Path("/tmp/datacube-review-runtime/prompt.md"))

    def test_memory_store_idempotency_stays_in_metadata_contract(self) -> None:
        payload = self.wrapper._temporary_evidence_store_payload(
            content="bounded evidence",
            metadata={"content_sha256": "a" * 64},
            idempotency_key="packet-key",
        )
        self.assertNotIn("idempotency_key", payload)
        self.assertEqual(payload["metadata"]["idempotency_key"], "packet-key")
        self.assertEqual(payload["metadata"]["content_sha256"], "a" * 64)

    def test_memory_reconciliation_accepts_gateway_memory_id(self) -> None:
        self.assertEqual(
            self.wrapper._durable_memory_item_identity({"memory_id": "lg-123"}),
            "lg-123",
        )

    def test_memory_pointer_uses_verified_gateway_purge_deadline(self) -> None:
        packet = self.packet()
        gateway_purge = "2026-11-03T00:00:00Z"
        with (
            patch.object(self.wrapper, "_find_temporary_evidence_by_packet", return_value=None),
            patch.object(
                self.wrapper,
                "_write_temporary_evidence_via_async_mcp",
                return_value=("lg-gateway-retention", "entry-gateway-retention"),
            ),
            patch.object(
                self.wrapper,
                "_memory_exact_result",
                return_value={
                    "metadata": {
                        "temporary": True,
                        "canonical": False,
                        "retention_verified": True,
                        "content_sha256": self.wrapper.hashlib.sha256(
                            json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                        ).hexdigest(),
                        "packet_sha256": self.wrapper.hashlib.sha256(
                            json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
                        ).hexdigest(),
                        "purge_after_utc": gateway_purge,
                    }
                },
            ),
        ):
            pointer = self.wrapper.write_temporary_evidence_record(packet)
        self.assertEqual(pointer["purge_after_utc"], gateway_purge)
        self.assertEqual(
            self.wrapper._durable_memory_item_identity({"id": "entry-123"}),
            "entry-123",
        )

    def test_peer_memory_write_reconciliation_identity_contract(self) -> None:
        payload = self.wrapper._temporary_evidence_store_payload(
            content="bounded evidence",
            metadata={"content_sha256": "a" * 64},
            idempotency_key="peer-contract",
        )
        self.assertNotIn("idempotency_key", payload)
        self.assertEqual(payload["metadata"]["idempotency_key"], "peer-contract")
        self.assertEqual(
            self.wrapper._memory_write_identity({"result": {"memory_id": "lg-peer"}}),
            ("lg-peer", "lg-peer"),
        )
        self.assertEqual(
            self.wrapper._durable_memory_item_identity({"memory_id": "lg-peer"}),
            "lg-peer",
        )

    def test_memory_exact_reconciliation_rejects_mismatched_memory_id(self) -> None:
        with (
            patch.object(
                self.wrapper,
                "_memory_api_json",
                return_value={"results": [{"memory_id": "other-id"}]},
            ),
            patch.object(self.wrapper, "_common_mcp_memory_call", return_value={"results": []}),
            patch.object(self.wrapper.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "did not find expected-id"):
                self.wrapper._memory_exact_result("expected-id", lookup_query="review evidence")

    def test_memory_reconciliation_content_path_accepts_memory_id_without_entry_id(self) -> None:
        content = json.dumps({"evidence": "bounded"}, sort_keys=True, separators=(",", ":"))
        content_sha256, packet_sha256 = self.wrapper._record_content_digests(
            {"content": content}
        )
        gateway_result = {
            "results": [{"memory_id": "lg-content-only", "content": content}],
        }
        authoritative_purge = "2026-11-04T00:00:00Z"
        with (
            patch.object(self.wrapper, "_memory_api_json", return_value={"results": []}),
            patch.object(self.wrapper, "_common_mcp_memory_call", return_value=gateway_result),
            patch.object(
                self.wrapper,
                "_memory_exact_result",
                return_value={
                    "metadata": {
                        "retention_verified": True,
                        "purge_after_utc": authoritative_purge,
                    }
                },
            ),
        ):
            reconciled = self.wrapper._find_temporary_evidence_by_packet(
                title="review evidence",
                content_sha256=content_sha256,
                packet_sha256=packet_sha256,
            )
        self.assertIsNotNone(reconciled)
        assert reconciled is not None
        self.assertEqual(reconciled["memory_id"], "lg-content-only")
        self.assertEqual(reconciled["entry_id"], "lg-content-only")
        self.assertTrue(reconciled["retention_verified"])
        self.assertEqual(reconciled["purge_after_utc"], authoritative_purge)

    def test_memory_reconciliation_content_without_retention_fails_closed(self) -> None:
        content = json.dumps({"evidence": "bounded"}, sort_keys=True, separators=(",", ":"))
        content_sha256, packet_sha256 = self.wrapper._record_content_digests(
            {"content": content}
        )
        with (
            patch.object(self.wrapper, "_memory_api_json", return_value={"results": []}),
            patch.object(
                self.wrapper,
                "_common_mcp_memory_call",
                return_value={"results": [{"memory_id": "lg-no-retention", "content": content}]},
            ),
            patch.object(self.wrapper, "_memory_exact_result", return_value={"metadata": {}}),
        ):
            reconciled = self.wrapper._find_temporary_evidence_by_packet(
                title="review evidence",
                content_sha256=content_sha256,
                packet_sha256=packet_sha256,
            )
        self.assertIsNone(reconciled)


if __name__ == "__main__":
    unittest.main()
