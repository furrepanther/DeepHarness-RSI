"""Gate 1 runner-neutral contracts.

These are deliberately small, immutable, and provider-free. They describe
authority and evidence; they do not execute processes, call models, or decide
whether a running task should be terminated. A later adapter may consume them
only after validating the same invariants at its side-effect boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable
from urllib.parse import urlparse


LOCAL_ROUTER_ENDPOINT = "http://127.0.0.1:11888/v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


class PolicyViolation(ValueError):
    """Raised when a requested contract would escape an authority boundary."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_tokens(values: Iterable[str], field: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field} must be an iterable of tokens, not a string")
    normalized = frozenset(str(value).strip() for value in values)
    if any(not value or value == "*" or not _TOKEN.fullmatch(value) for value in normalized):
        raise PolicyViolation(f"{field} contains an empty, wildcard, or malformed token")
    return normalized


def _require_digest(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if not _DIGEST.fullmatch(normalized):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return normalized


def validate_router_endpoint(endpoint: str) -> str:
    """Accept only the established loopback inference-router endpoint."""
    normalized = str(endpoint).strip().rstrip("/")
    parsed = urlparse(normalized)
    try:
        port = parsed.port
    except ValueError as exc:
        raise PolicyViolation(
            "inference must use the local router at http://127.0.0.1:11888/v1"
        ) from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port != 11888
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/v1"}
    ):
        raise PolicyViolation(
            "inference must use the local router at http://127.0.0.1:11888/v1"
        )
    return LOCAL_ROUTER_ENDPOINT


@dataclass(frozen=True, slots=True)
class EvidenceBudget:
    """Explicit evidence bounds; there is intentionally no duration bound."""

    max_bytes: int
    max_lines: int
    max_records: int
    allow_whole_log: bool = False

    def __post_init__(self) -> None:
        for field in ("max_bytes", "max_lines", "max_records"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        if self.allow_whole_log:
            raise PolicyViolation("whole-log evidence is forbidden")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_bytes": self.max_bytes,
            "max_lines": self.max_lines,
            "max_records": self.max_records,
            "allow_whole_log": False,
        }


@dataclass(frozen=True, slots=True)
class PolicyEnvelope:
    """Capabilities that a child may only narrow, never widen."""

    tools: frozenset[str]
    namespaces: frozenset[str]
    network_endpoints: frozenset[str]
    max_concurrency: int
    max_depth: int
    expires_at_epoch_s: int
    router_endpoint: str = LOCAL_ROUTER_ENDPOINT

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", _normalize_tokens(self.tools, "tools"))
        object.__setattr__(self, "namespaces", _normalize_tokens(self.namespaces, "namespaces"))
        object.__setattr__(
            self,
            "network_endpoints",
            _normalize_tokens(self.network_endpoints, "network_endpoints"),
        )
        if (
            isinstance(self.max_concurrency, bool)
            or not isinstance(self.max_concurrency, int)
            or self.max_concurrency <= 0
        ):
            raise ValueError("max_concurrency must be a positive integer")
        if (
            isinstance(self.max_depth, bool)
            or not isinstance(self.max_depth, int)
            or self.max_depth < 0
        ):
            raise ValueError("max_depth must be a non-negative integer")
        if (
            isinstance(self.expires_at_epoch_s, bool)
            or not isinstance(self.expires_at_epoch_s, int)
            or self.expires_at_epoch_s <= 0
        ):
            raise ValueError("expires_at_epoch_s must be a positive integer")
        object.__setattr__(self, "router_endpoint", validate_router_endpoint(self.router_endpoint))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": sorted(self.tools),
            "namespaces": sorted(self.namespaces),
            "network_endpoints": sorted(self.network_endpoints),
            "max_concurrency": self.max_concurrency,
            "max_depth": self.max_depth,
            "expires_at_epoch_s": self.expires_at_epoch_s,
            "router_endpoint": self.router_endpoint,
        }

    @property
    def digest(self) -> str:
        return _sha256(_canonical_json(self.to_dict()))


