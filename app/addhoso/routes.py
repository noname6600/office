import os

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app import config
from app.addhoso import logic
from app.auth.oauth import get_credentials_for_user
from app.db import get_db
from app.deps import get_current_user
from app.jobs import sheets
from app.jobs.textnorm import cccd_key, locate_header_row
from app.models import AddSession, Settings, User
from app.templating import templates

router = APIRouter(prefix="/addhoso", tags=["addhoso"])


def _session_upload_dir(session_id: int) -> str:
    path = os.path.join(config.UPLOAD_DIR, "addsessions", str(session_id))
    os.makedirs(path, exist_ok=True)
    return path


def _get_active_session(request: Request, db: Session, user: User) -> AddSession | None:
    session_id = request.session.get("add_session_id")
    if not session_id:
        return None

    add_session = db.get(AddSession, session_id)
    if add_session is None or add_session.user_id != user.id:
        request.session.pop("add_session_id", None)
        return None

    return add_session


@router.get("")
def addhoso_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    add_session = _get_active_session(request, db, user)
    if add_session is None:
        return templates.TemplateResponse(request, "addhoso_upload.html", {})
    return templates.TemplateResponse(request, "addhoso_lookup.html", {"add_session": add_session})


@router.post("/sessions")
async def create_add_session(
    request: Request,
    baocao_file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    old_session_id = request.session.get("add_session_id")
    if old_session_id:
        logic.evict_session(old_session_id)

    add_session = AddSession(user_id=user.id, baocao_filename=baocao_file.filename)
    db.add(add_session)
    db.commit()
    db.refresh(add_session)

    baocao_path = os.path.join(_session_upload_dir(add_session.id), "baocao.xlsx")
    with open(baocao_path, "wb") as f:
        f.write(await baocao_file.read())

    # Đọc + cache ngay lúc upload (file lớn có thể mất chục giây) — để các lần tra cứu
    # sau đó trong cùng session luôn tức thì, không phải đợi ở lần tra đầu tiên.
    logic.warm_baocao_cache(add_session.id, baocao_path)

    settings: Settings = db.get(Settings, user.id)
    logic.get_link1_index(settings.sheet_received_url)

    request.session["add_session_id"] = add_session.id
    return RedirectResponse("/addhoso", status_code=303)


@router.post("/reset")
def reset_add_session(request: Request):
    session_id = request.session.pop("add_session_id", None)
    if session_id:
        logic.evict_session(session_id)
    return RedirectResponse("/addhoso", status_code=303)


@router.get("/lookup")
def lookup_cccd(
    cccd: str, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    add_session = _get_active_session(request, db, user)
    if add_session is None:
        raise HTTPException(status_code=400, detail="Chưa có phiên làm việc — hãy upload báo cáo đào tạo trước.")

    settings: Settings = db.get(Settings, user.id)
    baocao_path = os.path.join(_session_upload_dir(add_session.id), "baocao.xlsx")

    return logic.build_preview(
        add_session.id, baocao_path, settings.sheet_received_url, settings.sheet_checklist_url, cccd
    )


@router.post("/add")
def add_to_checklist(
    request: Request,
    cccd: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    add_session = _get_active_session(request, db, user)
    if add_session is None:
        raise HTTPException(status_code=400, detail="Chưa có phiên làm việc — hãy upload báo cáo đào tạo trước.")

    settings: Settings = db.get(Settings, user.id)
    baocao_path = os.path.join(_session_upload_dir(add_session.id), "baocao.xlsx")

    baocao_row = logic.resolve_baocao_row(add_session.id, baocao_path, cccd)
    if baocao_row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy CCCD trong báo cáo đào tạo.")

    # Check trùng PHẢI luôn tải mới, không cache — tránh bỏ sót dòng người khác vừa thêm.
    checklist_rows = sheets.fetch_sheet_rows(settings.sheet_checklist_url)
    checklist_cccd_index = sheets.build_checklist_cccd_index(checklist_rows)
    if cccd_key(cccd) in checklist_cccd_index:
        raise HTTPException(status_code=409, detail="CCCD này đã tồn tại trong checklist.")

    link1_index = logic.get_link1_index(settings.sheet_received_url)
    link1_row = link1_index.get(cccd_key(cccd))

    header_idx = locate_header_row(checklist_rows, [sheets.CHECKLIST_CCCD_CANDIDATES])
    header = checklist_rows[header_idx]
    row_data = logic.build_row_data(baocao_row, link1_row)

    try:
        credentials = get_credentials_for_user(db, user)
        service = sheets.build_sheets_service(credentials)
        sheets.append_checklist_row(service, settings.sheet_checklist_url, header, row_data)
    except HttpError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Không ghi được vào Google Sheet — kiểm tra tài khoản đăng nhập có quyền "
                f"Editor trên sheet checklist chưa, hoặc đăng xuất/đăng nhập lại để cấp quyền Sheets. ({exc})"
            ),
        ) from exc

    add_session.added_count += 1
    db.commit()

    return {"success": True, "added_count": add_session.added_count}
