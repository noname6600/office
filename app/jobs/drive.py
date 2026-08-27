import io
import re
import time

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

MAX_RETRIES = 3
CHUNK_SIZE = 4 * 1024 * 1024
NUMBER_TOKEN_RE = re.compile(r"\d{5,}")

# Tên file chứa các cụm này (không phân biệt hoa/thường, có/không dấu) sẽ bị loại
# khỏi kết quả hoàn toàn — VD: hợp đồng thử nghiệm không tính là hồ sơ hợp lệ.
EXCLUDED_NAME_SUBSTRINGS = ["hdtn"]


def _normalize_for_filter(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return text.lower()


def is_excluded_filename(name: str) -> bool:
    normalized = _normalize_for_filter(name)
    return any(sub in normalized for sub in EXCLUDED_NAME_SUBSTRINGS)


def build_drive_service(credentials: Credentials):
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def list_pdfs_in_folder(service, folder_id: str) -> list[dict]:
    """Quét toàn bộ PDF trong 1 folder Drive, đệ quy vào mọi thư mục con.

    Hồ sơ thực tế được tổ chức thành nhiều thư mục con lồng nhau bên trong 2 folder
    gốc (VD: "HỒ SƠ CHƯA UP HỆ THỐNG"), nên không thể chỉ liệt kê con trực tiếp.
    """

    files = []
    folders_to_scan = [folder_id]
    seen_folders: set[str] = set()

    while folders_to_scan:
        current_folder = folders_to_scan.pop()
        if current_folder in seen_folders:
            continue
        seen_folders.add(current_folder)

        page_token = None
        while True:
            response = (
                service.files()
                .list(
                    q=(f"'{current_folder}' in parents and trashed = false"),
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    pageSize=1000,
                    fields="nextPageToken,files(id,name,mimeType)",
                    pageToken=page_token,
                )
                .execute()
            )

            for file in response.get("files", []):
                if file.get("mimeType") == FOLDER_MIME_TYPE:
                    folders_to_scan.append(file["id"])
                elif file.get("mimeType") == "application/pdf":
                    if not is_excluded_filename(file.get("name", "")):
                        files.append(file)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    return files


def list_pdfs_merged(service, folder_ids: list[str]) -> list[dict]:
    files = []
    for folder_id in folder_ids:
        folder_id = (folder_id or "").strip()
        if folder_id:
            files.extend(list_pdfs_in_folder(service, folder_id))
    return files


def build_mnv_file_index(files: list[dict], mnv_list: list[str]) -> dict[str, list[dict]]:
    """Index tên file PDF theo MNV, tránh vòng lặp lồng O(files x mnv) như script cũ.

    Giả định MNV là chuỗi số (đúng với dữ liệu thực tế) -> trích các dãy số trong tên file 1 lần,
    so khớp bằng set. Với MNV không phải số (hiếm), fallback kiểm tra substring trực tiếp.
    """

    mnv_set = set(mnv_list)
    numeric_mnvs = {m for m in mnv_set if m.isdigit()}
    other_mnvs = mnv_set - numeric_mnvs

    index: dict[str, list[dict]] = {}

    for file in files:
        name = file.get("name", "")

        for token in NUMBER_TOKEN_RE.findall(name):
            if token in numeric_mnvs:
                index.setdefault(token, []).append(file)

        for mnv in other_mnvs:
            if mnv in name:
                index.setdefault(mnv, []).append(file)

    return index


def download_file_bytes(credentials: Credentials, file_id: str) -> bytes:
    service = build_drive_service(credentials)
    request = service.files().get_media(fileId=file_id)

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request, chunksize=CHUNK_SIZE)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            buffer.seek(0)
            buffer.truncate()
            done = False
            while not done:
                _, done = downloader.next_chunk()
            return buffer.getvalue()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)

    raise RuntimeError(f"Không tải được file {file_id} sau {MAX_RETRIES} lần thử: {last_error}")
