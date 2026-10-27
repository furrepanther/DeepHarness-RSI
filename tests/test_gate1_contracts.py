"""Gate 1 contract and fail-closed boundary tests."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from deepharness_rsi.contracts import (  # noqa: E402
    EvidenceBudget,
    EvidenceRef,
    LeaseRecord,
    LeaseState,
    PolicyEnvelope,
    PolicyViolation,
    Receipt,
    TaskSpec,
    assert_static_contract,
    derive_child_policy,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Gate1ContractTests(unittest.TestCase):
    def parent_policy(self) -> PolicyEnvelope:
        return PolicyEnvelope(
            tools=frozenset({"read", "review", "run-local-test"}),
            namespaces=frozenset({"repo", "review-scratch"}),
            network_endpoints=frozenset({"router:11888", "memfab:18001"}),
            max_concurrency=4,
            max_depth=3,
            expires_at_epoch_s=2_000_000_000,
        )

    def test_child_policy_is_an_intersection_and_never_widens(self) -> None:
        parent = self.parent_policy()
        requested = PolicyEnvelope(
            tools=frozenset({"read", "review", "shell", "run-local-test"}),
            namespaces=frozenset({"repo", "review-scratch", "host-root"}),
            network_endpoints=frozenset({"router:11888", "internet"}),
            max_concurrency=99,
            max_depth=99,
            expires_at_epoch_s=9_000_000_000,
        )
        child = derive_child_policy(parent, requested)
        self.assertEqual(child.tools, frozenset({"read", "review", "run-local-test"}))
        self.assertEqual(child.namespaces, frozenset({"repo", "review-scratch"}))
        self.assertEqual(child.network_endpoints, frozenset({"router:11888"}))
        self.assertEqual(child.max_concurrency, 4)
        self.assertEqual(child.max_depth, 3)
        self.assertEqual(child.expires_at_epoch_s, 2_000_000_000)
        self.assertTrue(child.tools <= parent.tools)
        self.assertTrue(child.namespaces <= parent.namespaces)
        self.assertTrue(child.network_endpoints <= parent.network_endpoints)

    def test_child_cannot_change_router_authority(self) -> None:
        parent = self.parent_policy()
        with self.assertRaises(PolicyViolation):
            PolicyEnvelope(
                tools=frozenset({"read"}),
                namespaces=frozenset({"repo"}),
                network_endpoints=frozenset({"internet"}),
                max_concurrency=1,
                max_depth=1,
                expires_at_epoch_s=2_000_000_000,
                router_endpoint="https://api.openai.com/v1",
            )

    def test_evidence_budget_has_explicit_caps_and_no_whole_log(self) -> None:
        budget = EvidenceBudget(max_bytes=64_000, max_lines=1_000, max_records=128)
        self.assertEqual(budget.to_dict()["allow_whole_log"], False)
        with self.assertRaises(PolicyViolation):
            EvidenceBudget(max_bytes=1, max_lines=1, max_records=1, allow_whole_log=True)

    def test_contract_bounds_reject_non_integer_values_and_bad_router_ports(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceBudget(max_bytes="64000", max_lines=1_000, max_records=128)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            PolicyEnvelope(
                tools=frozenset({"read"}),
                namespaces=frozenset({"repo"}),
                network_endpoints=frozenset({"router:11888"}),
                max_concurrency="4",  # type: ignore[arg-type]
                max_depth=1,
                expires_at_epoch_s=2_000_000_000,
            )
        with self.assertRaises(PolicyViolation):
            PolicyEnvelope(
                tools=frozenset({"read"}),
                namespaces=frozenset({"repo"}),
                network_endpoints=frozenset({"router:11888"}),
                max_concurrency=1,
                max_depth=1,
                expires_at_epoch_s=2_000_000_000,
                router_endpoint="http://127.0.0.1:not-a-port",
            )

    def test_task_lease_evidence_and_receipt_are_typed(self) -> None:
        policy = self.parent_policy()
        task = TaskSpec(
            task_id="task-001",
            revision="rev-001",
            payload_digest=digest("payload"),
            policy_digest=policy.digest,
            owner_session="SwiftCat:session-001",
            evidence_budget=EvidenceBudget(max_bytes=64_000, max_lines=1_000, max_records=128),
            created_at_epoch_s=1_700_000_000,
            task_kind="review",
        )
        lease = LeaseRecord(
            task_id=task.task_id,
            claim_id="claim-001",
            owner_session=task.owner_session,
            fencing_token="fence-001",
            attempt=1,
            heartbeat_seq=0,
            last_heartbeat_epoch_s=1_700_000_001,
            state=LeaseState.RUNNING,
        )
        evidence = EvidenceRef(
            evidence_id="ev-001",
            content_sha256=digest("evidence"),
            byte_count=8,
            line_count=1,
            temporary=True,
            pointer_id="memory-001",
        )
        receipt = Receipt(
            work_order_id="RWO-001",
            revision=task.revision,
            event_id="event-001",
            task_id=task.task_id,
            claim_id=lease.claim_id,
            owner_session=task.owner_session,
            idempotency_key="idem-001",
            input_digest=task.payload_digest,
            output_digest=digest("output"),
            evidence_digest=evidence.content_sha256,
            router_request_id="router-001",
            route="local-router",
            adapter="primus-local-router",
            host="Primus",
            peer="Datacube",
            attempt=1,
            terminal_status="complete",
        )
        self.assertEqual(json.loads(json.dumps(task.to_dict()))["task_id"], "task-001")
        self.assertEqual(task.to_dict()["payload_digest"], digest("payload"))
        self.assertEqual(lease.to_dict()["state"], "running")
        self.assertEqual(evidence.to_dict()["pointer_id"], "memory-001")
        self.assertEqual(receipt.to_dict()["route"], "local-router")
        with self.assertRaises(PolicyViolation):
            TaskSpec(
                task_id=task.task_id,
                revision=task.revision,
                payload_digest=task.payload_digest,
                policy_digest=task.policy_digest,
                owner_session=task.owner_session,
                evidence_budget=task.evidence_budget,
                created_at_epoch_s=task.created_at_epoch_s,
                task_kind=task.task_kind,
                inference_route="direct-provider",
            )
        with self.assertRaises(PolicyViolation):
            replace(receipt, route="direct-provider")

    def test_static_gate_rejects_direct_provider_hidden_cloud_and_unbounded_reads(self) -> None:
        bad = """
        import requests
        client = OpenAI(api_key=OPENAI_API_KEY)
        requests.post('https://api.openai.com/v1/responses')
        body = open('evidence.log').read()
        if elapsed_s > 60:
            process.kill()
        """
        findings = []
        try:
            assert_static_contract(bad, source_name="bad-fixture.py")
        except PolicyViolation as exc:
            findings = str(exc).split("; ")
        self.assertTrue(any("direct provider" in finding for finding in findings))
        self.assertTrue(any("unbounded read" in finding for finding in findings))
        self.assertTrue(any("duration-only termination" in finding for finding in findings))

    def test_static_gate_accepts_router_only_bounded_source(self) -> None:
        good = """
        endpoint = 'http://127.0.0.1:11888/v1'
        with open(path, 'rb') as stream:
            packet = stream.read(64000)
        """
        assert_static_contract(good, source_name="good-fixture.py")

    def test_static_gate_rejects_generic_external_route(self) -> None:
        external = "endpoint = 'https://cloud.example.invalid/v1'"
        with self.assertRaises(PolicyViolation):
            assert_static_contract(external, source_name="external-fixture.py")

    def test_static_gate_rejects_malformed_literal_route(self) -> None:
        malformed = "endpoint = 'http://[::1'"
        with self.assertRaises(PolicyViolation):
            assert_static_contract(malformed, source_name="malformed-fixture.py")


if __name__ == "__main__":
    unittest.main()
