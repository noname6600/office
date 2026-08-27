from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.deps import get_current_user
from app.db import get_db
from app.models import Settings, User
from app.templating import templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def view_settings(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings = db.get(Settings, user.id)
    return templates.TemplateResponse(
        request, "settings.html", {"user": user, "settings": settings}
    )


@router.post("")
def update_settings(
    request: Request,
    drive_folder_1: str = Form(...),
    drive_folder_2: str = Form(...),
    sheet_recruit_url: str = Form(...),
    sheet_received_url: str = Form(...),
    sheet_checklist_url: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settings = db.get(Settings, user.id)
    settings.drive_folder_1 = drive_folder_1.strip()
    settings.drive_folder_2 = drive_folder_2.strip()
    settings.sheet_recruit_url = sheet_recruit_url.strip()
    settings.sheet_received_url = sheet_received_url.strip()
    settings.sheet_checklist_url = sheet_checklist_url.strip()
    db.commit()

    return RedirectResponse("/settings?saved=1", status_code=303)
