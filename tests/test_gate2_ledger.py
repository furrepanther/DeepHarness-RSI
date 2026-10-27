"""Gate 2 admission, fencing, recovery, and terminal receipt tests."""

from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from deepharness_rsi.contracts import EvidenceBudget, PolicyEnvelope, Receipt, TaskSpec
from deepharness_rsi.ledger import (
    ExecutionLedger,
    FencingError,
    IdempotencyConflictError,
    InvalidTransitionError,
    OwnershipConflictError,
    SchemaMismatchError,
    TerminalConflictError,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Gate2LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "ledger.sqlite3"
        self.ledger = ExecutionLedger(self.path)
        policy = PolicyEnvelope(
            tools=frozenset({"read", "run-local-test"}),
            namespaces=frozenset({"repo", "review-scratch"}),
            network_endpoints=frozenset({"router:11888"}),
            max_concurrency=2,
            max_depth=1,
            expires_at_epoch_s=2_000_000_000,
        )
        self.spec = TaskSpec(
            task_id="task-001",
            revision="rev-001",
            payload_digest=digest("payload"),
            policy_digest=policy.digest,
            owner_session="SwiftCat:submitter",
            evidence_budget=EvidenceBudget(max_bytes=64_000, max_lines=1_000, max_records=128),
            created_at_epoch_s=1_700_000_000,
            task_kind="review",
        )
        self.ledger.admit(self.spec, idempotency_key="idem-001", now_epoch_s=1_700_000_001)

    def tearDown(self) -> None:
        self.ledger.close()
        self.temp_dir.cleanup()

    def receipt(self, lease, status: str = "complete") -> Receipt:
        return Receipt(
            work_order_id="RWO-001",
            revision=self.spec.revision,
            event_id="event-001",
            task_id=self.spec.task_id,
            claim_id=lease.claim_id,
            owner_session=lease.owner_session,
            idempotency_key="idem-001",
            input_digest=self.spec.payload_digest,
            output_digest=digest("output") if status == "complete" else None,
            evidence_digest=digest("evidence"),
            router_request_id="router-001",
            route="local-router",
            adapter="primus-local-router",
            host="Primus",
            peer="Datacube",
            attempt=lease.attempt,
            terminal_status=status,
        )

    def claim(self, *, owner: str = "SwiftCat:worker", now: int = 1_700_000_010):
        return self.ledger.claim(
            self.spec.task_id,
            owner_session=owner,
            expected_revision=self.spec.revision,
            now_epoch_s=now,
        )

    def test_admission_is_idempotent_and_identity_conflicts_are_rejected(self) -> None:
        result = self.ledger.admit(self.spec, idempotency_key="idem-001", now_epoch_s=1_700_000_002)
        self.assertFalse(result.created)
        self.assertEqual(result.snapshot.task_id, self.spec.task_id)

        with self.assertRaises(IdempotencyConflictError):
            self.ledger.admit(
                replace(self.spec, task_id="task-002"),
                idempotency_key="idem-001",
                now_epoch_s=1_700_000_003,
            )
        with self.assertRaises(ValueError):
            self.ledger.admit(self.spec, idempotency_key="", now_epoch_s=1_700_000_003)
        with self.assertRaises(ValueError):
            self.ledger.claim(
                self.spec.task_id,
                owner_session="SwiftCat:worker",
                expected_revision=self.spec.revision,
                claim_id="",
                now_epoch_s=1_700_000_004,
            )

    def test_claim_start_and_heartbeat_require_fenced_monotonic_ownership(self) -> None:
        lease = self.claim()
        self.assertEqual(lease.state.value, "claimed")
        started = self.ledger.start(lease, now_epoch_s=1_700_000_011)
        self.assertEqual(started.state.value, "running")
        heartbeat = self.ledger.heartbeat(
            started,
            heartbeat_seq=1,
            evidence_digest=digest("heartbeat-1"),
            now_epoch_s=1_700_000_012,
        )
        self.assertEqual(heartbeat.heartbeat_seq, 1)
        duplicate = self.ledger.heartbeat(
            heartbeat,
            heartbeat_seq=1,
            evidence_digest=digest("heartbeat-1"),
            now_epoch_s=1_700_000_013,
        )
        self.assertEqual(duplicate.heartbeat_seq, 1)
        with self.assertRaises(InvalidTransitionError):
            self.ledger.heartbeat(
                heartbeat,
                heartbeat_seq=3,
                evidence_digest=digest("gap"),
                now_epoch_s=1_700_000_014,
            )
        with self.assertRaises(FencingError):
            self.ledger.heartbeat(
                replace(heartbeat, fencing_token="fence-stale"),
                heartbeat_seq=2,
                evidence_digest=digest("stale"),
                now_epoch_s=1_700_000_015,
            )
        with self.assertRaises(FencingError):
            self.ledger.heartbeat(
                replace(heartbeat, attempt=heartbeat.attempt + 1),
                heartbeat_seq=2,
                evidence_digest=digest("wrong-attempt"),
                now_epoch_s=1_700_000_016,
            )

    def test_second_worker_and_revision_mismatch_cannot_claim(self) -> None:
        lease = self.claim()
        with self.assertRaises(OwnershipConflictError):
            self.claim(owner="other-worker")
        self.ledger.settle(lease, self.receipt(lease), now_epoch_s=1_700_000_020)
        with self.assertRaises(InvalidTransitionError):
            self.ledger.claim(
                self.spec.task_id,
                owner_session="worker-2",
                expected_revision=self.spec.revision,
                now_epoch_s=1_700_000_021,
            )

        other = replace(self.spec, task_id="task-002", revision="rev-002")
        self.ledger.admit(other, idempotency_key="idem-002", now_epoch_s=1_700_000_022)
        with self.assertRaises(SchemaMismatchError):
            self.ledger.claim(
                other.task_id,
                owner_session="worker-2",
                expected_revision="rev-old",
                now_epoch_s=1_700_000_023,
            )

    def test_explicit_claim_retry_and_revoke_retry_are_idempotent(self) -> None:
        lease = self.ledger.claim(
            self.spec.task_id,
            owner_session="SwiftCat:worker",
            expected_revision=self.spec.revision,
            claim_id="claim-explicit-001",
            now_epoch_s=1_700_000_024,
        )
        replay = self.ledger.claim(
            self.spec.task_id,
            owner_session="SwiftCat:worker",
            expected_revision=self.spec.revision,
            claim_id="claim-explicit-001",
            now_epoch_s=1_700_000_025,
        )
        self.assertEqual(replay, lease)

        reason = "explicit reconciliation test"
        evidence = digest("revoke-replay")
        revoked = self.ledger.revoke_lease(
            lease,
            actor_session="SwiftCat:supervisor",
            reason=reason,
            evidence_digest=evidence,
            now_epoch_s=1_700_000_026,
        )
        replayed_revoke = self.ledger.revoke_lease(
            lease,
            actor_session="SwiftCat:supervisor",
            reason=reason,
            evidence_digest=evidence,
            now_epoch_s=1_700_000_027,
        )
        self.assertEqual(replayed_revoke, revoked)
        current = self.ledger.current_lease(self.spec.task_id)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.state.value, "revoked")

        reconciled = self.ledger.reconcile(
            self.spec.task_id,
            claim_id=lease.claim_id,
            fencing_token=lease.fencing_token,
            actor_session="SwiftCat:supervisor",
            evidence_digest=digest("reconciled-replay"),
            now_epoch_s=1_700_000_028,
        )
        replayed_reconcile = self.ledger.reconcile(
            self.spec.task_id,
            claim_id=lease.claim_id,
            fencing_token=lease.fencing_token,
            actor_session="SwiftCat:supervisor",
            evidence_digest=digest("reconciled-replay"),
            now_epoch_s=1_700_000_029,
        )
        self.assertEqual(replayed_reconcile, reconciled)

    def test_two_connections_allow_only_one_concurrent_claim(self) -> None:
        first = ExecutionLedger(self.path)
        second = ExecutionLedger(self.path)
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, object]] = []
        outcomes_lock = threading.Lock()

        def attempt(ledger: ExecutionLedger, owner: str, claim_id: str) -> None:
            try:
                barrier.wait()
                lease = ledger.claim(
                    self.spec.task_id,
                    owner_session=owner,
                    expected_revision=self.spec.revision,
                    claim_id=claim_id,
                    now_epoch_s=1_700_000_035,
                )
                outcome: tuple[str, object] = ("ok", lease)
            except BaseException as exc:  # assert every thread outcome below
                outcome = ("error", exc)
            with outcomes_lock:
                outcomes.append(outcome)

        threads = (
            threading.Thread(
                target=attempt,
                args=(first, "SwiftCat:worker-a", "claim-race-a"),
            ),
            threading.Thread(
                target=attempt,
                args=(second, "SwiftCat:worker-b", "claim-race-b"),
            ),
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        first.close()
        second.close()

        self.assertEqual(len(outcomes), 2)
        successes = [outcome for outcome in outcomes if outcome[0] == "ok"]
        failures = [outcome for outcome in outcomes if outcome[0] == "error"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0][1], OwnershipConflictError)

    def test_settlement_is_atomic_and_duplicate_safe(self) -> None:
        lease = self.claim()
        bad = replace(self.receipt(lease), input_digest=digest("wrong"))
        with self.assertRaises(OwnershipConflictError):
            self.ledger.settle(lease, bad, now_epoch_s=1_700_000_030)
        self.assertEqual(self.ledger.get_task(self.spec.task_id).state, "claimed")
        self.assertIsNone(self.ledger.get_receipt(self.spec.task_id))

        receipt = self.receipt(lease)
        settled = self.ledger.settle(lease, receipt, now_epoch_s=1_700_000_031)
        self.assertEqual(settled.state, "complete")
        replay = self.ledger.settle(lease, receipt, now_epoch_s=1_700_000_032)
        self.assertEqual(replay.receipt_digest, settled.receipt_digest)
        with self.assertRaises(TerminalConflictError):
            self.ledger.settle(lease, replace(receipt, event_id="event-002"), now_epoch_s=1_700_000_033)

    def test_explicit_revoke_requires_reconciliation_and_fences_old_worker(self) -> None:
        lease = self.claim()
        revoked = self.ledger.revoke_lease(
            lease,
            actor_session="SwiftCat:supervisor",
            reason="bounded side-effect reconciliation probe",
            evidence_digest=digest("revoke-evidence"),
            now_epoch_s=1_700_000_040,
        )
        self.assertEqual(revoked.state, "reconciling")
        with self.assertRaises(InvalidTransitionError):
            self.ledger.claim(
                self.spec.task_id,
                owner_session="worker-2",
                expected_revision=self.spec.revision,
                now_epoch_s=1_700_000_041,
            )
        with self.assertRaises(InvalidTransitionError):
            self.ledger.heartbeat(
                lease,
                heartbeat_seq=1,
                evidence_digest=digest("late"),
                now_epoch_s=1_700_000_042,
            )
        self.ledger.reconcile(
            self.spec.task_id,
            claim_id=lease.claim_id,
            fencing_token=lease.fencing_token,
            actor_session="SwiftCat:supervisor",
            evidence_digest=digest("reconciled"),
            now_epoch_s=1_700_000_043,
        )
        replacement = self.claim(owner="worker-2", now=1_700_000_044)
        self.assertNotEqual(replacement.fencing_token, lease.fencing_token)
        with self.assertRaises(FencingError):
            self.ledger.settle(lease, self.receipt(lease), now_epoch_s=1_700_000_045)

    def test_cancellation_is_terminal_and_restart_preserves_authority(self) -> None:
        lease = self.claim(now=1_700_000_050)
        self.ledger.close()
        self.ledger = ExecutionLedger(self.path)
        self.assertEqual(self.ledger.get_task(self.spec.task_id).state, "claimed")
        cancelled = self.ledger.cancel(
            lease,
            self.receipt(lease, status="cancelled"),
            now_epoch_s=1_700_000_051,
        )
        self.assertEqual(cancelled.state, "cancelled")
        self.assertEqual(self.ledger.get_receipt(self.spec.task_id)["terminal_status"], "cancelled")

    def test_events_are_task_scoped_and_explicitly_capped(self) -> None:
        lease = self.claim()
        self.ledger.start(lease, now_epoch_s=1_700_000_061)
        self.ledger.heartbeat(
            lease,
            heartbeat_seq=1,
            evidence_digest=digest("heartbeat"),
            now_epoch_s=1_700_000_062,
        )
        events = self.ledger.events(self.spec.task_id, max_records=2)
        self.assertEqual(len(events), 2)
        self.assertEqual([event["event_type"] for event in events], ["started", "heartbeat"])
        with self.assertRaises(ValueError):
            self.ledger.events(self.spec.task_id, max_records=0)
        with self.assertRaises(ValueError):
            self.ledger.events(self.spec.task_id, max_bytes=10)
        with self.assertRaises(ValueError):
            self.ledger.events(self.spec.task_id, max_lines=0)


if __name__ == "__main__":
    unittest.main()
