import io
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.auth.oauth import get_credentials_for_user
from app.db import get_db
from app.deps import get_current_user
from app.jobs import excel_io
from app.jobs.drive import download_file_bytes
from app.jobs.runner import job_upload_dir, submit_job
from app.jobs.textnorm import normalize_code
from app.models import Job, JobResult, User
from app.templating import templates

router = APIRouter(prefix="/jobs", tags=["jobs"])


def content_disposition(disposition: str, filename: str) -> str:
    """Header Content-Disposition an toàn với tên file có dấu tiếng Việt.

    HTTP header chỉ encode được latin-1, nên tên file Unicode phải đi qua
    filename* (RFC 5987) kèm 1 bản fallback ASCII cho client cũ.
    """

    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip() or "file.pdf"
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.post("")
async def create_job(
    request: Request,
    baocao_file: UploadFile,
    ds_file: UploadFile | None = None,
    single_mnv: str = Form(""),
    search_type: str = Form("mnv"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if search_type not in ("mnv", "cccd"):
        raise HTTPException(status_code=400, detail="search_type không hợp lệ")

    has_ds_file = ds_file is not None and bool(ds_file.filename)
    mnv = normalize_code(single_mnv)

    if has_ds_file and mnv:
        raise HTTPException(status_code=400, detail="Chỉ chọn 1 trong 2: nhập mã hoặc upload danh sách")
    if not has_ds_file and not mnv:
        raise HTTPException(status_code=400, detail="Cần nhập mã hoặc upload danh sách")

    job = Job(
        user_id=user.id,
        status="pending",
        ds_filename=ds_file.filename if has_ds_file else None,
        baocao_filename=baocao_file.filename,
        single_mnv=mnv or None,
        search_type=search_type,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    upload_dir = job_upload_dir(job.id)
    baocao_path = os.path.join(upload_dir, "baocao.xlsx")
    with open(baocao_path, "wb") as f:
        f.write(await baocao_file.read())

    if has_ds_file:
        ds_path = os.path.join(upload_dir, "ds.xlsx")
        with open(ds_path, "wb") as f:
            f.write(await ds_file.read())

    submit_job(job.id)

    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


def _get_owned_job(db: Session, job_id: int, user: User) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy job")
    return job


@router.get("/{job_id}")
def job_status_page(
    request: Request, job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _get_owned_job(db, job_id, user)
    return templates.TemplateResponse(request, "job_status.html", {"job": job})


@router.get("/{job_id}/api")
def job_status_api(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_owned_job(db, job_id, user)
    return {
        "id": job.id,
        "status": job.status,
        "total": job.total,
        "processed": job.processed,
        "found_count": job.found_count,
        "not_found_count": job.not_found_count,
        "error_message": job.error_message,
    }


@router.get("/{job_id}/results.json")
def job_results_json(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = _get_owned_job(db, job_id, user)
    if job.status != "done":
        raise HTTPException(status_code=409, detail="Job chưa hoàn tất")

    results = db.query(JobResult).filter_by(job_id=job.id).order_by(JobResult.id).all()
    return [
        {
            "stt": r.stt,
            "mnv": r.mnv,
            "ho_ten": r.ho_ten,
            "status": r.status,
            "drive_file_id": r.drive_file_id,
            "drive_file_name": r.drive_file_name,
            "cccd": r.cccd,
            "phong_tuyen_dung": r.phong_tuyen_dung,
            "da_nhan_ho_so": r.da_nhan_ho_so,
            "nguon": r.nguon,
            "ngay_viet_ho_so": r.ngay_viet_ho_so,
            "co_ma_checklist": r.co_ma_checklist,
            "ket_luan": r.ket_luan,
        }
        for r in results
    ]


@router.get("/{job_id}/download/pdf/{file_id}")
def download_pdf(
    job_id: int, file_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _get_owned_job(db, job_id, user)

    result = (
        db.query(JobResult)
        .filter_by(job_id=job.id, drive_file_id=file_id, status="found")
        .one_or_none()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy file trong kết quả job này")

    credentials = get_credentials_for_user(db, user)
    content = download_file_bytes(credentials, file_id)

    filename = result.drive_file_name or f"{file_id}.pdf"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition("inline", filename)},
    )


@router.get("/{job_id}/download/pdf-all")
def download_all_pdfs(
    job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _get_owned_job(db, job_id, user)

    results = (
        db.query(JobResult).filter_by(job_id=job.id, status="found").order_by(JobResult.id).all()
    )
    if not results:
        raise HTTPException(status_code=404, detail="Không có file PDF nào để tải")

    credentials = get_credentials_for_user(db, user)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_map = {
                executor.submit(download_file_bytes, credentials, r.drive_file_id): r for r in results
            }
            for future in as_completed(future_map):
                result = future_map[future]
                content = future.result()
                filename = result.drive_file_name or f"{result.drive_file_id}.pdf"
                arcname = f"{result.stt}_{filename}" if result.stt else filename
                zip_file.writestr(arcname, content)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_pdfs.zip"'},
    )


@router.get("/{job_id}/download/excel")
def download_not_found_excel(
    job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    job = _get_owned_job(db, job_id, user)

    results = db.query(JobResult).filter_by(job_id=job.id, status="not_found").order_by(JobResult.id).all()
    rows = [
        {
            "stt": r.stt,
            "mnv": r.mnv,
            "ho_ten": r.ho_ten,
            "cccd": r.cccd,
            "phong_tuyen_dung": r.phong_tuyen_dung,
            "da_nhan_ho_so": r.da_nhan_ho_so,
            "nguon": r.nguon,
            "ngay_viet_ho_so": r.ngay_viet_ho_so,
            "co_ma_checklist": r.co_ma_checklist,
            "ket_luan": r.ket_luan,
        }
        for r in results
    ]

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        excel_io.write_not_found_excel(rows, tmp_path)
        with open(tmp_path, "rb") as f:
            content = f.read()
    finally:
        os.remove(tmp_path)

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id}_not_found.xlsx"'},
    )
