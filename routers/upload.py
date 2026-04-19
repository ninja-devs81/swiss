import logging

from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from auth.rbac import get_current_user
from config import settings
from models.enums import (
    ReconciliationStatus,
    STATUS_LABELS,
    PlanActualStatus,
    PLAN_ACTUAL_LABELS,
    OverallStatus,
    OVERALL_STATUS_LABELS,
)
from parser import parse_prescriptions, parse_controlling, parse_planning
from reconciler import reconcile, reconcile_plan_actual
import state

logger = logging.getLogger("spitex.upload")

router = APIRouter(tags=["upload"])
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "error": None},
    )


@router.post("/upload", response_class=HTMLResponse)
async def upload_files(
    request: Request,
    verordnung: UploadFile = File(...),
    controlling: UploadFile = File(...),
    planung: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    try:
        # --- Read files into memory (never touch disk) ---
        vo_bytes = await verordnung.read()
        if len(vo_bytes) > max_bytes:
            raise ValueError(f"Verordnungsdatei zu gross (max {settings.MAX_UPLOAD_MB} MB)")

        ctrl_bytes = await controlling.read()
        if len(ctrl_bytes) > max_bytes:
            raise ValueError(f"Controllingdatei zu gross (max {settings.MAX_UPLOAD_MB} MB)")

        plan_bytes = await planung.read()
        if len(plan_bytes) > max_bytes:
            raise ValueError(f"Planungsdatei zu gross (max {settings.MAX_UPLOAD_MB} MB)")

        # --- Parse ---
        prescriptions_df = parse_prescriptions(vo_bytes)
        controlling_df   = parse_controlling(ctrl_bytes)
        planning_df      = parse_planning(plan_bytes)

        # --- Prescription reconciliation ---
        summary = reconcile(prescriptions_df, controlling_df)

        # --- Plan-vs-actual reconciliation ---
        plan_actual = reconcile_plan_actual(planning_df, controlling_df, prescriptions_df)

        # Store in-memory for download
        state.save_result(user["sub"], summary, plan_actual)

        logger.info(
            "Reconciliation complete: patients=%d exceeded=%d plan_actual_rows=%s",
            summary.total_patients,
            summary.exceeded,
            len(plan_actual.rows),
        )

        return templates.TemplateResponse(
            "results.html",
            {
                "request": request,
                "user": user,
                "summary": summary,
                "plan_actual": plan_actual,
                "status_labels": STATUS_LABELS,
                "plan_actual_labels": PLAN_ACTUAL_LABELS,
                "overall_status_labels": OVERALL_STATUS_LABELS,
                "ReconciliationStatus": ReconciliationStatus,
                "PlanActualStatus": PlanActualStatus,
                "OverallStatus": OverallStatus,
            },
        )

    except ValueError as exc:
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": user, "error": str(exc)},
            status_code=422,
        )

    except Exception as exc:
        logger.exception("Upload processing failed")
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": user, "error": f"Verarbeitungsfehler: {exc}"},
            status_code=500,
        )
