from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response, RedirectResponse

from auth.rbac import get_current_user
from reporter import generate_report, generate_csv_report
import state

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/download")
async def download_report(user: dict = Depends(get_current_user)):
    result = state.get_result(user["sub"])
    if result is None:
        return RedirectResponse("/dashboard", status_code=303)

    report_bytes = generate_report(result.prescription, result.plan_actual)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"Spitex_Reconciliation_{timestamp}.xlsx"

    return Response(
        content=report_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download/csv")
async def download_report_csv(user: dict = Depends(get_current_user)):
    result = state.get_result(user["sub"])
    if result is None:
        return RedirectResponse("/dashboard", status_code=303)

    csv_bytes = generate_csv_report(result.prescription, result.plan_actual)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"Spitex_Reconciliation_{timestamp}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
