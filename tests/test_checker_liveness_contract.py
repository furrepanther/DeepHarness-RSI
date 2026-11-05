"""Regression coverage for request-owned checker liveness decisions."""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

loader = SourceFileLoader("checker_liveness_candidate", str(TOOLS / "primus-adversarial-code-checker"))
spec = spec_from_loader(loader.name, loader)
if spec is None:
    raise RuntimeError("cannot load checker candidate")
checker = module_from_spec(spec)
loader.exec_module(checker)


def evidence(*, active_global: int = 0, queued_global: int = 0) -> dict[str, object]:
    """Return the smallest complete evidence shape needed by the liveness guard."""
    headers = {
        "x-inference-local-only": "true",
        "x-inference-adapter-id": checker.EXPECTED_LOCAL_ROUTER_ADAPTER_ID,
        "x-inference-adapter-version": checker.EXPECTED_LOCAL_ROUTER_ADAPTER_VERSION,
    }
    return {
        "health_ok": True,
        "local_agent_route_ok": True,
        "local_agent_preflight": {
            "health": {
                "ok": True,
                "status": 200,
                "headers": headers,
                "payload": {"status": "ok", "local_only": True},
            },
            "model_check": {
                "ok": True,
                "status": 200,
                "headers": headers,
                "payload": {
                    "status": "ok",
                    "local_only": True,
                    "cloud_fallback_allowed": False,
                    "route_mode": "local_agent_fail_loud",
                    "generation_probe": "disabled_by_model_registry",
                    "generation_ready": None,
                    "worker_model": checker.DEFAULT_MODEL,
                    "physical_worker_model": checker.EXPECTED_PHYSICAL_WORKER_MODEL,
                    "upstream_status": 200,
                },
            },
            "verified": True,
        },
        "queue_ok": True,
        "slots_ok": True,
        "metrics_ok": True,
        "resident_slots": 4,
        "user_max_in_flight": 4,
        "active_global": active_global,
        "active_user": active_global,
        "active_background": 0,
        "queued_global": queued_global,
        "queued_user": queued_global,
        "queued_background": 0,
        "total_admitted": 1,
        "total_released": 0,
        "worker_busy": active_global,
        "worker_total": 4,
        "slot_busy": active_global,
        "slot_total": 4,
        "slot_progress": [],
        "requests_processing": active_global,
        "requests_deferred": queued_global,
        "prompt_tokens_total": 0,
        "tokens_predicted_total": 0,
        "n_decode_total": 0,
        "probe_errors": [],
    }


class CheckerLivenessContractTests(unittest.TestCase):
    def test_checker_bundle_bootstraps_without_ambient_pythonpath(self) -> None:
        runtime_files = (
            "primus-adversarial-code-checker",
            "primus-grumpy-reviewer",
            "primus_inference_mode.py",
            "review_packet_identity.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            for name in runtime_files:
                shutil.copy2(TOOLS / name, runtime_root / name)
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, "-B", str(runtime_root / "primus-adversarial-code-checker"), "--help"],
                capture_output=True,
                check=False,
                env=environment,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Run Primus adversarial code checker through local inference router", result.stdout)

    def test_review_runtime_bundle_rejects_explicit_and_inherited_cloud_mode(self) -> None:
        runtime_files = (
            "primus-adversarial-code-checker",
            "primus-grumpy-reviewer",
            "primus_inference_mode.py",
            "review_packet_identity.py",
        )
        variants = ((["--cloud"], None), ([], "cloud"))
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory)
            for name in runtime_files:
                shutil.copy2(TOOLS / name, runtime_root / name)
            for launcher in ("primus-adversarial-code-checker", "primus-grumpy-reviewer"):
                for arguments, inherited_mode in variants:
                    with self.subTest(launcher=launcher, arguments=arguments, inherited_mode=inherited_mode):
                        environment = dict(os.environ)
                        environment.pop("PYTHONPATH", None)
                        if inherited_mode is None:
                            environment.pop("PRIMUS_INFERENCE_MODE", None)
                        else:
                            environment["PRIMUS_INFERENCE_MODE"] = inherited_mode
                        result = subprocess.run(
                            [
                                sys.executable,
                                "-B",
                                str(runtime_root / launcher),
                                *arguments,
                                "--input",
                                str(runtime_root / "unused.json"),
                            ],
                            capture_output=True,
                            check=False,
                            env=environment,
                            text=True,
                        )
                        self.assertEqual(result.returncode, 2)
                        self.assertIn("must be local for review workers", result.stderr)

    def test_live_request_is_not_abandoned_while_router_queue_evidence_exists(self) -> None:
        baseline = evidence()
        queued = evidence(active_global=1, queued_global=1)
        samples = [baseline, queued, queued, queued, queued]
        sample_index = 0
        release_response = threading.Event()
        request_started = threading.Event()

        def collect(_: str) -> dict[str, object]:
            nonlocal sample_index
            current = samples[min(sample_index, len(samples) - 1)]
            sample_index += 1
            # Release only after the old idle-probe branch would have fired.
            if sample_index >= len(samples):
                release_response.set()
            return current

        def delayed_http(_: str, __: dict[str, object]):
            request_started.set()
            release_response.wait()
            return {"fixture": "response"}, {}, b"request", b"response"

        with patch.object(checker, "collect_review_evidence", side_effect=collect), patch.object(
            checker, "http_json", side_effect=delayed_http
        ):
            try:
                response, _, _, _ = checker.local_http_json_with_evidence(
                    checker.DEFAULT_ROUTER_BASE + "/chat/completions",
                    {"fixture": True},
                    checker.DEFAULT_ROUTER_BASE,
                    0.001,
                )
            finally:
                release_response.set()

        self.assertTrue(request_started.is_set())
        self.assertEqual(response, {"fixture": "response"})
        self.assertGreaterEqual(sample_index, len(samples))

    def test_absent_router_ownership_evidence_remains_transport_ambiguous(self) -> None:
        baseline = evidence()
        no_ownership = evidence()
        release_response = threading.Event()

        def delayed_http(_: str, __: dict[str, object]):
            release_response.wait()
            return {"fixture": "late"}, {}, b"request", b"response"

        with patch.object(
            checker,
            "collect_review_evidence",
            side_effect=[baseline, no_ownership, no_ownership, no_ownership],
        ), patch.object(checker, "http_json", side_effect=delayed_http):
            try:
                with self.assertRaises(checker.ReviewEvidenceFailure) as raised:
                    checker.local_http_json_with_evidence(
                        checker.DEFAULT_ROUTER_BASE + "/chat/completions",
                        {"fixture": True},
                        checker.DEFAULT_ROUTER_BASE,
                        0.001,
                    )
            finally:
                release_response.set()

        self.assertEqual(raised.exception.reason, "transport_ambiguous")
        self.assertEqual(raised.exception.evidence["idle_probe_count"], 3)


if __name__ == "__main__":
    unittest.main()
