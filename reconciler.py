import pandas as pd
from collections import Counter
from datetime import datetime
from models.enums import ReconciliationStatus, PlanActualStatus, OverallStatus
from models.schemas import ReconciliationRow, ReconciliationSummary, PlanActualRow, PlanActualSummary


_MINOR_DEVIATION_PCT = 10.0
_MAJOR_DEVIATION_PCT = 25.0


def _status(consumed: float, authorized: float) -> ReconciliationStatus:
    if authorized <= 0:
        return ReconciliationStatus.NO_SERVICES
    pct = consumed / authorized * 100
    if pct >= 100:
        return ReconciliationStatus.EXCEEDED
    if pct >= 80:
        return ReconciliationStatus.NEAR_LIMIT
    return ReconciliationStatus.WITHIN_LIMIT


def _in_period(service_start: datetime | None, service_end: datetime | None, valid_from: datetime | None, valid_to: datetime | None) -> bool:
    if service_start is None:
        return False

    if service_end is None:
        service_end = service_start

    period_start = valid_from
    period_end = valid_to

    if period_start is None and period_end is None:
        return True
    if period_start is None:
        return service_start <= period_end
    if period_end is None:
        return service_end >= period_start

    # Overlap check (inclusive boundaries).
    return service_start <= period_end and service_end >= period_start


def _status_rank(status: str) -> int:
    order = {
        ReconciliationStatus.WITHIN_LIMIT.value: 0,
        ReconciliationStatus.NO_SERVICES.value: 0,
        ReconciliationStatus.NEAR_LIMIT.value: 1,
        ReconciliationStatus.OUT_OF_RANGE.value: 2,
        ReconciliationStatus.EXCEEDED.value: 2,
        ReconciliationStatus.NO_PRESCRIPTION.value: 2,
    }
    return order.get(status, 0)


def _prescription_to_overall(status: str) -> OverallStatus:
    if status in {
        ReconciliationStatus.EXCEEDED.value,
        ReconciliationStatus.NO_PRESCRIPTION.value,
        ReconciliationStatus.OUT_OF_RANGE.value,
    }:
        return OverallStatus.RED
    if status == ReconciliationStatus.NEAR_LIMIT.value:
        return OverallStatus.YELLOW
    return OverallStatus.GREEN


def _detail_to_overall(status: str) -> OverallStatus:
    if status in {
        PlanActualStatus.MAJOR_DEVIATION.value,
        PlanActualStatus.PLANNED_NOT_BILLED.value,
        PlanActualStatus.TARIFF_MISMATCH.value,
    }:
        return OverallStatus.RED
    if status in {
        PlanActualStatus.MINOR_DEVIATION.value,
        PlanActualStatus.BILLED_NOT_PLANNED.value,
    }:
        return OverallStatus.YELLOW
    return OverallStatus.GREEN


def _merge_overall(detail_status: str, prescription_status: str) -> OverallStatus:
    detail = _detail_to_overall(detail_status)
    rx = _prescription_to_overall(prescription_status)
    severity = {
        OverallStatus.GREEN: 0,
        OverallStatus.YELLOW: 1,
        OverallStatus.RED: 2,
    }
    return detail if severity[detail] >= severity[rx] else rx


def _fmt_date(dt: datetime | None) -> str | None:
    return dt.strftime("%d.%m.%Y") if dt else None


def _fmt_time_window(start: datetime | None, end: datetime | None) -> str | None:
    if start is None and end is None:
        return None
    if start and end:
        return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
    if start:
        return start.strftime("%H:%M")
    return end.strftime("%H:%M") if end else None


def _time_overlap(plan_start: datetime | None, plan_end: datetime | None, actual_start: datetime | None, actual_end: datetime | None) -> bool:
    if plan_start is None or plan_end is None or actual_start is None:
        return False
    if actual_end is None:
        actual_end = actual_start
    return actual_start <= plan_end and actual_end >= plan_start


def _choose_prescription_status(
    lookup: dict[str, list[dict]],
    patient_key: str,
    tariff_key: str,
    service_date: datetime | None,
) -> str:
    entries = lookup.get(patient_key, [])
    if not entries:
        return ReconciliationStatus.NO_PRESCRIPTION.value

    if service_date is not None:
        in_period = [
            e for e in entries
            if _in_period(service_date, service_date, e.get("valid_from"), e.get("valid_to"))
        ]
    else:
        in_period = entries

    if not in_period:
        return ReconciliationStatus.NO_PRESCRIPTION.value

    if tariff_key:
        by_tariff = [e for e in in_period if (e.get("tariff_key") or "") == tariff_key]
        if not by_tariff:
            return ReconciliationStatus.NO_PRESCRIPTION.value
        in_period = by_tariff

    return max(in_period, key=lambda e: _status_rank(e.get("status", ""))).get("status", ReconciliationStatus.NO_PRESCRIPTION.value)


