"""Logic tính toán cho tab 'Thêm hồ sơ vào Checklist' — tra CCCD, tính các mốc ngày,
chuẩn bị dữ liệu để ghi 1 dòng mới vào sheet checklist.
"""

import datetime
import time
from collections import OrderedDict

from app.jobs import excel_io, sheets
from app.jobs.sheets import format_sheet_date
from app.jobs.textnorm import cccd_key

# ============================================================
# CACHE — file báo cáo đào tạo không đổi trong 1 session nên cache theo session_id;
# sheet "đã nhận hồ sơ" (link 1) là dữ liệu sống, cache ngắn hạn (TTL) để tránh tải
# lại toàn bộ sheet (hàng ngàn dòng) ở mỗi lần bấm tra cứu liên tiếp.
#
# _BAOCAO_INDEX_CACHE giới hạn số session giữ trong bộ nhớ cùng lúc (LRU) — không thì
# mỗi lần upload báo cáo mới (session mới) sẽ tích tụ dần, không bao giờ được dọn.
# ============================================================

_BAOCAO_CACHE_MAX_SESSIONS = 5
_BAOCAO_INDEX_CACHE: "OrderedDict[int, dict[str, dict]]" = OrderedDict()
_LINK1_CACHE_TTL_SECONDS = 600  # 10 phút — sheet này chỉ dùng hiển thị tham khảo, không phải check trùng
_link1_cache: dict[str, tuple[float, dict]] = {}


def _get_baocao_index(session_id: int, baocao_path: str) -> dict[str, dict]:
    if session_id in _BAOCAO_INDEX_CACHE:
        _BAOCAO_INDEX_CACHE.move_to_end(session_id)
        return _BAOCAO_INDEX_CACHE[session_id]

    index = excel_io.read_baocao_full_index(baocao_path)
    _BAOCAO_INDEX_CACHE[session_id] = index
    if len(_BAOCAO_INDEX_CACHE) > _BAOCAO_CACHE_MAX_SESSIONS:
        _BAOCAO_INDEX_CACHE.popitem(last=False)
    return index


def evict_session(session_id: int) -> None:
    """Dọn cache của 1 session — gọi khi user đổi sang báo cáo đào tạo khác."""

    _BAOCAO_INDEX_CACHE.pop(session_id, None)


def get_link1_index(sheet_link1_url: str) -> dict[str, dict]:
    now = time.monotonic()
    cached = _link1_cache.get(sheet_link1_url)
    if cached is not None and now - cached[0] < _LINK1_CACHE_TTL_SECONDS:
        return cached[1]

    index = sheets.build_cccd_index(sheets.fetch_sheet_rows(sheet_link1_url))
    _link1_cache[sheet_link1_url] = (now, index)
    return index


def resolve_baocao_row(session_id: int, baocao_path: str, cccd: str) -> dict | None:
    index = _get_baocao_index(session_id, baocao_path)
    return index.get(cccd_key(cccd))


def warm_baocao_cache(session_id: int, baocao_path: str) -> None:
    """Đọc + cache trước file báo cáo đào tạo ngay lúc upload — file lớn (hàng chục nghìn
    dòng) có thể mất hàng chục giây để parse, nên trả giá 1 lần ở đây thay vì ở lần tra
    cứu CCCD đầu tiên của user."""

    _get_baocao_index(session_id, baocao_path)


def compute_dates(baocao_row: dict) -> dict:
    """Ngày nhận việc = Ngày bắt đầu HĐTN = 'Ngày vào công ty' trong báo cáo đào tạo.
    Ngày kết thúc HĐTN = Ngày bắt đầu HĐTN + 30 ngày lịch.
    """

    ngay_nhan_viec_raw = baocao_row.get("ngay_vao_cong_ty")
    ngay_ket_thuc_raw = None
    if isinstance(ngay_nhan_viec_raw, datetime.datetime | datetime.date):
        ngay_ket_thuc_raw = ngay_nhan_viec_raw + datetime.timedelta(days=30)

    return {"ngay_nhan_viec_raw": ngay_nhan_viec_raw, "ngay_ket_thuc_raw": ngay_ket_thuc_raw}


def build_preview(session_id: int, baocao_path: str, sheet_link1_url: str, cccd: str) -> dict:
    """Trả về đúng 7 field hiển thị, hoặc {"error": ...} nếu không tra được."""

    baocao_row = resolve_baocao_row(session_id, baocao_path, cccd)
    if baocao_row is None:
        return {"error": "Không tìm thấy CCCD trong báo cáo đào tạo."}

    link1_index = get_link1_index(sheet_link1_url)
    link1_row = link1_index.get(cccd_key(cccd))
    ngay_phong_van = (link1_row or {}).get("ngay_viet_ho_so") or ""
    co_o_ho_so_da_nhan = "Có ở hồ sơ đã nhận" if link1_row else ""

    dates = compute_dates(baocao_row)

    return {
        "co_o_ho_so_da_nhan": co_o_ho_so_da_nhan,
        "cccd": cccd,
        "mnv": baocao_row.get("mnv"),
        "ho_ten": baocao_row.get("ho_ten"),
        "ngay_phong_van": ngay_phong_van,
        "ngay_nhan_viec": format_sheet_date(dates["ngay_nhan_viec_raw"]),
        "ngay_bat_dau_hdtn": format_sheet_date(dates["ngay_nhan_viec_raw"]),
        "ngay_ket_thuc_hdtn": format_sheet_date(dates["ngay_ket_thuc_raw"]),
    }


def build_row_data(baocao_row: dict, link1_row: dict | None) -> dict:
    """Dữ liệu đầy đủ để append_checklist_row ghi vào sheet — gồm mọi field trong
    baocao_row, field tính toán 'ngay_nhan_viec', và 8 cột trạng thái hồ sơ lấy từ
    link1_row (sheet 'đã nhận hồ sơ') tại thời điểm Add.
    """

    dates = compute_dates(baocao_row)
    row_data = dict(baocao_row)
    row_data["ngay_nhan_viec"] = dates["ngay_nhan_viec_raw"]

    link1_row = link1_row or {}
    hanh_kiem_lltp = link1_row.get("hanh_kiem_lltp") or ""
    row_data["ly_lich_tu_phap"] = hanh_kiem_lltp
    row_data["xac_nhan_hanh_kiem"] = hanh_kiem_lltp
    row_data["giay_kham_suc_khoe"] = link1_row.get("giay_kham_suc_khoe") or ""
    row_data["can_cuoc_cong_dan"] = link1_row.get("can_cuoc_cong_dan") or ""
    row_data["phieu_thong_tin_ca_nhan"] = link1_row.get("phieu_thong_tin_ca_nhan") or ""
    row_data["thong_tin_cu_tru"] = link1_row.get("xac_nhan_cu_tru") or ""
    row_data["hs_thieu_du"] = link1_row.get("tinh_trang") or ""
    row_data["ghi_chu"] = link1_row.get("nguon") or ""

    return row_data
