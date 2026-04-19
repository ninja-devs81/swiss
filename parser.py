import io
import re
from datetime import date, datetime, time, timedelta
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIME_FORMATS = (
    "%H:%M:%S",
    "%H:%M",
)

_DATETIME_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%Y%m%d",
)

_LEISTUNG_NR_TO_TARIFF = {
    "11000": "53201",
    "11100": "53202",
    "11200": "53203",
}


def _normalize_name(val: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", str(val).lower().strip())


def _normalize_col_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().rstrip("'").lower())


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    normalized = {_normalize_col_name(c): c for c in df.columns}
    for cand in candidates:
        key = _normalize_col_name(cand)
        if key in normalized:
            return normalized[key]

    # Soft fallback: substring match for slightly different exports.
    for cand in candidates:
        key = _normalize_col_name(cand)
        for norm, original in normalized.items():
            if key in norm:
                return original
    return None


def _is_missing(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    s = str(val).strip().lower()
    return s in {"", "nan", "none", "nat"}


def _parse_date(val) -> Optional[datetime]:
    dt = _parse_datetime(val)
    if dt is None:
        return None
    return datetime(dt.year, dt.month, dt.day)


def _parse_datetime(val) -> Optional[datetime]:
    if _is_missing(val):
        return None

    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)

    s = str(val).strip()
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue

    parsed = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime()
    return None


