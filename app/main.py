from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.addhoso.routes import router as addhoso_router
from app.auth.routes import router as auth_router
from app.db import init_db
from app.deps import get_current_user
from app.jobs.routes import router as jobs_router
from app.models import User
from app.settings.routes import router as settings_router
from app.templating import templates

app = FastAPI(title="Tra cứu & tải hồ sơ nhân viên")

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET_KEY,
    https_only=config.SESSION_HTTPS_ONLY,
)

app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(jobs_router)
app.include_router(addhoso_router)


@app.on_event("startup")
def on_startup():
    init_db()
    import os

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)


@app.exception_handler(HTTPException)
async def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/")
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/")
def home(request: Request):
    user_id = request.session.get("user_id")
    if user_id:
        return templates.TemplateResponse(request, "upload.html", {})
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/upload")
def upload_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "upload.html", {})
