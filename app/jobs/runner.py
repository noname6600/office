import logging
import os
from concurrent.futures import ThreadPoolExecutor

from app import config
from app.auth.oauth import get_credentials_for_user
from app.db import SessionLocal
from app.jobs import drive, excel_io, sheets
from app.jobs.matcher import build_fallback_conclusion
from app.models import Job, JobResult, Settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


def job_upload_dir(job_id: int) -> str:
    path = os.path.join(config.UPLOAD_DIR, str(job_id))
    os.makedirs(path, exist_ok=True)
    return path


def submit_job(job_id: int) -> None:
    _executor.submit(_run_job, job_id)


def _run_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return

        job.status = "running"
        db.commit()

        user = job.user
        settings: Settings = db.get(Settings, user.id)
        credentials = get_credentials_for_user(db, user)
        service = drive.build_drive_service(credentials)

        upload_dir = job_upload_dir(job_id)
        baocao_path = os.path.join(upload_dir, "baocao.xlsx")

        if job.single_mnv:
            ds_list = [{"stt": "1", "mnv": job.single_mnv, "ho_ten": None}]
        else:
            ds_path = os.path.join(upload_dir, "ds.xlsx")
            ds_list = excel_io.read_ds_list(ds_path)

        baocao_index = excel_io.read_baocao_index(baocao_path)

        recruit_index = sheets.build_cccd_index(sheets.fetch_sheet_rows(settings.sheet_recruit_url))
        received_index = sheets.build_cccd_index(sheets.fetch_sheet_rows(settings.sheet_received_url))
        checklist_mnv_set = sheets.build_mnv_set(sheets.fetch_sheet_rows(settings.sheet_checklist_url))

        mnv_list = [item["mnv"] for item in ds_list]
        files = drive.list_pdfs_merged(service, [settings.drive_folder_1, settings.drive_folder_2])
        file_index = drive.build_mnv_file_index(files, mnv_list)

        job.total = len(ds_list)
        db.commit()

        found_count = 0
        not_found_count = 0

        for item in ds_list:
            mnv = item["mnv"]
            stt = item["stt"]
            ho_ten = item.get("ho_ten")

            matched_files = file_index.get(mnv, [])

            if matched_files:
                found_count += 1
                for matched_file in matched_files:
                    db.add(
                        JobResult(
                            job_id=job.id,
                            stt=stt,
                            mnv=mnv,
                            ho_ten=ho_ten,
                            status="found",
                            drive_file_id=matched_file["id"],
                            drive_file_name=matched_file["name"],
                        )
                    )
            else:
                not_found_count += 1
                conclusion = build_fallback_conclusion(
                    mnv, baocao_index, recruit_index, received_index, checklist_mnv_set
                )
                db.add(
                    JobResult(
                        job_id=job.id,
                        stt=stt,
                        mnv=mnv,
                        ho_ten=ho_ten,
                        status="not_found",
                        **conclusion,
                    )
                )

            job.processed += 1
            db.commit()

        job.found_count = found_count
        job.not_found_count = not_found_count
        job.status = "done"
        db.commit()

    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = "error"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