def _parse_time(val) -> Optional[time]:
    if _is_missing(val):
        return None
    if isinstance(val, datetime):
        return val.time()
    if isinstance(val, time):
        return val

    s = str(val).strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue

    parsed = pd.to_datetime(s, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().time()


def _combine_date_and_time(date_val, time_val) -> Optional[datetime]:
    d = _parse_date(date_val)
    t = _parse_time(time_val)
    if d is None or t is None:
        return None
    return datetime.combine(d.date(), t)


def _parse_duration_minutes(val) -> float:
    """
    Accept HH:MM, HH:MM:SS, plain int/float (minutes), or decimal notation.
    Returns float minutes.
    """
    if _is_missing(val):
        return 0.0

    s = str(val).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                h = int(parts[0])
                m = int(parts[1])
                return float(h * 60 + m)
            if len(parts) == 3:
                h = int(parts[0])
                m = int(parts[1])
                sec = int(parts[2])
                return float(h * 60 + m + (sec / 60.0))
        except ValueError:
            return 0.0

    try:
        return float(s.replace(",", "."))
    except ValueError:
        return 0.0


def _normalize_number_string(s: str) -> str:
    v = s.strip().replace(",", ".")
    if re.fullmatch(r"\d+(\.0+)?", v):
        return str(int(float(v)))
    return v


def _map_klv_tariff_from_text(text: str) -> str:
    u = str(text or "").upper()
    if "KLV-A" in u or "KLV A" in u:
        return "53201"
    if "KLV-B" in u or "KLV B" in u:
        return "53202"
    if "KLV-C" in u or "KLV C" in u:
        return "53203"
    return ""


def _normalize_tariff(code_val, text_fallback=None) -> str:
    if not _is_missing(code_val):
        raw = _normalize_number_string(str(code_val))
        mapped = _LEISTUNG_NR_TO_TARIFF.get(raw)
        if mapped:
            return mapped
        klv = _map_klv_tariff_from_text(raw)
        if klv:
            return klv
        return raw.strip().upper()

    klv = _map_klv_tariff_from_text(str(text_fallback or ""))
    if klv:
        return klv
    return ""


def _split_klient(klient: str):
    """
    Try to split 'Nachname Vorname' or 'Nachname, Vorname'.
    Returns (nachname, vorname).
    """
    s = str(klient).strip()
    if "," in s:
        parts = s.split(",", 1)
        return parts[0].strip(), parts[1].strip()

    parts = s.split()
    if len(parts) >= 2:
        # Keep this tolerant because exports vary between "Vorname Nachname"
        # and "Nachname Vorname". name_key canonicalization handles the order.
        return parts[0].strip(), " ".join(parts[1:]).strip()

    return s, ""


def _name_key(nachname: str, vorname: str) -> str:
    # Canonical key independent from "first last" vs "last first" ordering.
    parts = sorted([_normalize_name(nachname), _normalize_name(vorname)])
    return "|".join(parts)


def _ensure_end_after_start(start_dt: Optional[datetime], end_dt: Optional[datetime]) -> Optional[datetime]:
    if start_dt and end_dt and end_dt < start_dt:
        return end_dt + timedelta(days=1)
    return end_dt


def _resolve_patient_id(df: pd.DataFrame) -> pd.Series:
    id_col = _find_col(df, ["Kli-Nr", "Klient-Nr", "Patient ID", "PatientID", "Klient ID", "ID"])
    if id_col:
        return df[id_col].astype(str).str.strip()
    return pd.Series([""] * len(df), index=df.index)


def _row_has_col_token(values: list[str], candidates: list[str]) -> bool:
    for value in values:
        norm = _normalize_col_name(value)
        padded = f" {norm} "
        for cand in candidates:
            key = _normalize_col_name(cand)
            if not key:
                continue
            if norm == key:
                return True
            if padded.startswith(f" {key} ") or padded.endswith(f" {key} ") or f" {key} " in padded:
                return True
    return False


def _row_looks_like_controlling_header(row_values: list[str]) -> bool:
    values = [str(v).strip() for v in row_values if not _is_missing(v)]
    if len(values) < 3:
        return False

    has_patient = _row_has_col_token(values, ["Klient", "Patient", "Name Patient", "Name"])
    has_begin_or_date = _row_has_col_token(
        values,
        ["Beginn", "Start", "Leistungsbeginn", "Beginnzeit", "Datum", "Einsatzdatum", "Leistungsdatum"],
    )
    has_end_or_duration = _row_has_col_token(
        values,
        ["Ende", "Leistungsende", "Endzeit", "Dauer", "Minuten", "Dauer (Min.)", "Zeitdauer"],
    )
    return has_patient and has_begin_or_date and has_end_or_duration


def _promote_controlling_header_row(df: pd.DataFrame, max_scan_rows: int = 25) -> pd.DataFrame:
    scan_rows = min(max_scan_rows, len(df))
    for idx in range(scan_rows):
        row = df.iloc[idx].tolist()
        if not _row_looks_like_controlling_header(row):
            continue

        header = []
        for col_idx, val in enumerate(row):
            if _is_missing(val):
                header.append(f"Unnamed: {col_idx}")
            else:
                header.append(str(val).strip())

        promoted = df.iloc[idx + 1 :].copy()
        promoted.columns = header
        promoted = promoted.dropna(how="all")
        return promoted

    return df


def _looks_like_generated_reconciliation_report(df: pd.DataFrame) -> bool:
    normalized_cols = [_normalize_col_name(c) for c in df.columns]
    if any("reconciliation report" in c for c in normalized_cols):
        return True
    if any("spitex leistungskontrolle" in c for c in normalized_cols):
        return True
    return _find_col(df, ["Kennzahl"]) is not None and _find_col(df, ["Anzahl"]) is not None


# ---------------------------------------------------------------------------
# Prescription parser  (CSV semicolon-delimited)
# ---------------------------------------------------------------------------

def parse_prescriptions(file_bytes: bytes) -> pd.DataFrame:
    # Try semicolon CSV first (as declared by user), then Excel fallback.
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), sep=";", dtype=str, encoding="utf-8-sig")
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=";", dtype=str, encoding="latin-1")
        except Exception:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)

    # Normalize column names: strip whitespace + trailing apostrophes.
    df.columns = [str(c).strip().rstrip("'").strip() for c in df.columns]

    required = [
        "Name Patient",
        "Vorname Patient",
        "Geburtsdatum",
        "Gültig von Datum",
        "Gültig bis Datum",
        "Tarifcode",
        "Tarifziffer",
        "Anz. verordnete Minuten",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Verordnung: fehlende Spalten: {missing}\nGefundene Spalten: {list(df.columns)}")

    df["patient_key"] = df.apply(lambda r: _name_key(r["Name Patient"], r["Vorname Patient"]), axis=1)
    df["valid_from"] = df["Gültig von Datum"].apply(_parse_date)
    df["valid_to"] = df["Gültig bis Datum"].apply(_parse_date)
    df["authorized_minutes"] = pd.to_numeric(df["Anz. verordnete Minuten"], errors="coerce").fillna(0)
    df["patient_display"] = df["Vorname Patient"].astype(str).str.strip() + " " + df["Name Patient"].astype(str).str.strip()
    df["dob_display"] = df["Geburtsdatum"].astype(str).str.strip().str.split(" ").str[0]
    df["tariff_key"] = df.apply(
        lambda r: _normalize_tariff(r.get("Tarifziffer"), r.get("Tarifcode")),
        axis=1,
    )

    return df


# ---------------------------------------------------------------------------
# Controlling parser  (Excel / CSV)
# ---------------------------------------------------------------------------

def parse_controlling(file_bytes: bytes) -> pd.DataFrame:
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    except Exception:
        # Fallbacks for alternate exports.
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=";", dtype=str, encoding="utf-8-sig")
        except Exception:
            df = pd.read_csv(io.BytesIO(file_bytes), sep="\t", dtype=str, encoding="utf-8-sig")

    df.columns = [str(c).strip() for c in df.columns]
    df = _promote_controlling_header_row(df)
    df.columns = [str(c).strip() for c in df.columns]

    patient_col = _find_col(df, ["Klient", "Patient", "Name Patient", "Name"]) 
    begin_col = _find_col(df, ["Beginn", "Start", "Von", "Leistungsbeginn", "Beginnzeit"])
    end_col = _find_col(df, ["Ende", "Bis", "Leistungsende", "Endzeit"])
    date_col = _find_col(df, ["Datum", "Einsatzdatum", "Leistungsdatum"])
    start_time_col = _find_col(df, ["Startzeit", "Von", "Uhrzeit von"])
    end_time_col = _find_col(df, ["Endzeit", "Bis", "Uhrzeit bis"])
    duration_col = _find_col(df, ["Dauer", "Minuten", "Dauer (Min.)", "Zeitdauer"])

    tariff_col = _find_col(df, ["Tarifziffer", "Tarif", "Tarifcode", "Leistung-Nr", "Leistung Nr", "Leistungscode"])
    tariff_text_col = _find_col(df, ["Leistung", "Leistungsart", "Tariftext"])

    missing = []
    if patient_col is None:
        missing.append("Klient/Patient")
    if begin_col is None and date_col is None:
        missing.append("Beginn oder Datum")
    if end_col is None and duration_col is None and end_time_col is None:
        missing.append("Ende oder Dauer")
    if missing:
        if _looks_like_generated_reconciliation_report(df):
            raise ValueError(
                "Controlling: Es wurde offenbar der exportierte Reconciliation-Report hochgeladen. "
                "Bitte bei 'Leistungen Controlling' die Originaldatei mit Spalten wie "
                "Klient, Beginn/Datum und Ende oder Dauer hochladen."
            )
        raise ValueError(f"Controlling: fehlende Spalten: {missing}\nGefundene Spalten: {list(df.columns)}")

    name_parts = df[patient_col].apply(_split_klient)
    df["nachname"] = name_parts.apply(lambda x: x[0])
    df["vorname"] = name_parts.apply(lambda x: x[1])
    df["name_key"] = df.apply(lambda r: _name_key(r["nachname"], r["vorname"]), axis=1)
    df["patient_display"] = df[patient_col].astype(str).str.strip()
    df["patient_id"] = _resolve_patient_id(df)

    starts: list[Optional[datetime]] = []
    ends: list[Optional[datetime]] = []
    durations: list[float] = []
    tariff_keys: list[str] = []

    for _, row in df.iterrows():
        start_dt = _parse_datetime(row.get(begin_col)) if begin_col else None
        if start_dt is None and date_col and start_time_col:
            start_dt = _combine_date_and_time(row.get(date_col), row.get(start_time_col))
        if start_dt is None and date_col:
            start_dt = _parse_date(row.get(date_col))

        end_dt = _parse_datetime(row.get(end_col)) if end_col else None
        if end_dt is None and date_col and end_time_col:
            end_dt = _combine_date_and_time(row.get(date_col), row.get(end_time_col))

        duration_min = _parse_duration_minutes(row.get(duration_col)) if duration_col else 0.0

        if end_dt is None and start_dt is not None and duration_min > 0:
            end_dt = start_dt + timedelta(minutes=duration_min)

        end_dt = _ensure_end_after_start(start_dt, end_dt)

        if duration_min <= 0 and start_dt and end_dt:
            duration_min = max(0.0, (end_dt - start_dt).total_seconds() / 60.0)

        tariff_keys.append(_normalize_tariff(row.get(tariff_col), row.get(tariff_text_col)))
        starts.append(start_dt)
        ends.append(end_dt)
        durations.append(round(duration_min, 2))

    df["service_start"] = starts
    df["service_end"] = ends
    df["service_date"] = df["service_start"].apply(lambda v: datetime(v.year, v.month, v.day) if v else None)
    df["service_end_date"] = df["service_end"].apply(lambda v: datetime(v.year, v.month, v.day) if v else None)
    df["duration_min"] = durations
    df["tariff_key"] = tariff_keys
    df["tarifziffer"] = df["tariff_key"]

    return df


