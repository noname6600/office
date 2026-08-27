import os

from dotenv import load_dotenv

load_dotenv()


GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "dev-only-insecure-secret")
SESSION_HTTPS_ONLY = os.environ.get("SESSION_HTTPS_ONLY", "false").lower() == "true"
TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./app.db")

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "./uploads")

# ------------------------------------------------------------
# Giá trị mặc định cho Settings của user mới (seed lần đầu login)
# ------------------------------------------------------------

DEFAULT_DRIVE_FOLDER_1 = "1pHnflFoG5UiYefXgqm7rulsKfqGyxTRs"
DEFAULT_DRIVE_FOLDER_2 = "1H0VLqYwdJKTsVDlZJbYhUo-M2gwsUCUg"

DEFAULT_SHEET_RECEIVED_URL = (
    "https://docs.google.com/spreadsheets/d/1D9Jbq5Fz-USc2KwfQPJRqTCNw0iL36d_6ZlMM6f-0WA/edit?gid=0#gid=0"
)
DEFAULT_SHEET_RECRUIT_URL = (
    "https://docs.google.com/spreadsheets/d/1hijYcW-sE3qY6P6kqagLYA-0GqqjCjX2ZSD6egw7tis/"
    "edit?gid=1152559492#gid=1152559492"
)
DEFAULT_SHEET_CHECKLIST_URL = (
    "https://docs.google.com/spreadsheets/d/15iBJ8mJrgQkV1PwXS669KugQ0EcMAP6rMqtowQwe5lM/"
    "edit?gid=1369995148#gid=1369995148"
)
