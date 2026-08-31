from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401  (đăng ký model trước khi tạo bảng)

    Base.metadata.create_all(bind=engine)
    _run_lightweight_migrations()


def _run_lightweight_migrations():
    """create_all() không tự thêm cột mới vào bảng đã tồn tại -> thêm thủ công nếu thiếu."""

    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.connect() as conn:
        cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(jobs)").fetchall()]
        if "single_mnv" not in cols:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN single_mnv VARCHAR(50)")
            conn.commit()
        if "search_type" not in cols:
            conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN search_type VARCHAR(10) DEFAULT 'mnv'")
            conn.commit()

        addsession_cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(add_sessions)").fetchall()]
        if addsession_cols and "added_count" not in addsession_cols:
            conn.exec_driver_sql("ALTER TABLE add_sessions ADD COLUMN added_count INTEGER DEFAULT 0")
            conn.commit()
