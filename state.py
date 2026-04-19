"""
In-memory store for reconciliation results keyed by username.
No patient data ever touches disk.
"""
from typing import Optional
from models.schemas import ReconciliationSummary, PlanActualSummary, CombinedResult

_store: dict[str, CombinedResult] = {}


def save_result(
    username: str,
    summary: ReconciliationSummary,
    plan_actual: Optional[PlanActualSummary] = None,
) -> None:
    _store[username] = CombinedResult(prescription=summary, plan_actual=plan_actual)


def get_result(username: str) -> Optional[CombinedResult]:
    return _store.get(username)


def clear_result(username: str) -> None:
    _store.pop(username, None)