# ---------------------------------------------------------------------------
# Planning / Einsatzplanung parser  (Excel / CSV)
# ---------------------------------------------------------------------------

def parse_planning(file_bytes: bytes) -> pd.DataFrame:
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=";", dtype=str, encoding="utf-8-sig")
        except Exception:
            df = pd.read_csv(io.BytesIO(file_bytes), sep=",", dtype=str, encoding="utf-8-sig")

    df.columns = [str(c).strip() for c in df.columns]

    patient_col = _find_col(df, ["Klient", "Patient", "Name Patient", "Name", "Kunde", "Titel", "Betreff"])
    start_col = _find_col(df, ["Beginn", "Start", "Von", "Geplanter Beginn", "Einsatzbeginn"])
    end_col = _find_col(df, ["Ende", "Bis", "Geplantes Ende", "Einsatzende"])
    date_col = _find_col(df, ["Datum", "Einsatzdatum", "Geplant am", "Startdatum"])
    start_time_col = _find_col(df, ["Startzeit", "Von", "Uhrzeit von"])
    end_time_col = _find_col(df, ["Endzeit", "Bis", "Uhrzeit bis"])
    duration_col = _find_col(df, ["Dauer", "Minuten", "Zeit", "Geplante Dauer", "Geplante Minuten"])

    tariff_col = _find_col(df, ["Tarifziffer", "Tarif", "Tarifcode", "Leistung", "Leistung-Nr", "Leistungsart"])
    tariff_text_col = _find_col(df, ["Leistung", "Leistungsart", "Tariftext"])

    missing = []
    if patient_col is None:
        missing.append("Klient/Patient/Name")
    if start_col is None and date_col is None:
        missing.append("Beginn/Start oder Datum")
    if end_col is None and duration_col is None and end_time_col is None:
        missing.append("Ende oder Dauer")
    if missing:
        raise ValueError(f"Planung: fehlende Spalten: {missing}\nGefundene Spalten: {list(df.columns)}")

    name_parts = df[patient_col].apply(_split_klient)
    df["nachname"] = name_parts.apply(lambda x: x[0])
    df["vorname"] = name_parts.apply(lambda x: x[1])
    df["name_key"] = df.apply(lambda r: _name_key(r["nachname"], r["vorname"]), axis=1)
    df["patient_col"] = df[patient_col].astype(str).str.strip()
    df["patient_id"] = _resolve_patient_id(df)

    starts: list[Optional[datetime]] = []
    ends: list[Optional[datetime]] = []
    durations: list[float] = []
    plan_dates: list[Optional[datetime]] = []
    tariff_keys: list[str] = []

    for _, row in df.iterrows():
        plan_start = _parse_datetime(row.get(start_col)) if start_col else None
        if plan_start is None and date_col and start_time_col:
            plan_start = _combine_date_and_time(row.get(date_col), row.get(start_time_col))
        if plan_start is None and date_col:
            plan_start = _parse_date(row.get(date_col))

        plan_end = _parse_datetime(row.get(end_col)) if end_col else None
        if plan_end is None and date_col and end_time_col:
            plan_end = _combine_date_and_time(row.get(date_col), row.get(end_time_col))

        plan_min = _parse_duration_minutes(row.get(duration_col)) if duration_col else 0.0

        if plan_end is None and plan_start is not None and plan_min > 0:
            plan_end = plan_start + timedelta(minutes=plan_min)

        plan_end = _ensure_end_after_start(plan_start, plan_end)

        if plan_min <= 0 and plan_start and plan_end:
            plan_min = max(0.0, (plan_end - plan_start).total_seconds() / 60.0)

        plan_date = datetime(plan_start.year, plan_start.month, plan_start.day) if plan_start else _parse_date(row.get(date_col))

        starts.append(plan_start)
        ends.append(plan_end)
        durations.append(round(plan_min, 2))
        plan_dates.append(plan_date)
        tariff_keys.append(_normalize_tariff(row.get(tariff_col), row.get(tariff_text_col)))

    df["plan_start"] = starts
    df["plan_end"] = ends
    df["plan_date"] = plan_dates
    df["plan_min"] = durations
    df["tariff_key"] = tariff_keys
    df["tarifziffer"] = df["tariff_key"]

    return df
