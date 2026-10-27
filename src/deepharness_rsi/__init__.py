"""DeepHarness-RSI contract primitives.

The package intentionally has no provider SDK or network dependency. Runtime
adapters are added only after the Gate 1 contracts are independently verified.
"""

from .contracts import (
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
    static_contract_findings,
    validate_router_endpoint,
)
from .ledger import (
    AdmissionResult,
    DuplicateTaskError,
    ExecutionLedger,
    FencingError,
    IdempotencyConflictError,
    InvalidTransitionError,
    LedgerError,
    OwnershipConflictError,
    SchemaMismatchError,
    TaskSnapshot,
    TerminalConflictError,
    UnknownTaskError,
)

__all__ = [
    "EvidenceBudget",
    "EvidenceRef",
    "LeaseRecord",
    "LeaseState",
    "PolicyEnvelope",
    "PolicyViolation",
    "Receipt",
    "TaskSpec",
    "assert_static_contract",
    "derive_child_policy",
    "static_contract_findings",
    "validate_router_endpoint",
    "AdmissionResult",
    "DuplicateTaskError",
    "ExecutionLedger",
    "FencingError",
    "IdempotencyConflictError",
    "InvalidTransitionError",
    "LedgerError",
    "OwnershipConflictError",
    "SchemaMismatchError",
    "TaskSnapshot",
    "TerminalConflictError",
    "UnknownTaskError",
]