def _build_prescription_rows(
    prescriptions_df: pd.DataFrame,
    controlling_df: pd.DataFrame,
) -> tuple[list[ReconciliationRow], dict[str, list[dict]], set[tuple[str, str]]]:
    rows: list[ReconciliationRow] = []
    lookup: dict[str, list[dict]] = {}
    known_prescription_keys: set[tuple[str, str]] = set()

    for _, presc in prescriptions_df.iterrows():
        name_key = presc["patient_key"]
        valid_from = presc["valid_from"]
        valid_to = presc["valid_to"]
        authorized = float(presc["authorized_minutes"])
        tariff_key = str(presc.get("tariff_key") or "").strip()

        patient_ctrl = controlling_df[controlling_df["name_key"] == name_key].copy()
        if tariff_key:
            patient_ctrl = patient_ctrl[patient_ctrl["tariff_key"] == tariff_key]

        in_range_mask = patient_ctrl.apply(
            lambda r: _in_period(r.get("service_start"), r.get("service_end"), valid_from, valid_to),
            axis=1,
        ) if not patient_ctrl.empty else pd.Series([], dtype=bool)

        period_services = patient_ctrl[in_range_mask] if not patient_ctrl.empty else patient_ctrl
        out_of_range_services = patient_ctrl[~in_range_mask] if not patient_ctrl.empty else patient_ctrl

        consumed = float(period_services["duration_min"].sum()) if not period_services.empty else 0.0
        out_of_range_min = float(out_of_range_services["duration_min"].sum()) if not out_of_range_services.empty else 0.0
        out_of_range_cnt = len(out_of_range_services)
        remaining = max(0.0, authorized - consumed)
        pct = round(consumed / authorized * 100, 1) if authorized > 0 else None
        status = _status(consumed, authorized)

        reasons = []
        if authorized > 0 and consumed >= authorized:
            reasons.append(f"Zeitüberschreitung: {consumed:.0f} von {authorized:.0f} Min. verbraucht")
        if out_of_range_cnt > 0:
            reasons.append(f"Ausserhalb Gültigkeitszeitraum: {out_of_range_cnt} Leistung(en), {out_of_range_min:.0f} Min.")
        refusal_reason = " | ".join(reasons) if reasons else None

        known_prescription_keys.add((name_key, tariff_key))
        lookup.setdefault(name_key, []).append(
            {
                "tariff_key": tariff_key,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "status": status.value,
            }
        )

        rows.append(
            ReconciliationRow(
                patient=presc["patient_display"],
                geburtsdatum=presc.get("dob_display"),
                tarifcode=str(presc.get("Tarifcode", "") or ""),
                tarifziffer=str(presc.get("Tarifziffer", "") or ""),
                valid_from=_fmt_date(valid_from),
                valid_to=_fmt_date(valid_to),
                authorized_minutes=authorized,
                consumed_minutes=consumed,
                remaining_minutes=remaining,
                utilization_pct=pct,
                status=status.value,
                service_count=len(period_services),
                refusal_reason=refusal_reason,
                out_of_range_count=out_of_range_cnt,
                out_of_range_minutes=out_of_range_min,
            )
        )

    unmatched = controlling_df[
        ~controlling_df.apply(
            lambda r: (r.get("name_key", ""), r.get("tariff_key", "")) in known_prescription_keys,
            axis=1,
        )
    ]

    for (_, _), grp in unmatched.groupby(["name_key", "tariff_key"], dropna=False):
        consumed = float(grp["duration_min"].sum())
        rows.append(
            ReconciliationRow(
                patient=str(grp.iloc[0].get("patient_display") or grp.iloc[0].get("Klient") or grp.iloc[0]["name_key"]),
                geburtsdatum=None,
                tarifcode=None,
                tarifziffer=str(grp.iloc[0].get("tariff_key") or "") or None,
                valid_from=None,
                valid_to=None,
                authorized_minutes=0,
                consumed_minutes=consumed,
                remaining_minutes=0,
                utilization_pct=None,
                status=ReconciliationStatus.NO_PRESCRIPTION.value,
                service_count=len(grp),
                refusal_reason="Keine passende Verordnung für Patient/Tarif gefunden",
            )
        )

    return rows, lookup, known_prescription_keys


