from pydantic import BaseModel
from typing import Optional


class ReconciliationRow(BaseModel):
    patient: str
    geburtsdatum: Optional[str] = None
    tarifcode: Optional[str] = None
    tarifziffer: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    authorized_minutes: float = 0
    consumed_minutes: float = 0
    remaining_minutes: float = 0
    utilization_pct: Optional[float] = None
    status: str = ""
    service_count: int = 0
    refusal_reason: Optional[str] = None
    out_of_range_count: int = 0
    out_of_range_minutes: float = 0


class ReconciliationSummary(BaseModel):
    total_patients: int = 0
    total_prescriptions: int = 0
    within_limit: int = 0
    near_limit: int = 0
    exceeded: int = 0
    out_of_range: int = 0
    no_services: int = 0
    no_prescription: int = 0
    generated_at: str = ""
    rows: list[ReconciliationRow] = []


class PlanActualRow(BaseModel):
    patient: str
    service_date: Optional[str] = None
    planned_time: Optional[str] = None
    recorded_time: Optional[str] = None
    tarifziffer_plan: Optional[str] = None
    tarifziffer_actual: Optional[str] = None
    tariff: Optional[str] = None
    planned_minutes: Optional[float] = None
    actual_minutes: Optional[float] = None
    deviation_minutes: Optional[float] = None   # actual - planned (None if one side missing)
    prescription_status: str = ""
    overall_status: str = ""
    status: str = ""
    note: Optional[str] = None


class PlanActualSummary(BaseModel):
    total_rows: int = 0
    green: int = 0
    yellow: int = 0
    red: int = 0
    ok: int = 0
    deviation: int = 0
    minor_deviation: int = 0
    major_deviation: int = 0
    billed_not_planned: int = 0
    planned_not_billed: int = 0
    tariff_mismatch: int = 0
    generated_at: str = ""
    rows: list[PlanActualRow] = []


class CombinedResult(BaseModel):
    prescription: ReconciliationSummary
    plan_actual: Optional[PlanActualSummary] = None
