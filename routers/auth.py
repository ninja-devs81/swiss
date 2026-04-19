from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from auth.rbac import authenticate_user, create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_user(username, password)
    if not user:
        # Re-render login page with error via redirect + flash
        from fastapi.responses import HTMLResponse
        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="templates")
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Ungültige Anmeldedaten"},
            status_code=401,
        )

    token = create_token(user["username"], user["role"])
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="strict",
        max_age=7200,
        # secure=True,  # Enable in production with HTTPS
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response
