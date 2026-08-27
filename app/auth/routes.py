import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.oauth import build_flow, upsert_user_from_credentials
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request):
    flow = build_flow()
    state = secrets.token_urlsafe(24)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = flow.code_verifier
    return RedirectResponse(authorization_url)


@router.get("/callback")
def callback(request: Request, code: str, state: str, db: Session = Depends(get_db)):
    expected_state = request.session.pop("oauth_state", None)
    code_verifier = request.session.pop("oauth_code_verifier", None)
    if not expected_state or expected_state != state:
        return RedirectResponse("/?error=invalid_state")

    flow = build_flow(state=state)
    flow.code_verifier = code_verifier
    flow.fetch_token(code=code)

    user = upsert_user_from_credentials(db, flow.credentials)

    request.session["user_id"] = user.id
    return RedirectResponse("/upload")


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")
