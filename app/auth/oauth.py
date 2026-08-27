import datetime

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app import config, crypto
from app.models import OAuthToken, Settings, User

USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    *config.DRIVE_SCOPES,
]


def build_flow(state: str | None = None) -> Flow:
    client_config = {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [config.GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=OAUTH_SCOPES,
        state=state,
        redirect_uri=config.GOOGLE_REDIRECT_URI,
    )


def fetch_userinfo(access_token: str) -> dict:
    resp = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def upsert_user_from_credentials(db: Session, credentials: Credentials) -> User:
    info = fetch_userinfo(credentials.token)
    google_sub = info["sub"]
    email = info.get("email", "")

    user = db.query(User).filter_by(google_sub=google_sub).one_or_none()
    if user is None:
        user = User(google_sub=google_sub, email=email)
        db.add(user)
        db.flush()

        db.add(
            Settings(
                user_id=user.id,
                drive_folder_1=config.DEFAULT_DRIVE_FOLDER_1,
                drive_folder_2=config.DEFAULT_DRIVE_FOLDER_2,
                sheet_recruit_url=config.DEFAULT_SHEET_RECRUIT_URL,
                sheet_received_url=config.DEFAULT_SHEET_RECEIVED_URL,
                sheet_checklist_url=config.DEFAULT_SHEET_CHECKLIST_URL,
            )
        )
    else:
        user.email = email

    save_token(db, user, credentials)
    db.commit()
    return user


def save_token(db: Session, user: User, credentials: Credentials) -> None:
    token_row = db.query(OAuthToken).filter_by(user_id=user.id).one_or_none()
    if token_row is None:
        token_row = OAuthToken(user_id=user.id)
        db.add(token_row)

    token_row.access_token_enc = crypto.encrypt(credentials.token)
    token_row.refresh_token_enc = (
        crypto.encrypt(credentials.refresh_token) if credentials.refresh_token else token_row.refresh_token_enc
    )
    token_row.expiry = credentials.expiry
    token_row.scope = " ".join(credentials.scopes or [])


def get_credentials_for_user(db: Session, user: User) -> Credentials:
    token_row = db.query(OAuthToken).filter_by(user_id=user.id).one_or_none()
    if token_row is None:
        raise RuntimeError("Người dùng chưa đăng nhập Google.")

    credentials = Credentials(
        token=crypto.decrypt(token_row.access_token_enc),
        refresh_token=crypto.decrypt(token_row.refresh_token_enc) if token_row.refresh_token_enc else None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        scopes=(token_row.scope or "").split(),
        expiry=token_row.expiry,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())
        save_token(db, user, credentials)
        db.commit()

    return credentials
