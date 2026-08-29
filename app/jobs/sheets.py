import csv
import datetime
import io
import re

import httpx
from googleapiclient.discovery import build as build_google_service

from app.jobs.textnorm import cccd_key, find_column, locate_header_row, normalize_code, normalize_header

SPREADSHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
GID_RE = re.compile(r"[?&#]gid=(\d+)")

CCCD_CANDIDATES = ["CCCD", "Số CMND/Hộ chiếu", "Số CMND"]
NGAY_VIET_HO_SO_CANDIDATES = ["Ngày viết hồ sơ"]
NGUON_CANDIDATES = ["Nguồn"]
MNV_CANDIDATES = ["Mã nhân viên", "Mã NV", "MNV"]

# Các cột "trạng thái hồ sơ" ở sheet 1 (đã nhận hồ sơ) — dùng khi Add sang checklist (link 2).
LINK1_EXTRA_FIELD_CANDIDATES: dict[str, list[str]] = {
    "hanh_kiem_lltp": ["Giấy xác nhận hạnh kiếm/LLTPS2", "Giấy xác nhận hạnh kiểm/LLTPS2"],
    "giay_kham_suc_khoe": ["Giấy khám sức khỏe"],
    "can_cuoc_cong_dan": ["Căn cước công dân"],
    "xac_nhan_cu_tru": ["Xác nhận cư trú"],
    "phieu_thong_tin_ca_nhan": ["Phiếu thông tin cá nhân"],
    "tinh_trang": ["Tình trạng"],
}
CHECKLIST_CCCD_CANDIDATES = ["Số CMND/Hộ chiếu", "CCCD", "Số CMND"]

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
    extra_idx = {key: find_column(headers, candidates) for key, candidates in LINK1_EXTRA_FIELD_CANDIDATES.items()}

    index: dict[str, dict] = {}
    for row in data_rows:
        if idx_cccd >= len(row):
            continue

        cccd = normalize_code(row[idx_cccd])
        if not cccd:
            continue

        entry = {
            "nguon": row[idx_nguon].strip() if idx_nguon is not None and idx_nguon < len(row) else "",
            "ngay_viet_ho_so": row[idx_ngay].strip() if idx_ngay is not None and idx_ngay < len(row) else "",
        }
        for key, idx in extra_idx.items():
            entry[key] = row[idx].strip() if idx is not None and idx < len(row) else ""

        index[cccd_key(cccd)] = entry

    return index


def build_checklist_cccd_index(rows: list[list[str]]) -> dict[str, str]:
    """dict[cccd_key(CCCD)] = MNV (rỗng nếu dòng checklist chưa có MNV) — dùng khi tìm theo CCCD."""

    header_idx = locate_header_row(rows, [CHECKLIST_CCCD_CANDIDATES])
    headers = rows[header_idx]
    data_rows = rows[header_idx + 1 :]

    idx_cccd = find_column(headers, CHECKLIST_CCCD_CANDIDATES)
    idx_mnv = find_column(headers, MNV_CANDIDATES)

    result: dict[str, str] = {}
    if idx_cccd is None:
        return result

    for row in data_rows:
        if idx_cccd >= len(row):
            continue
        cccd = normalize_code(row[idx_cccd])
        if not cccd:
            continue
        mnv = normalize_code(row[idx_mnv]) if idx_mnv is not None and idx_mnv < len(row) else ""
        result[cccd_key(cccd)] = mnv

    return result


# ============================================================
# GHI VÀO SHEET (tab "Thêm hồ sơ vào Checklist")
# ============================================================

