import csv
import io
import re

import httpx

from app.jobs.textnorm import find_column, locate_header_row, normalize_code

SPREADSHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
GID_RE = re.compile(r"[?&#]gid=(\d+)")

CCCD_CANDIDATES = ["CCCD", "Số CMND/Hộ chiếu", "Số CMND"]
NGAY_VIET_HO_SO_CANDIDATES = ["Ngày viết hồ sơ"]
NGUON_CANDIDATES = ["Nguồn"]
MNV_CANDIDATES = ["Mã nhân viên", "Mã NV", "MNV"]

def parse_sheet_url(url: str) -> tuple[str, str]:
    match = SPREADSHEET_ID_RE.search(url)
    if not match:
        raise ValueError(f"Không nhận diện được spreadsheet ID trong URL: {url}")

    sheet_id = match.group(1)
    gid_match = GID_RE.search(url)
    gid = gid_match.group(1) if gid_match else "0"
    return sheet_id, gid


def build_export_url(url: str) -> str:
    sheet_id, gid = parse_sheet_url(url)
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def fetch_sheet_rows(url: str, client: httpx.Client | None = None) -> list[list[str]]:
    """Tải toàn bộ sheet dạng CSV, trả về raw rows (KHÔNG giả định dòng 1 là header —
    sheet sống có thể bị chèn/xoá dòng nên header có thể lệch xuống dòng khác).
    """

    export_url = build_export_url(url)

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=30)
    try:
        resp = client.get(export_url)
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    reader = csv.reader(io.StringIO(resp.text))
    return list(reader)


def build_cccd_index(rows: list[list[str]]) -> dict[str, dict]:
    header_idx = locate_header_row(rows, [CCCD_CANDIDATES])
    headers = rows[header_idx]
    data_rows = rows[header_idx + 1 :]

    idx_cccd = find_column(headers, CCCD_CANDIDATES)
    idx_ngay = find_column(headers, NGAY_VIET_HO_SO_CANDIDATES)
    idx_nguon = find_column(headers, NGUON_CANDIDATES)

    index: dict[str, dict] = {}
    for row in data_rows:
        if idx_cccd >= len(row):
            continue

        cccd = normalize_code(row[idx_cccd])
        if not cccd:
            continue

        index[cccd] = {
            "nguon": row[idx_nguon].strip() if idx_nguon is not None and idx_nguon < len(row) else "",
            "ngay_viet_ho_so": row[idx_ngay].strip() if idx_ngay is not None and idx_ngay < len(row) else "",
        }

    return index


def build_mnv_set(rows: list[list[str]]) -> set[str]:
    header_idx = locate_header_row(rows, [MNV_CANDIDATES])
    headers = rows[header_idx]
    data_rows = rows[header_idx + 1 :]

    idx_mnv = find_column(headers, MNV_CANDIDATES)

    result: set[str] = set()
    for row in data_rows:
        if idx_mnv >= len(row):
            continue
        value = normalize_code(row[idx_mnv])
        if value:
            result.add(value)

    return result