def reconcile(prescriptions_df: pd.DataFrame, controlling_df: pd.DataFrame) -> ReconciliationSummary:
    rows, _, _ = _build_prescription_rows(prescriptions_df, controlling_df)

    status_counts = Counter(r.status for r in rows)

    return ReconciliationSummary(
        total_patients=len(set(r.patient for r in rows)),
        total_prescriptions=len([r for r in rows if r.status != ReconciliationStatus.NO_PRESCRIPTION.value]),
        within_limit=status_counts[ReconciliationStatus.WITHIN_LIMIT.value],
        near_limit=status_counts[ReconciliationStatus.NEAR_LIMIT.value],
        exceeded=status_counts[ReconciliationStatus.EXCEEDED.value],
        out_of_range=status_counts[ReconciliationStatus.OUT_OF_RANGE.value],
        no_services=status_counts[ReconciliationStatus.NO_SERVICES.value],
        no_prescription=status_counts[ReconciliationStatus.NO_PRESCRIPTION.value],
        generated_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
        rows=rows,
    )


# ---------------------------------------------------------------------------
# Plan-vs-Actual reconciliation
# Matches each planning row against controlling by patient + date + time overlap.
# ---------------------------------------------------------------------------

def reconcile_plan_actual(
    planning_df: pd.DataFrame,
    controlling_df: pd.DataFrame,
    prescriptions_df: pd.DataFrame,
) -> PlanActualSummary:

    pa_rows: list[PlanActualRow] = []
    matched_ctrl_idx: set = set()
    _, rx_lookup, _ = _build_prescription_rows(prescriptions_df, controlling_df)

    for _, plan in planning_df.iterrows():
        name_key = plan["name_key"]
        patient_id = str(plan.get("patient_id") or "").strip()
        plan_date = plan["plan_date"]
        plan_start = plan.get("plan_start")
        plan_end = plan.get("plan_end")
        plan_min = float(plan.get("plan_min") or 0)
        if plan_min <= 0 and plan_start and plan_end:
            plan_min = round(max(0.0, (plan_end - plan_start).total_seconds() / 60.0), 2)

        tariff_p = str(plan.get("tariff_key") or plan.get("tarifziffer") or "").strip()
        plan_date_display = _fmt_date(plan_date)
        plan_time_display = _fmt_time_window(plan_start, plan_end)

        if patient_id:
            patient_mask = (controlling_df["patient_id"] == patient_id) | (controlling_df["name_key"] == name_key)
        else:
            patient_mask = controlling_df["name_key"] == name_key

        candidates = controlling_df[patient_mask]

        if plan_start and plan_end:
            matches = candidates[candidates.apply(
                lambda r: _time_overlap(plan_start, plan_end, r.get("service_start"), r.get("service_end")),
                axis=1,
            )]
        else:
            matches = candidates[candidates["service_date"].apply(
                lambda d: d is not None and plan_date is not None and d == plan_date
            )]

        prescription_status = _choose_prescription_status(rx_lookup, name_key, tariff_p, plan_date)

        if matches.empty:
            detail_status = PlanActualStatus.PLANNED_NOT_BILLED.value
            overall = _merge_overall(detail_status, prescription_status)
            pa_rows.append(
                PlanActualRow(
                    patient=str(plan.get("patient_col") or name_key),
                    service_date=plan_date_display,
                    planned_time=plan_time_display,
                    recorded_time=None,
                    tarifziffer_plan=tariff_p or None,
                    tarifziffer_actual=None,
                    tariff=tariff_p or None,
                    planned_minutes=plan_min if plan_min > 0 else None,
                    actual_minutes=None,
                    deviation_minutes=None,
                    prescription_status=prescription_status,
                    overall_status=overall.value,
                    status=detail_status,
                    note="Kein überlappender Ist-Einsatz gefunden",
                )
            )
            continue

        matched_ctrl_idx.update(matches.index.tolist())

        actual_min = float(matches["duration_min"].sum())
        deviation = round(actual_min - plan_min, 1) if plan_min > 0 else None

        actual_tariffs = sorted({str(t).strip() for t in matches["tariff_key"].tolist() if str(t).strip()})
        actual_tariff_display = ", ".join(actual_tariffs) if actual_tariffs else None

        tariff_mismatch = bool(tariff_p and actual_tariffs and any(t != tariff_p for t in actual_tariffs))
        deviation_pct = abs(deviation) / plan_min * 100 if (deviation is not None and plan_min > 0) else 0.0

        if tariff_mismatch:
            detail_status = PlanActualStatus.TARIFF_MISMATCH.value
            note = "Tarif stimmt zwischen Planung und Ist nicht überein"
        elif deviation_pct > _MAJOR_DEVIATION_PCT:
            detail_status = PlanActualStatus.MAJOR_DEVIATION.value
            note = f"Grosse Zeitabweichung ({deviation_pct:.1f}%)"
        elif deviation_pct > _MINOR_DEVIATION_PCT:
            detail_status = PlanActualStatus.MINOR_DEVIATION.value
            note = f"Kleine Zeitabweichung ({deviation_pct:.1f}%)"
        else:
            detail_status = PlanActualStatus.OK.value
            note = None

        recorded_start = min([d for d in matches["service_start"].tolist() if d is not None], default=None)
        recorded_end = max([d for d in matches["service_end"].tolist() if d is not None], default=None)

        overall = _merge_overall(detail_status, prescription_status)

        pa_rows.append(
            PlanActualRow(
                patient=str(plan.get("patient_col") or name_key),
                service_date=plan_date_display,
                planned_time=plan_time_display,
                recorded_time=_fmt_time_window(recorded_start, recorded_end),
                tarifziffer_plan=tariff_p or None,
                tarifziffer_actual=actual_tariff_display,
                tariff=tariff_p or actual_tariff_display,
                planned_minutes=plan_min if plan_min > 0 else None,
                actual_minutes=actual_min,
                deviation_minutes=deviation,
                prescription_status=prescription_status,
                overall_status=overall.value,
                status=detail_status,
                note=note,
            )
        )

    unplanned = controlling_df[~controlling_df.index.isin(matched_ctrl_idx)]
    for _, row in unplanned.iterrows():
        row_date = row.get("service_date")
        row_tariff = str(row.get("tariff_key") or "").strip()
        prescription_status = _choose_prescription_status(
            rx_lookup,
            str(row.get("name_key") or ""),
            row_tariff,
            row_date,
        )

        detail_status = PlanActualStatus.BILLED_NOT_PLANNED.value
        overall = _merge_overall(detail_status, prescription_status)

        pa_rows.append(
            PlanActualRow(
                patient=str(row.get("patient_display") or row.get("Klient") or row.get("name_key")),
                service_date=_fmt_date(row_date),
                planned_time=None,
                recorded_time=_fmt_time_window(row.get("service_start"), row.get("service_end")),
                tarifziffer_plan=None,
                tarifziffer_actual=row_tariff or None,
                tariff=row_tariff or None,
                planned_minutes=None,
                actual_minutes=float(row.get("duration_min") or 0),
                deviation_minutes=None,
                prescription_status=prescription_status,
                overall_status=overall.value,
                status=detail_status,
                note="Verrechnet ohne passenden Plan-Einsatz",
            )
        )

    sc = Counter(r.status for r in pa_rows)
    oc = Counter(r.overall_status for r in pa_rows)
    deviation_total = sc[PlanActualStatus.MINOR_DEVIATION.value] + sc[PlanActualStatus.MAJOR_DEVIATION.value]

    return PlanActualSummary(
        total_rows=len(pa_rows),
        green=oc[OverallStatus.GREEN.value],
        yellow=oc[OverallStatus.YELLOW.value],
        red=oc[OverallStatus.RED.value],
        ok=sc[PlanActualStatus.OK.value],
        deviation=deviation_total,
        minor_deviation=sc[PlanActualStatus.MINOR_DEVIATION.value],
        major_deviation=sc[PlanActualStatus.MAJOR_DEVIATION.value],
        billed_not_planned=sc[PlanActualStatus.BILLED_NOT_PLANNED.value],
        planned_not_billed=sc[PlanActualStatus.PLANNED_NOT_BILLED.value],
        tariff_mismatch=sc[PlanActualStatus.TARIFF_MISMATCH.value],
        generated_at=datetime.now().strftime("%d.%m.%Y %H:%M"),
        rows=pa_rows,
    )