# Mỗi mục: (danh sách tên cột ứng viên trong checklist, key tương ứng trong dict data truyền vào
# append_checklist_row). "ngay_nhan_viec" là field tính toán (không có sẵn trong báo cáo đào tạo
# dưới tên này — xem app/addhoso), map vào cột "Ngày vào Tập đoàn" của checklist.
CHECKLIST_FIELD_SOURCE: list[tuple[list[str], str]] = [
    # Phòng/Vùng/Miền: KHÔNG map — toàn bộ dòng có sẵn trong checklist đều để trống cột này,
    # tự fill từ báo cáo đào tạo sẽ sai quy ước hiện tại.
    (MNV_CANDIDATES, "mnv"),
    (["Họ và tên", "Họ tên"], "ho_ten"),
    (["Job"], "job"),
    (["Chức danh"], "chuc_danh"),
    (["Giới tính"], "gioi_tinh"),
    (["Ngày sinh"], "ngay_sinh"),
    (["Nơi sinh"], "noi_sinh"),
    (["Địa chỉ thường trú"], "dia_chi_thuong_tru"),
    (["Địa chỉ hiện tại"], "dia_chi_hien_tai"),
    (CHECKLIST_CCCD_CANDIDATES, "cccd"),
    (["Ngày cấp"], "ngay_cap"),
    (["Nơi cấp"], "noi_cap"),
    (["Điện thoại di động", "Điện thoại"], "dien_thoai"),
    (["Ngày vào Tập đoàn"], "ngay_nhan_viec"),
    # 8 cột trạng thái hồ sơ — lấy từ sheet "đã nhận hồ sơ" (link 1) tại thời điểm Add.
    (["Lý lịch tư pháp số 2"], "ly_lich_tu_phap"),
    (["Xác nhận hạnh kiểm"], "xac_nhan_hanh_kiem"),
    (["Giấy khám sức khỏe"], "giay_kham_suc_khoe"),
    (["Căn cước công dân"], "can_cuoc_cong_dan"),
    (["Phiếu thông tin cá nhân"], "phieu_thong_tin_ca_nhan"),
    (["Thông tin cư trú"], "thong_tin_cu_tru"),
    (["Hs thiếu/đủ"], "hs_thieu_du"),
    (["Ghi chú"], "ghi_chu"),
    # Trạng thái: không có nguồn tương ứng ở link 1 -> để trống.
]


def format_sheet_date(value) -> str:
    """D/M/YYYY không đệm số 0 — khớp format chuẩn hoá của sheet checklist."""

    if value is None:
        return ""
    if isinstance(value, datetime.datetime | datetime.date):
        return f"{value.day}/{value.month}/{value.year}"
    return str(value)


def _sheet_value(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, datetime.datetime | datetime.date):
        return format_sheet_date(raw)
    return str(raw)


def build_checklist_row(header: list[str], data: dict) -> list[str]:
    """Map dữ liệu (theo key) vào đúng thứ tự cột hiện tại của checklist (theo TÊN cột, không
    hardcode vị trí). Cột không nhận diện được (VD: các cột trạng thái hồ sơ) để trống.
    """

    row = []
    for raw_header in header:
        normalized_h = normalize_header(raw_header)
        value = ""
        for candidates, key in CHECKLIST_FIELD_SOURCE:
            if normalized_h in [normalize_header(c) for c in candidates]:
                value = _sheet_value(data.get(key))
                break
        row.append(value)
    return row


def build_sheets_service(credentials):
    return build_google_service("sheets", "v4", credentials=credentials, cache_discovery=False)


def get_sheet_title(service, spreadsheet_id: str, gid: str) -> str:
    """Sheets API append cần TÊN sheet (tab), không phải gid — tra qua metadata."""

    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="sheets.properties").execute()
    target_gid = int(gid)
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("sheetId") == target_gid:
            return props["title"]
    raise ValueError(f"Không tìm thấy sheet có gid={gid} trong spreadsheet {spreadsheet_id}")


def append_checklist_row(service, sheet_url: str, header: list[str], data: dict) -> None:
    """Ghi 1 dòng mới vào cuối bảng checklist. Dùng insertDataOption=INSERT_ROWS để Google tự
    tìm dòng trống cuối bảng, không cần tự dò dòng cuối.
    """

    spreadsheet_id, gid = parse_sheet_url(sheet_url)
    sheet_title = get_sheet_title(service, spreadsheet_id, gid)
    row = build_checklist_row(header, data)

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_title}'!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


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
