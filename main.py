import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from routers import auth, upload, reports
from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title=settings.APP_TITLE,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(reports.router)

templates = Jinja2Templates(directory="templates")


@app.exception_handler(HTTPException)
async def redirect_on_auth_error(request: Request, exc: HTTPException):
    """Redirect to login page on 303 (unauthenticated) or 401."""
    if exc.status_code in (303, 401):
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse(content=str(exc.detail), status_code=exc.status_code)


@app.get("/", include_in_schema=False)
async def root(request: Request):
    return RedirectResponse("/dashboard")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
