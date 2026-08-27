import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    token: Mapped["OAuthToken"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings: Mapped["Settings"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=True)
    expiry: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str] = mapped_column(String(500), nullable=True)

    user: Mapped["User"] = relationship(back_populates="token")


class Settings(Base):
    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    drive_folder_1: Mapped[str] = mapped_column(String(255))
    drive_folder_2: Mapped[str] = mapped_column(String(255))
    sheet_recruit_url: Mapped[str] = mapped_column(String(1000))
    sheet_received_url: Mapped[str] = mapped_column(String(1000))
    sheet_checklist_url: Mapped[str] = mapped_column(String(1000))

    user: Mapped["User"] = relationship(back_populates="settings")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/done/error
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow
    )
    ds_filename: Mapped[str] = mapped_column(String(500), nullable=True)
    baocao_filename: Mapped[str] = mapped_column(String(500), nullable=True)
    single_mnv: Mapped[str] = mapped_column(String(50), nullable=True)
    search_type: Mapped[str] = mapped_column(String(10), default="mnv")  # "mnv" hoặc "cccd"
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    found_count: Mapped[int] = mapped_column(Integer, default=0)
    not_found_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    results: Mapped[list["JobResult"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobResult(Base):
    __tablename__ = "job_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    stt: Mapped[str] = mapped_column(String(50), nullable=True)
    mnv: Mapped[str] = mapped_column(String(50), index=True)
    ho_ten: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # found / not_found

    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=True)
    drive_file_name: Mapped[str] = mapped_column(String(500), nullable=True)

    cccd: Mapped[str] = mapped_column(String(50), nullable=True)
    phong_tuyen_dung: Mapped[str] = mapped_column(String(255), nullable=True)
    da_nhan_ho_so: Mapped[str] = mapped_column(String(255), nullable=True)
    nguon: Mapped[str] = mapped_column(String(255), nullable=True)
    ngay_viet_ho_so: Mapped[str] = mapped_column(String(50), nullable=True)
    co_ma_checklist: Mapped[str] = mapped_column(String(50), nullable=True)
    ket_luan: Mapped[str] = mapped_column(String(255), nullable=True)

    job: Mapped["Job"] = relationship(back_populates="results")
