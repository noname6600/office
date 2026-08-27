from openpyxl import Workbook, load_workbook

from app.jobs.textnorm import cccd_key, find_column, is_numeric, locate_header_row, normalize_code

# DS.xlsx đã được chuẩn hoá: STT luôn ở cột A (index 0), MNV luôn ở cột C (index 2).
# Cột D (Họ và tên) là best-effort — đọc nếu có, không bắt buộc.
DS_STT_COL = 0
DS_MNV_COL = 2
DS_HOTEN_COL = 3

BAOCAO_MNV_CANDIDATES = ["Mã nhân viên", "Mã NV", "MNV"]
BAOCAO_CCCD_CANDIDATES = ["Số CMND/Hộ chiếu", "CCCD", "Số CMND"]
BAOCAO_HOTEN_CANDIDATES = ["Họ và tên", "Họ tên"]


def _find_data_start_row(ws, max_scan: int = 20) -> int:
    """DS.xlsx có thể có nhiều dòng header phía trên (VD: 3 dòng) trước khi tới dữ liệu thật.
    Dò dòng đầu tiên có STT (cột A) là số để xác định dòng bắt đầu dữ liệu.
    """

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan), start=1):
        if is_numeric(row[DS_STT_COL].value):
            return row_idx
    return 2


def read_ds_list(path: str) -> list[dict]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = workbook.active
        start_row = _find_data_start_row(ws)

        data = []
        for row in ws.iter_rows(min_row=start_row):
            stt_value = row[DS_STT_COL].value
            mnv_value = row[DS_MNV_COL].value

            mnv = normalize_code(mnv_value)
            if not mnv:
                continue

            ho_ten_value = row[DS_HOTEN_COL].value if len(row) > DS_HOTEN_COL else None
            ho_ten = str(ho_ten_value).strip() if ho_ten_value is not None else None

            data.append({"stt": normalize_code(stt_value), "mnv": mnv, "ho_ten": ho_ten})

        return data
    finally:
        workbook.close()


def read_cccd_list(path: str) -> list[dict]:
    """Đọc danh sách CCCD cần tìm — cùng định dạng chuẩn với DS.xlsx (STT cột A, mã cột C)."""

    raw = read_ds_list(path)
    return [{"stt": item["stt"], "cccd": item["mnv"], "ho_ten": item["ho_ten"]} for item in raw]


def _read_baocao_rows(path: str) -> list[tuple[str, str]]:
    """Đọc file 'BÁO CÁO ĐÀO TẠO' -> list[{"mnv", "cccd", "ho_ten"}].

    Cột được dò theo TÊN header, không hardcode vị trí, vì file này đổi theo ngày
    và có thể lệch thứ tự cột. Cột Họ và tên là best-effort — không bắt buộc phải có.
    """

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = workbook.active
        rows = [list(row) for row in ws.iter_rows(values_only=True)]
        if not rows:
            return []

        header_idx = locate_header_row(rows, [BAOCAO_MNV_CANDIDATES, BAOCAO_CCCD_CANDIDATES])
        header = rows[header_idx]
        data_rows = rows[header_idx + 1 :]

        idx_mnv = find_column(header, BAOCAO_MNV_CANDIDATES)
        idx_cccd = find_column(header, BAOCAO_CCCD_CANDIDATES)
        idx_hoten = find_column(header, BAOCAO_HOTEN_CANDIDATES)

        if idx_mnv is None or idx_cccd is None:
            raise ValueError(
                "Không tìm thấy cột 'Mã nhân viên' hoặc 'Số CMND/Hộ chiếu' trong file báo cáo đào tạo."
            )

        result = []
        for row in data_rows:
            if idx_mnv >= len(row):
                continue

            mnv = normalize_code(row[idx_mnv])
            if not mnv:
                continue

            cccd = normalize_code(row[idx_cccd]) if idx_cccd < len(row) else ""

            ho_ten = None
            if idx_hoten is not None and idx_hoten < len(row) and row[idx_hoten] is not None:
                ho_ten = str(row[idx_hoten]).strip() or None

            result.append({"mnv": mnv, "cccd": cccd, "ho_ten": ho_ten})

        return result
    finally:
        workbook.close()


def read_baocao_index(path: str) -> dict[str, dict]:
    """dict[MNV] = {"cccd": str, "ho_ten": str|None} — dùng khi đã biết MNV."""

    return {r["mnv"]: {"cccd": r["cccd"], "ho_ten": r["ho_ten"]} for r in _read_baocao_rows(path)}


def read_baocao_cccd_index(path: str) -> dict[str, dict]:
    """dict[cccd_key(CCCD)] = {"mnv": str, "ho_ten": str|None} — chiều ngược lại read_baocao_index()."""

    result: dict[str, dict] = {}
    for r in _read_baocao_rows(path):
        if r["cccd"]:
            result[cccd_key(r["cccd"])] = {"mnv": r["mnv"], "ho_ten": r["ho_ten"]}
    return result


NOT_FOUND_COLUMNS = [
    ("stt", "STT"),
    ("mnv", "MNV"),
    ("ho_ten", "Họ và tên"),
    ("cccd", "CCCD"),
    ("phong_tuyen_dung", "Phòng tuyển dụng"),
    ("da_nhan_ho_so", "Đã nhận hồ sơ"),
    ("nguon", "Nguồn"),
    ("ngay_viet_ho_so", "Ngày viết hồ sơ"),
    ("co_ma_checklist", "Có mã (checklist)"),
    ("ket_luan", "Kết luận"),
]


def write_not_found_excel(rows: list[dict], output_path: str) -> None:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Not found"

    ws.append([label for _, label in NOT_FOUND_COLUMNS])
    for row in rows:
        ws.append([row.get(key, "") for key, _ in NOT_FOUND_COLUMNS])

    workbook.save(output_path)
