# Spitex Reconciliation Platform

A secure Python web application for automated service controlling and reconciliation in Swiss home care (Spitex) organizations.

## What it does

Uploads two files and automatically:
- Matches patients across **Verordnung** (prescriptions) and **Leistungen Controlling** (services)
- Calculates consumed vs. authorized service minutes within each prescription validity period
- Flags patients as: **Im Rahmen** / **Nahe Limit (≥80%)** / **Überschritten** / **Keine Leistungen** / **Keine Verordnung**
- Generates a downloadable **Excel report** with summary sheet + detail rows
- All processing is **in-memory** — no patient data is written to disk

---

## Quick Start

```bash
chmod +x setup.sh && ./setup.sh
source .venv/bin/activate
python main.py
```

Open: http://localhost:8000

Default login: `admin` / `secret` — **change this before production use**

---

## Setting Up Users

Edit `.env` and replace the `USERS_JSON` value:

```bash
# Generate a bcrypt hash for a password:
python3 -c "from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt']); print(c.hash('yourpassword'))"
```

Then update `.env`:
```
USERS_JSON=[{"username":"admin","password":"$2b$12$YOUR_HASH_HERE","role":"admin"},{"username":"reviewer","password":"$2b$12$ANOTHER_HASH","role":"viewer"}]
```

---

## File Formats

### Verordnung (CSV, semicolon-delimited)
Required columns:
- `Name Patient`, `Vorname Patient`, `Geburtsdatum`
- `Gültig von Datum`, `Gültig bis Datum`
- `Tarifcode`, `Tarifziffer`
- `Anz. verordnete Minuten`

### Leistungen Controlling (Excel .xlsx)
Required columns:
- `Klient` (format: "Nachname Vorname" or "Nachname, Vorname")
- `Beginn` (date/datetime)
- `Dauer` (minutes as integer, or HH:MM format)

---

## Patient Matching

Patients are matched by normalized **Nachname + Vorname** (case-insensitive, whitespace-normalized).

The Controlling file's `Klient` field is split into Nachname/Vorname and matched against the Verordnung's `Name Patient` + `Vorname Patient`.

**Important**: Ensure name spelling is consistent across both files.

---

## Status Classifications

| Status | Meaning |
|--------|---------|
| ✓ Im Rahmen | < 80% of authorized minutes consumed |
| ⚠ Nahe am Limit | 80–99% consumed |
| ✗ Überschritten | ≥ 100% consumed |
| — Keine Leistungen | Prescription exists but 0 minutes recorded |
| ! Keine Verordnung | Services recorded but no matching prescription |

---

## Project Structure

```
spitex/
├── main.py               # FastAPI app entry point
├── config.py             # Settings from .env
├── state.py              # In-memory result store
├── requirements.txt
├── .env.example
├── auth/
│   └── rbac.py           # JWT auth + cookie sessions
├── models/
│   ├── enums.py          # Status enums
│   └── schemas.py        # Pydantic data models
├── routers/
│   ├── auth.py           # Login/logout endpoints
│   ├── upload.py         # File upload + reconciliation
│   └── reports.py        # Excel report download
├── services/
│   ├── parser.py         # Excel/CSV ingestion + normalization
│   ├── reconciler.py     # Core matching logic
│   └── reporter.py       # Excel report generation
└── templates/
    ├── login.html        # Login page
    ├── dashboard.html    # File upload dashboard
    └── results.html      # Results table + download
```

---

## Security Notes

- Passwords are bcrypt-hashed — never store plaintext
- Sessions use httponly cookies (JWT)
- Files are processed in memory and never written to disk
- For production: use HTTPS (nginx reverse proxy with TLS)
- For production: set `SECRET_KEY` to a strong random value in `.env`
- For production: host in a Swiss-compliant environment (e.g., Exoscale CH, Nine.ch)

---

## Production Deployment (Swiss hosting)

```bash
# Install gunicorn
pip install gunicorn

# Run with multiple workers
gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Put nginx in front with TLS termination and a Swiss SSL certificate.
