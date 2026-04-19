from enum import Enum


class ReconciliationStatus(str, Enum):
    WITHIN_LIMIT = "WITHIN_LIMIT"
    NEAR_LIMIT = "NEAR_LIMIT"
    EXCEEDED = "EXCEEDED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    NO_SERVICES = "NO_SERVICES"
    NO_PRESCRIPTION = "NO_PRESCRIPTION"


STATUS_LABELS: dict[ReconciliationStatus, str] = {
    ReconciliationStatus.WITHIN_LIMIT: "✓ Im Rahmen",
    ReconciliationStatus.NEAR_LIMIT: "⚠ Nahe am Limit",
    ReconciliationStatus.EXCEEDED: "✗ Überschritten",
    ReconciliationStatus.OUT_OF_RANGE: "✗ Ausserhalb Zeitraum",
    ReconciliationStatus.NO_SERVICES: "— Keine Leistungen",
    ReconciliationStatus.NO_PRESCRIPTION: "! Keine Verordnung",
}


class PlanActualStatus(str, Enum):
    OK = "OK"
    MINOR_DEVIATION = "MINOR_DEVIATION"
    MAJOR_DEVIATION = "MAJOR_DEVIATION"
    BILLED_NOT_PLANNED = "BILLED_NOT_PLANNED"
    PLANNED_NOT_BILLED = "PLANNED_NOT_BILLED"
    TARIFF_MISMATCH = "TARIFF_MISMATCH"


PLAN_ACTUAL_LABELS: dict[PlanActualStatus, str] = {
    PlanActualStatus.OK: "✓ OK",
    PlanActualStatus.MINOR_DEVIATION: "⚠ Kleine Abweichung",
    PlanActualStatus.MAJOR_DEVIATION: "✗ Grosse Abweichung",
    PlanActualStatus.BILLED_NOT_PLANNED: "✗ Nur verrechnet",
    PlanActualStatus.PLANNED_NOT_BILLED: "! Nur geplant",
    PlanActualStatus.TARIFF_MISMATCH: "✗ Tarifabweichung",
}


class OverallStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


OVERALL_STATUS_LABELS: dict[OverallStatus, str] = {
    OverallStatus.GREEN: "Gruen",
    OverallStatus.YELLOW: "Gelb",
    OverallStatus.RED: "Rot",
}
