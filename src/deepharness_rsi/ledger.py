"""Durable admission and execution ledger for DeepHarness-RSI Gate 2.

The ledger is intentionally local and provider-free.  SQLite is the durable
source for task ownership and terminal receipts; Memory Fabric remains the
shared knowledge authority and is not duplicated here.  No state transition is
driven by elapsed time.  Recovery is explicit and evidence-backed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .contracts import LeaseRecord, LeaseState, Receipt, TaskSpec


SCHEMA_VERSION = 1
DEFAULT_EVENT_MAX_BYTES = 64_000
DEFAULT_EVENT_MAX_LINES = 1_000
MAX_REVOKE_REASON_BYTES = 1_024
_TERMINAL_STATES = frozenset({"complete", "failed", "blocked", "cancelled", "unknown"})
_ACTIVE_LEASE_STATES = frozenset({"claimed", "running"})
_TASK_STATES = frozenset({"admitted", "claimed", "running", "reconciling", *_TERMINAL_STATES})
_ATTEMPT_STATES = frozenset({"claimed", "running", "revoked", "released"})


class LedgerError(RuntimeError):
    """Base class for explicit ledger failures."""


class UnknownTaskError(LedgerError):
    """The requested task is not present in the authoritative ledger."""


class DuplicateTaskError(LedgerError):
    """A task identity was reused with different immutable data."""


class IdempotencyConflictError(LedgerError):
    """An idempotency key was reused for a different task identity."""


class OwnershipConflictError(LedgerError):
    """A second owner or stale owner attempted a protected transition."""


class FencingError(OwnershipConflictError):
    """A stale or mismatched fencing token attempted a mutation."""


class SchemaMismatchError(LedgerError):
    """The worker and task do not share the admitted schema/revision."""


class InvalidTransitionError(LedgerError):
    """The requested state transition is not valid for the current state."""


class TerminalConflictError(LedgerError):
    """A terminal task was presented with a different receipt."""


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """Result of admission, including whether an existing identity was reused."""

    snapshot: "TaskSnapshot"
    created: bool


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    """Bounded task state returned by the ledger read path."""

    task_id: str
    revision: str
    payload_digest: str
    policy_digest: str
    owner_session: str
    idempotency_key: str
    task_kind: str
    inference_route: str
    schema_version: int
    state: str
    attempt: int
    claim_id: str | None
    claim_owner_session: str | None
    fencing_token: str | None
    heartbeat_seq: int
    last_heartbeat_epoch_s: int | None
    terminal_status: str | None
    receipt_digest: str | None
    updated_at_epoch_s: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "revision": self.revision,
            "payload_digest": self.payload_digest,
            "policy_digest": self.policy_digest,
            "owner_session": self.owner_session,
            "idempotency_key": self.idempotency_key,
            "task_kind": self.task_kind,
            "inference_route": self.inference_route,
            "schema_version": self.schema_version,
            "state": self.state,
            "attempt": self.attempt,
            "claim_id": self.claim_id,
            "claim_owner_session": self.claim_owner_session,
            "fencing_token": self.fencing_token,
            "heartbeat_seq": self.heartbeat_seq,
            "last_heartbeat_epoch_s": self.last_heartbeat_epoch_s,
            "terminal_status": self.terminal_status,
            "receipt_digest": self.receipt_digest,
            "updated_at_epoch_s": self.updated_at_epoch_s,
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_digest(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return normalized


def _require_text(value: str, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    return normalized


def _epoch(value: int | None) -> int:
    if value is None:
        return int(time.time())
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("epoch values must be positive integers")
    return value


def _receipt_digest(receipt: Receipt) -> str:
    return _sha256(_canonical_json(receipt.to_dict()))


class ExecutionLedger:
    """SQLite-backed task admission, fencing, reconciliation, and settlement.

    The connection uses WAL and full synchronous commits, while a process-local
    re-entrant lock keeps multi-threaded callers from interleaving transactions.
    SQLite remains the cross-process serialization authority.  `busy_timeout`
    only governs lock acquisition; it never terminates a task or worker.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            self.path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._initialize()

    def _ensure_open(self) -> None:
        if self._closed:
            raise LedgerError("execution ledger is closed")

    def _initialize(self) -> None:
        self._ensure_open()
        with self._transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ledger_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    revision TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    owner_session TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    task_kind TEXT NOT NULL,
                    inference_route TEXT NOT NULL,
                    evidence_budget_json TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    created_at_epoch_s INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK (state IN (
                        'admitted', 'claimed', 'running', 'reconciling',
                        'complete', 'failed', 'blocked', 'cancelled', 'unknown'
                    )),
                    attempt INTEGER NOT NULL DEFAULT 0,
                    claim_id TEXT,
                    claim_owner_session TEXT,
                    fencing_token TEXT,
                    heartbeat_seq INTEGER NOT NULL DEFAULT 0,
                    last_heartbeat_epoch_s INTEGER,
                    terminal_status TEXT,
                    receipt_digest TEXT,
                    updated_at_epoch_s INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    attempt INTEGER NOT NULL,
                    claim_id TEXT NOT NULL UNIQUE,
                    owner_session TEXT NOT NULL,
                    fencing_token TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN (
                        'claimed', 'running', 'revoked', 'released'
                    )),
                    heartbeat_seq INTEGER NOT NULL DEFAULT 0,
                    last_heartbeat_epoch_s INTEGER NOT NULL,
                    claimed_at_epoch_s INTEGER NOT NULL,
                    started_at_epoch_s INTEGER,
                    revoked_at_epoch_s INTEGER,
                    released_at_epoch_s INTEGER,
                    revoke_reason TEXT,
                    revoke_evidence_digest TEXT,
                    PRIMARY KEY (task_id, attempt)
                );
                CREATE TABLE IF NOT EXISTS heartbeats (
                    task_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    heartbeat_seq INTEGER NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    occurred_at_epoch_s INTEGER NOT NULL,
                    PRIMARY KEY (task_id, claim_id, heartbeat_seq),
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id),
                    receipt_digest TEXT NOT NULL UNIQUE,
                    receipt_json TEXT NOT NULL,
                    recorded_at_epoch_s INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    attempt INTEGER NOT NULL,
                    claim_id TEXT,
                    fencing_token TEXT,
                    owner_session TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    occurred_at_epoch_s INTEGER NOT NULL,
                    details_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_task_seq
                    ON events(task_id, event_seq);
                CREATE INDEX IF NOT EXISTS attempts_task_state
                    ON attempts(task_id, state);
                """
            )
            row = connection.execute(
                "SELECT value FROM ledger_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO ledger_meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise SchemaMismatchError(
                    f"unsupported ledger schema {row['value']}; expected {SCHEMA_VERSION}"
                )

    @contextlib.contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self._ensure_open()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    @staticmethod
    def _budget_json(spec: TaskSpec) -> str:
        return _canonical_json(spec.evidence_budget.to_dict())

    @staticmethod
    def _immutable_identity(spec: TaskSpec, idempotency_key: str, schema_version: int) -> dict[str, Any]:
        return {
            "task_id": spec.task_id,
            "revision": spec.revision,
            "payload_digest": spec.payload_digest,
            "policy_digest": spec.policy_digest,
            "owner_session": spec.owner_session,
            "idempotency_key": idempotency_key,
            "task_kind": spec.task_kind,
            "inference_route": spec.inference_route,
            "evidence_budget": spec.evidence_budget.to_dict(),
            "schema_version": schema_version,
            "created_at_epoch_s": spec.created_at_epoch_s,
        }

    @staticmethod
    def _row_snapshot(row: sqlite3.Row) -> TaskSnapshot:
        return TaskSnapshot(
            task_id=row["task_id"],
            revision=row["revision"],
            payload_digest=row["payload_digest"],
            policy_digest=row["policy_digest"],
            owner_session=row["owner_session"],
            idempotency_key=row["idempotency_key"],
            task_kind=row["task_kind"],
            inference_route=row["inference_route"],
            schema_version=row["schema_version"],
            state=row["state"],
            attempt=row["attempt"],
            claim_id=row["claim_id"],
            claim_owner_session=row["claim_owner_session"],
            fencing_token=row["fencing_token"],
            heartbeat_seq=row["heartbeat_seq"],
            last_heartbeat_epoch_s=row["last_heartbeat_epoch_s"],
            terminal_status=row["terminal_status"],
            receipt_digest=row["receipt_digest"],
            updated_at_epoch_s=row["updated_at_epoch_s"],
        )

    @staticmethod
    def _lease_from_row(row: sqlite3.Row, state: LeaseState | None = None) -> LeaseRecord:
        if not row["claim_id"] or not row["claim_owner_session"] or not row["fencing_token"]:
            raise InvalidTransitionError("task has no current lease")
        if state is None:
            state = LeaseState(row["state"])
        return LeaseRecord(
            task_id=row["task_id"],
            claim_id=row["claim_id"],
            owner_session=row["claim_owner_session"],
            fencing_token=row["fencing_token"],
            attempt=row["attempt"],
            heartbeat_seq=row["heartbeat_seq"],
            last_heartbeat_epoch_s=row["last_heartbeat_epoch_s"],
            state=state,
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        attempt: int,
        claim_id: str | None,
        fencing_token: str | None,
        owner_session: str,
        event_type: str,
        occurred_at_epoch_s: int,
        details: dict[str, Any],
    ) -> str:
        event_id = f"evt-{uuid.uuid4().hex}"
        event_body = {
            "event_id": event_id,
            "task_id": task_id,
            "attempt": attempt,
            "claim_id": claim_id,
            "fencing_token": fencing_token,
            "owner_session": owner_session,
            "event_type": event_type,
            "occurred_at_epoch_s": occurred_at_epoch_s,
            "details": details,
        }
        connection.execute(
            """
            INSERT INTO events(
                event_id, task_id, attempt, claim_id, fencing_token, owner_session,
                event_type, event_digest, occurred_at_epoch_s, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                task_id,
                attempt,
                claim_id,
                fencing_token,
                owner_session,
                event_type,
                _sha256(_canonical_json(event_body)),
                occurred_at_epoch_s,
                _canonical_json(details),
            ),
        )
        return event_id

    def admit(
        self,
        spec: TaskSpec,
        *,
        idempotency_key: str,
        schema_version: int = SCHEMA_VERSION,
        now_epoch_s: int | None = None,
    ) -> AdmissionResult:
        """Admit one immutable task or return the exact prior admission."""
        idempotency_key = _require_text(idempotency_key, "idempotency_key")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != SCHEMA_VERSION
        ):
            raise SchemaMismatchError(
                f"unsupported task schema {schema_version}; expected {SCHEMA_VERSION}"
            )
        now = _epoch(now_epoch_s)
        identity = self._immutable_identity(spec, idempotency_key, schema_version)
        with self._transaction() as connection:
            by_task = connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (spec.task_id,)
            ).fetchone()
            by_key = connection.execute(
                "SELECT * FROM tasks WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if by_task is not None:
                existing_identity = self._identity_from_row(by_task)
                if existing_identity == identity:
                    return AdmissionResult(self._row_snapshot(by_task), created=False)
                raise DuplicateTaskError(f"task identity already exists: {spec.task_id}")
            if by_key is not None:
                raise IdempotencyConflictError(
                    f"idempotency key already belongs to task {by_key['task_id']}"
                )
            connection.execute(
                """
                INSERT INTO tasks(
                    task_id, revision, payload_digest, policy_digest, owner_session,
                    idempotency_key, task_kind, inference_route, evidence_budget_json,
                    schema_version, created_at_epoch_s, state, updated_at_epoch_s
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'admitted', ?)
                """,
                (
                    spec.task_id,
                    spec.revision,
                    spec.payload_digest,
                    spec.policy_digest,
                    spec.owner_session,
                    idempotency_key,
                    spec.task_kind,
                    spec.inference_route,
                    self._budget_json(spec),
                    schema_version,
                    spec.created_at_epoch_s,
                    now,
                ),
            )
            self._append_event(
                connection,
                task_id=spec.task_id,
                attempt=0,
                claim_id=None,
                fencing_token=None,
                owner_session=spec.owner_session,
                event_type="admitted",
                occurred_at_epoch_s=now,
                details={
                    "idempotency_key": idempotency_key,
                    "revision": spec.revision,
                    "payload_digest": spec.payload_digest,
                    "policy_digest": spec.policy_digest,
                    "schema_version": schema_version,
                },
            )
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (spec.task_id,)
            ).fetchone()
            assert row is not None
            return AdmissionResult(self._row_snapshot(row), created=True)

    @staticmethod
    def _identity_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "revision": row["revision"],
            "payload_digest": row["payload_digest"],
            "policy_digest": row["policy_digest"],
            "owner_session": row["owner_session"],
            "idempotency_key": row["idempotency_key"],
            "task_kind": row["task_kind"],
            "inference_route": row["inference_route"],
            "evidence_budget": json.loads(row["evidence_budget_json"]),
            "schema_version": row["schema_version"],
            "created_at_epoch_s": row["created_at_epoch_s"],
        }

    def get_task(self, task_id: str) -> TaskSnapshot:
        task_id = _require_text(task_id, "task_id")
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            raise UnknownTaskError(task_id)
        return self._row_snapshot(row)

    def current_lease(self, task_id: str) -> LeaseRecord | None:
        snapshot = self.get_task(task_id)
        if snapshot.claim_id is None:
            return None
        if snapshot.state in _TERMINAL_STATES or snapshot.state == "reconciling":
            return LeaseRecord(
                task_id=snapshot.task_id,
                claim_id=snapshot.claim_id,
                owner_session=snapshot.claim_owner_session or "",
                fencing_token=snapshot.fencing_token or "",
                attempt=snapshot.attempt,
                heartbeat_seq=snapshot.heartbeat_seq,
                last_heartbeat_epoch_s=snapshot.last_heartbeat_epoch_s or snapshot.updated_at_epoch_s,
                state=LeaseState.REVOKED if snapshot.state == "reconciling" else LeaseState.RELEASED,
            )
        return LeaseRecord(
            task_id=snapshot.task_id,
            claim_id=snapshot.claim_id,
            owner_session=snapshot.claim_owner_session or "",
            fencing_token=snapshot.fencing_token or "",
            attempt=snapshot.attempt,
            heartbeat_seq=snapshot.heartbeat_seq,
            last_heartbeat_epoch_s=snapshot.last_heartbeat_epoch_s or snapshot.updated_at_epoch_s,
            state=LeaseState(snapshot.state),
        )

    def claim(
        self,
        task_id: str,
        *,
        owner_session: str,
        expected_revision: str,
        expected_schema_version: int = SCHEMA_VERSION,
        now_epoch_s: int | None = None,
        claim_id: str | None = None,
    ) -> LeaseRecord:
        """Atomically acquire one fenced lease after revision validation."""
        task_id = _require_text(task_id, "task_id")
        owner_session = _require_text(owner_session, "owner_session")
        expected_revision = _require_text(expected_revision, "expected_revision")
        if (
            isinstance(expected_schema_version, bool)
            or not isinstance(expected_schema_version, int)
            or expected_schema_version != SCHEMA_VERSION
        ):
            raise SchemaMismatchError(
                f"unsupported worker schema {expected_schema_version}; expected {SCHEMA_VERSION}"
            )
        now = _epoch(now_epoch_s)
        claim_id = (
            f"claim-{uuid.uuid4().hex}"
            if claim_id is None
            else _require_text(claim_id, "claim_id")
        )
        fencing_token = f"fence-{uuid.uuid4().hex}"
        with self._transaction() as connection:
            row = self._task_or_raise(connection, task_id)
            if row["revision"] != expected_revision or row["schema_version"] != expected_schema_version:
                raise SchemaMismatchError(f"task {task_id} revision/schema does not match worker")
            existing_attempt = connection.execute(
                "SELECT * FROM attempts WHERE claim_id=?", (claim_id,)
            ).fetchone()
            if existing_attempt is not None:
                if (
                    row["claim_id"] == claim_id
                    and row["claim_owner_session"] == owner_session
                    and row["fencing_token"] == existing_attempt["fencing_token"]
                    and row["state"] in _ACTIVE_LEASE_STATES
                ):
                    return self._lease_from_row(row, LeaseState(row["state"]))
                raise OwnershipConflictError(f"claim ID already belongs to another attempt: {claim_id}")
            if row["state"] in _TERMINAL_STATES:
                raise InvalidTransitionError(f"task {task_id} is terminal: {row['state']}")
            if row["state"] == "reconciling":
                raise InvalidTransitionError(
                    f"task {task_id} requires explicit reconciliation before re-dispatch"
                )
            if row["state"] in _ACTIVE_LEASE_STATES:
                raise OwnershipConflictError(f"task {task_id} already has an active lease")
            if row["state"] != "admitted":
                raise InvalidTransitionError(f"task {task_id} cannot be claimed from {row['state']}")
            attempt = row["attempt"] + 1
            connection.execute(
                """
                INSERT INTO attempts(
                    task_id, attempt, claim_id, owner_session, fencing_token,
                    state, heartbeat_seq, last_heartbeat_epoch_s, claimed_at_epoch_s
                ) VALUES (?, ?, ?, ?, ?, 'claimed', 0, ?, ?)
                """,
                (task_id, attempt, claim_id, owner_session, fencing_token, now, now),
            )
            connection.execute(
                """
                UPDATE tasks
                SET state='claimed', attempt=?, claim_id=?, claim_owner_session=?,
                    fencing_token=?, heartbeat_seq=0, last_heartbeat_epoch_s=?,
                    terminal_status=NULL, receipt_digest=NULL, updated_at_epoch_s=?
                WHERE task_id=?
                """,
                (attempt, claim_id, owner_session, fencing_token, now, now, task_id),
            )
            self._append_event(
                connection,
                task_id=task_id,
                attempt=attempt,
                claim_id=claim_id,
                fencing_token=fencing_token,
                owner_session=owner_session,
                event_type="claimed",
                occurred_at_epoch_s=now,
                details={"revision": row["revision"], "schema_version": row["schema_version"]},
            )
            return LeaseRecord(
                task_id=task_id,
                claim_id=claim_id,
                owner_session=owner_session,
                fencing_token=fencing_token,
                attempt=attempt,
                heartbeat_seq=0,
                last_heartbeat_epoch_s=now,
                state=LeaseState.CLAIMED,
            )

    @staticmethod
    def _task_or_raise(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise UnknownTaskError(task_id)
        return row

    @staticmethod
    def _verify_lease_row(
        row: sqlite3.Row,
        lease: LeaseRecord,
        *,
        allow_reconciling: bool = False,
    ) -> None:
        if row["attempt"] != lease.attempt:
            raise FencingError(f"stale attempt for task {row['task_id']}")
        if row["claim_id"] != lease.claim_id or row["fencing_token"] != lease.fencing_token:
            raise FencingError(f"stale fencing token for task {row['task_id']}")
        if row["claim_owner_session"] != lease.owner_session:
            raise OwnershipConflictError(f"wrong lease owner for task {row['task_id']}")
        allowed = _ACTIVE_LEASE_STATES | ({"reconciling"} if allow_reconciling else set())
        if row["state"] not in allowed:
            raise InvalidTransitionError(
                f"task {row['task_id']} lease is not active: {row['state']}"
            )

    def start(self, lease: LeaseRecord, *, now_epoch_s: int | None = None) -> LeaseRecord:
        now = _epoch(now_epoch_s)
        with self._transaction() as connection:
            row = self._task_or_raise(connection, lease.task_id)
            self._verify_lease_row(row, lease)
            if row["state"] == "running":
                return self._lease_from_row(row, LeaseState.RUNNING)
            if row["state"] != "claimed":
                raise InvalidTransitionError(f"cannot start task from {row['state']}")
            connection.execute(
                "UPDATE tasks SET state='running', updated_at_epoch_s=? WHERE task_id=?",
                (now, lease.task_id),
            )
            connection.execute(
                "UPDATE attempts SET state='running', started_at_epoch_s=? WHERE task_id=? AND attempt=?",
                (now, lease.task_id, lease.attempt),
            )
            self._append_event(
                connection,
                task_id=lease.task_id,
                attempt=lease.attempt,
                claim_id=lease.claim_id,
                fencing_token=lease.fencing_token,
                owner_session=lease.owner_session,
                event_type="started",
                occurred_at_epoch_s=now,
                details={},
            )
            return LeaseRecord(
                task_id=lease.task_id,
                claim_id=lease.claim_id,
                owner_session=lease.owner_session,
                fencing_token=lease.fencing_token,
                attempt=lease.attempt,
                heartbeat_seq=lease.heartbeat_seq,
                last_heartbeat_epoch_s=lease.last_heartbeat_epoch_s,
                state=LeaseState.RUNNING,
            )

    def heartbeat(
        self,
        lease: LeaseRecord,
        *,
        heartbeat_seq: int,
        evidence_digest: str,
        now_epoch_s: int | None = None,
    ) -> LeaseRecord:
        if isinstance(heartbeat_seq, bool) or not isinstance(heartbeat_seq, int) or heartbeat_seq <= 0:
            raise ValueError("heartbeat_seq must be a positive integer")
        evidence_digest = _require_digest(evidence_digest, "evidence_digest")
        now = _epoch(now_epoch_s)
        with self._transaction() as connection:
            row = self._task_or_raise(connection, lease.task_id)
            self._verify_lease_row(row, lease)
            current_seq = row["heartbeat_seq"]
            if heartbeat_seq <= current_seq:
                previous = connection.execute(
                    """
                    SELECT evidence_digest FROM heartbeats
                    WHERE task_id=? AND claim_id=? AND heartbeat_seq=?
                    """,
                    (lease.task_id, lease.claim_id, heartbeat_seq),
                ).fetchone()
                if previous is not None and previous["evidence_digest"] == evidence_digest:
                    return self._lease_from_row(row, LeaseState(row["state"]))
                raise FencingError("heartbeat sequence is stale or has a different digest")
            if heartbeat_seq != current_seq + 1:
                raise InvalidTransitionError(
                    f"heartbeat sequence gap: expected {current_seq + 1}, got {heartbeat_seq}"
                )
            connection.execute(
                """
                INSERT INTO heartbeats(task_id, claim_id, heartbeat_seq, evidence_digest, occurred_at_epoch_s)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lease.task_id, lease.claim_id, heartbeat_seq, evidence_digest, now),
            )
            connection.execute(
                """
                UPDATE tasks SET heartbeat_seq=?, last_heartbeat_epoch_s=?, updated_at_epoch_s=?
                WHERE task_id=?
                """,
                (heartbeat_seq, now, now, lease.task_id),
            )
            connection.execute(
                """
                UPDATE attempts SET heartbeat_seq=?, last_heartbeat_epoch_s=?
                WHERE task_id=? AND attempt=?
                """,
                (heartbeat_seq, now, lease.task_id, lease.attempt),
            )
            self._append_event(
                connection,
                task_id=lease.task_id,
                attempt=lease.attempt,
                claim_id=lease.claim_id,
                fencing_token=lease.fencing_token,
                owner_session=lease.owner_session,
                event_type="heartbeat",
                occurred_at_epoch_s=now,
                details={"heartbeat_seq": heartbeat_seq, "evidence_digest": evidence_digest},
            )
            return LeaseRecord(
                task_id=lease.task_id,
                claim_id=lease.claim_id,
                owner_session=lease.owner_session,
                fencing_token=lease.fencing_token,
                attempt=lease.attempt,
                heartbeat_seq=heartbeat_seq,
                last_heartbeat_epoch_s=now,
                state=LeaseState(row["state"]),
            )

    def revoke_lease(
        self,
        lease: LeaseRecord,
        *,
        actor_session: str,
        reason: str,
        evidence_digest: str,
        now_epoch_s: int | None = None,
    ) -> TaskSnapshot:
        """Explicitly revoke a lease; age alone can never trigger this method."""
        actor_session = _require_text(actor_session, "actor_session")
        reason = _require_text(reason, "reason")
        if len(reason.encode("utf-8")) > MAX_REVOKE_REASON_BYTES:
            raise ValueError(
                f"reason must be at most {MAX_REVOKE_REASON_BYTES} UTF-8 bytes"
            )
        evidence_digest = _require_digest(evidence_digest, "evidence_digest")
        now = _epoch(now_epoch_s)
        with self._transaction() as connection:
            row = self._task_or_raise(connection, lease.task_id)
            if row["state"] == "reconciling":
                previous = connection.execute(
                    """
                    SELECT revoke_reason, revoke_evidence_digest
                    FROM attempts WHERE task_id=? AND attempt=?
                    """,
                    (lease.task_id, lease.attempt),
                ).fetchone()
                if (
                    row["claim_id"] == lease.claim_id
                    and row["fencing_token"] == lease.fencing_token
                    and previous is not None
                    and previous["revoke_reason"] == reason
                    and previous["revoke_evidence_digest"] == evidence_digest
                ):
                    return self._row_snapshot(row)
            self._verify_lease_row(row, lease)
            connection.execute(
                """
                UPDATE attempts
                SET state='revoked', revoked_at_epoch_s=?, revoke_reason=?, revoke_evidence_digest=?
                WHERE task_id=? AND attempt=?
                """,
                (now, reason, evidence_digest, lease.task_id, lease.attempt),
            )
            connection.execute(
                "UPDATE tasks SET state='reconciling', updated_at_epoch_s=? WHERE task_id=?",
                (now, lease.task_id),
            )
            self._append_event(
                connection,
                task_id=lease.task_id,
                attempt=lease.attempt,
                claim_id=lease.claim_id,
                fencing_token=lease.fencing_token,
                owner_session=actor_session,
                event_type="lease_revoked",
                occurred_at_epoch_s=now,
                details={
                    "actor_session": actor_session,
                    "reason": reason,
                    "evidence_digest": evidence_digest,
                    "previous_owner_session": lease.owner_session,
                },
            )
            updated = connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (lease.task_id,)
            ).fetchone()
            assert updated is not None
            return self._row_snapshot(updated)

    def reconcile(
        self,
        task_id: str,
        *,
        claim_id: str,
        fencing_token: str,
        actor_session: str,
        evidence_digest: str,
        now_epoch_s: int | None = None,
    ) -> TaskSnapshot:
        """Record side-effect reconciliation before allowing a new claim."""
        task_id = _require_text(task_id, "task_id")
        claim_id = _require_text(claim_id, "claim_id")
        fencing_token = _require_text(fencing_token, "fencing_token")
        actor_session = _require_text(actor_session, "actor_session")
        evidence_digest = _require_digest(evidence_digest, "evidence_digest")
        now = _epoch(now_epoch_s)
        with self._transaction() as connection:
            row = self._task_or_raise(connection, task_id)
            if row["state"] != "reconciling":
                previous = connection.execute(
                    """
                    SELECT details_json FROM events
                    WHERE task_id=? AND event_type='reconciled' AND claim_id=?
                    ORDER BY event_seq DESC LIMIT 1
                    """,
                    (task_id, claim_id),
                ).fetchone()
                if (
                    previous is not None
                    and json.loads(previous["details_json"]).get("evidence_digest") == evidence_digest
                ):
                    return self._row_snapshot(row)
                raise InvalidTransitionError(f"task {task_id} is not awaiting reconciliation")
            if row["claim_id"] != claim_id or row["fencing_token"] != fencing_token:
                raise FencingError(f"reconciliation token does not match task {task_id}")
            attempt = connection.execute(
                """
                SELECT state, fencing_token FROM attempts
                WHERE task_id=? AND attempt=? AND claim_id=?
                """,
                (task_id, row["attempt"], claim_id),
            ).fetchone()
            if attempt is None or attempt["fencing_token"] != fencing_token:
                raise FencingError(f"reconciliation attempt does not match task {task_id}")
            if attempt["state"] != "revoked":
                raise InvalidTransitionError(
                    f"task {task_id} attempt is not revoked: {attempt['state']}"
                )
            connection.execute(
                """
                UPDATE tasks
                SET state='admitted', claim_id=NULL, claim_owner_session=NULL,
                    fencing_token=NULL, heartbeat_seq=0, last_heartbeat_epoch_s=NULL,
                    updated_at_epoch_s=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self._append_event(
                connection,
                task_id=task_id,
                attempt=row["attempt"],
                claim_id=claim_id,
                fencing_token=fencing_token,
                owner_session=actor_session,
                event_type="reconciled",
                occurred_at_epoch_s=now,
                details={"actor_session": actor_session, "evidence_digest": evidence_digest},
            )
            updated = connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            assert updated is not None
            return self._row_snapshot(updated)

    def _validate_receipt(self, row: sqlite3.Row, receipt: Receipt) -> None:
        expected = {
            "task_id": row["task_id"],
            "revision": row["revision"],
            "claim_id": row["claim_id"],
            "owner_session": row["claim_owner_session"],
            "idempotency_key": row["idempotency_key"],
            "input_digest": row["payload_digest"],
            "attempt": row["attempt"],
        }
        actual = {
            "task_id": receipt.task_id,
            "revision": receipt.revision,
            "claim_id": receipt.claim_id,
            "owner_session": receipt.owner_session,
            "idempotency_key": receipt.idempotency_key,
            "input_digest": receipt.input_digest,
            "attempt": receipt.attempt,
        }
        if actual != expected:
            raise OwnershipConflictError("receipt does not match the current task lease and identity")

    def settle(self, lease: LeaseRecord, receipt: Receipt, *, now_epoch_s: int | None = None) -> TaskSnapshot:
        """Atomically publish one authoritative terminal receipt."""
        if receipt.task_id != lease.task_id or receipt.claim_id != lease.claim_id:
            raise OwnershipConflictError("receipt task and lease do not match")
        receipt_digest = _receipt_digest(receipt)
        now = _epoch(now_epoch_s)
        with self._transaction() as connection:
            row = self._task_or_raise(connection, lease.task_id)
            if row["state"] in _TERMINAL_STATES:
                if row["receipt_digest"] == receipt_digest:
                    return self._row_snapshot(row)
                raise TerminalConflictError(f"task {lease.task_id} already has a different terminal receipt")
            self._verify_lease_row(row, lease)
            self._validate_receipt(row, receipt)
            connection.execute(
                """
                INSERT INTO receipts(task_id, receipt_digest, receipt_json, recorded_at_epoch_s)
                VALUES (?, ?, ?, ?)
                """,
                (lease.task_id, receipt_digest, _canonical_json(receipt.to_dict()), now),
            )
            connection.execute(
                """
                UPDATE tasks
                SET state=?, terminal_status=?, receipt_digest=?, updated_at_epoch_s=?
                WHERE task_id=?
                """,
                (receipt.terminal_status, receipt.terminal_status, receipt_digest, now, lease.task_id),
            )
            connection.execute(
                """
                UPDATE attempts SET state='released', released_at_epoch_s=?
                WHERE task_id=? AND attempt=?
                """,
                (now, lease.task_id, lease.attempt),
            )
            self._append_event(
                connection,
                task_id=lease.task_id,
                attempt=lease.attempt,
                claim_id=lease.claim_id,
                fencing_token=lease.fencing_token,
                owner_session=lease.owner_session,
                event_type="settled",
                occurred_at_epoch_s=now,
                details={
                    "terminal_status": receipt.terminal_status,
                    "receipt_digest": receipt_digest,
                },
            )
            updated = connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (lease.task_id,)
            ).fetchone()
            assert updated is not None
            return self._row_snapshot(updated)

    def cancel(self, lease: LeaseRecord, receipt: Receipt, *, now_epoch_s: int | None = None) -> TaskSnapshot:
        """Cancel through the same receipt path; cancellation is terminal and replay-safe."""
        if receipt.terminal_status != "cancelled":
            raise InvalidTransitionError("cancel requires a cancelled receipt")
        return self.settle(lease, receipt, now_epoch_s=now_epoch_s)

    def get_receipt(self, task_id: str) -> dict[str, Any] | None:
        task_id = _require_text(task_id, "task_id")
        with self._lock:
            self._ensure_open()
            row = self._connection.execute(
                "SELECT receipt_json FROM receipts WHERE task_id=?", (task_id,)
            ).fetchone()
        return None if row is None else json.loads(row["receipt_json"])

    def events(
        self,
        task_id: str,
        *,
        max_records: int = 128,
        max_bytes: int = DEFAULT_EVENT_MAX_BYTES,
        max_lines: int = DEFAULT_EVENT_MAX_LINES,
    ) -> tuple[dict[str, Any], ...]:
        """Return a task-scoped tail under record, byte, and line caps."""
        task_id = _require_text(task_id, "task_id")
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records <= 0:
            raise ValueError("max_records must be a positive integer")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines <= 0:
            raise ValueError("max_lines must be a positive integer")
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute(
                """
                SELECT event_seq, event_id, task_id, attempt, claim_id, fencing_token,
                       owner_session, event_type, event_digest, occurred_at_epoch_s, details_json
                FROM events WHERE task_id=? ORDER BY event_seq DESC LIMIT ?
                """,
                (task_id, max_records),
            ).fetchall()
        selected: list[dict[str, Any]] = []
        bytes_used = 0
        lines_used = 0
        for row in rows:
            event = {
                "event_seq": row["event_seq"],
                "event_id": row["event_id"],
                "task_id": row["task_id"],
                "attempt": row["attempt"],
                "claim_id": row["claim_id"],
                "fencing_token": row["fencing_token"],
                "owner_session": row["owner_session"],
                "event_type": row["event_type"],
                "event_digest": row["event_digest"],
                "occurred_at_epoch_s": row["occurred_at_epoch_s"],
                "details": json.loads(row["details_json"]),
            }
            encoded = _canonical_json(event).encode("utf-8")
            event_bytes = len(encoded)
            event_lines = encoded.count(b"\n") + 1
            if event_bytes > max_bytes or event_lines > max_lines:
                if not selected:
                    raise ValueError("newest event exceeds the requested evidence caps")
                break
            if bytes_used + event_bytes > max_bytes or lines_used + event_lines > max_lines:
                break
            selected.append(event)
            bytes_used += event_bytes
            lines_used += event_lines
        selected.reverse()
        return tuple(selected)

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> "ExecutionLedger":
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