def derive_child_policy(parent: PolicyEnvelope, requested: PolicyEnvelope) -> PolicyEnvelope:
    """Derive a policy by intersection; reject an attempt to change authority."""
    if requested.router_endpoint != parent.router_endpoint:
        raise PolicyViolation("child policy cannot change the parent router authority")
    return PolicyEnvelope(
        tools=parent.tools & requested.tools,
        namespaces=parent.namespaces & requested.namespaces,
        network_endpoints=parent.network_endpoints & requested.network_endpoints,
        max_concurrency=min(parent.max_concurrency, requested.max_concurrency),
        max_depth=min(parent.max_depth, requested.max_depth),
        expires_at_epoch_s=min(parent.expires_at_epoch_s, requested.expires_at_epoch_s),
        router_endpoint=parent.router_endpoint,
    )


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Immutable task identity and the policy/evidence envelope it carries."""

    task_id: str
    revision: str
    payload_digest: str
    policy_digest: str
    owner_session: str
    evidence_budget: EvidenceBudget
    created_at_epoch_s: int
    task_kind: str
    inference_route: str = "local-router"

    def __post_init__(self) -> None:
        for field in ("task_id", "revision", "owner_session", "task_kind"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"{field} must not be empty")
        object.__setattr__(self, "payload_digest", _require_digest(self.payload_digest, "payload_digest"))
        object.__setattr__(self, "policy_digest", _require_digest(self.policy_digest, "policy_digest"))
        if (
            isinstance(self.created_at_epoch_s, bool)
            or not isinstance(self.created_at_epoch_s, int)
            or self.created_at_epoch_s <= 0
        ):
            raise ValueError("created_at_epoch_s must be a positive integer")
        if self.inference_route != "local-router":
            raise PolicyViolation("task callers cannot select a non-router inference route")

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "revision": self.revision,
            "payload_digest": self.payload_digest,
            "policy_digest": self.policy_digest,
            "owner_session": self.owner_session,
            "evidence_budget": self.evidence_budget.to_dict(),
            "created_at_epoch_s": self.created_at_epoch_s,
            "task_kind": self.task_kind,
            "inference_route": self.inference_route,
        }


class LeaseState(str, Enum):
    CLAIMED = "claimed"
    RUNNING = "running"
    RELEASED = "released"
    RECONCILING = "reconciling"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class LeaseRecord:
    """Fenced ownership record; heartbeat age is telemetry, not a kill rule."""

    task_id: str
    claim_id: str
    owner_session: str
    fencing_token: str
    attempt: int
    heartbeat_seq: int
    last_heartbeat_epoch_s: int
    state: LeaseState = LeaseState.CLAIMED

    def __post_init__(self) -> None:
        for field in ("task_id", "claim_id", "owner_session", "fencing_token"):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"{field} must not be empty")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt <= 0:
            raise ValueError("attempt must be a positive integer")
        if (
            isinstance(self.heartbeat_seq, bool)
            or not isinstance(self.heartbeat_seq, int)
            or self.heartbeat_seq < 0
        ):
            raise ValueError("heartbeat_seq must be a non-negative integer")
        if (
            isinstance(self.last_heartbeat_epoch_s, bool)
            or not isinstance(self.last_heartbeat_epoch_s, int)
            or self.last_heartbeat_epoch_s <= 0
        ):
            raise ValueError("last_heartbeat_epoch_s must be a positive integer")
        if not isinstance(self.state, LeaseState):
            object.__setattr__(self, "state", LeaseState(self.state))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "claim_id": self.claim_id,
            "owner_session": self.owner_session,
            "fencing_token": self.fencing_token,
            "attempt": self.attempt,
            "heartbeat_seq": self.heartbeat_seq,
            "last_heartbeat_epoch_s": self.last_heartbeat_epoch_s,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """A bounded, digest-anchored evidence object or temporary pointer."""

    evidence_id: str
    content_sha256: str
    byte_count: int
    line_count: int
    temporary: bool
    pointer_id: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        object.__setattr__(self, "content_sha256", _require_digest(self.content_sha256, "content_sha256"))
        for field in ("byte_count", "line_count"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.temporary and not (self.pointer_id and self.pointer_id.strip()):
            raise PolicyViolation("temporary evidence requires an exact pointer id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "content_sha256": self.content_sha256,
            "byte_count": self.byte_count,
            "line_count": self.line_count,
            "temporary": self.temporary,
            "pointer_id": self.pointer_id,
        }


_TERMINAL_STATUSES = frozenset({"complete", "failed", "blocked", "cancelled", "unknown"})
_ROUTES = frozenset({"local-router", "router-cloud-handoff"})


@dataclass(frozen=True, slots=True)
class Receipt:
    """Authoritative terminal evidence; notifications are not receipts."""

    work_order_id: str
    revision: str
    event_id: str
    task_id: str
    claim_id: str
    owner_session: str
    idempotency_key: str
    input_digest: str
    output_digest: str | None
    evidence_digest: str
    router_request_id: str
    route: str
    adapter: str
    host: str
    peer: str
    attempt: int
    terminal_status: str

    def __post_init__(self) -> None:
        for field in (
            "work_order_id",
            "revision",
            "event_id",
            "task_id",
            "claim_id",
            "owner_session",
            "idempotency_key",
            "router_request_id",
            "adapter",
            "host",
            "peer",
        ):
            if not str(getattr(self, field)).strip():
                raise ValueError(f"{field} must not be empty")
        object.__setattr__(self, "input_digest", _require_digest(self.input_digest, "input_digest"))
        object.__setattr__(self, "evidence_digest", _require_digest(self.evidence_digest, "evidence_digest"))
        if self.output_digest is not None:
            object.__setattr__(self, "output_digest", _require_digest(self.output_digest, "output_digest"))
        if self.route not in _ROUTES:
            raise PolicyViolation("receipt route must be router-owned")
        if self.terminal_status not in _TERMINAL_STATUSES:
            raise ValueError(f"unsupported terminal status: {self.terminal_status}")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt <= 0:
            raise ValueError("attempt must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "revision": self.revision,
            "event_id": self.event_id,
            "task_id": self.task_id,
            "claim_id": self.claim_id,
            "owner_session": self.owner_session,
            "idempotency_key": self.idempotency_key,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "evidence_digest": self.evidence_digest,
            "router_request_id": self.router_request_id,
            "route": self.route,
            "adapter": self.adapter,
            "host": self.host,
            "peer": self.peer,
            "attempt": self.attempt,
            "terminal_status": self.terminal_status,
        }


_DIRECT_PROVIDER_PATTERNS = (
    re.compile(r"https?://(?:api\.)?(?:openai\.com|anthropic\.com|deepseek\.com|openrouter\.ai)", re.IGNORECASE),
    re.compile(r"\b(?:OPENAI|ANTHROPIC|DEEPSEEK|OPENROUTER)_API_KEY\b"),
    re.compile(r"\b(?:OpenAI|Anthropic|ChatOpenAI|ChatAnthropic|AsyncOpenAI)\s*\("),
)
_LITERAL_URL = re.compile(r"https?://[^\s'\"`]+", re.IGNORECASE)
_UNBOUNDED_READ = re.compile(r"\.(?:read|read_text|readlines)\(\s*\)")
_DURATION_SIGNAL = re.compile(r"\b(?:elapsed|duration|age|timeout)(?:[_-]|\b)", re.IGNORECASE)
_TERMINATION_CALL = re.compile(r"\b(?:kill|terminate|cancel|abort)\s*\(", re.IGNORECASE)


def static_contract_findings(source: str, *, source_name: str = "<source>") -> tuple[str, ...]:
    """Return fail-closed findings for common boundary violations.

    This is a deliberately conservative source gate. It is not a substitute
    for review or sandboxing; it prevents obvious bypasses from reaching later
    adapter work without an explicit exception and test.
    """
    findings: list[str] = []
    for pattern in _DIRECT_PROVIDER_PATTERNS:
        if pattern.search(source):
            findings.append(f"{source_name}: direct provider or credential route")
    for match in _LITERAL_URL.finditer(source):
        endpoint = match.group(0).rstrip(".,);]")
        try:
            hostname = urlparse(endpoint).hostname
        except ValueError:
            hostname = None
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            findings.append(f"{source_name}: non-local network route")
            break
    if _UNBOUNDED_READ.search(source):
        findings.append(f"{source_name}: unbounded read")
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if _DURATION_SIGNAL.search(line) and re.search(r"(?:>=|>|==)", line):
            window = "\n".join(lines[index : index + 5])
            if _TERMINATION_CALL.search(window):
                findings.append(f"{source_name}: duration-only termination")
    return tuple(dict.fromkeys(findings))


def assert_static_contract(source: str, *, source_name: str = "<source>") -> None:
    findings = static_contract_findings(source, source_name=source_name)
    if findings:
        raise PolicyViolation("; ".join(findings))
