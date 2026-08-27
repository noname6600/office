"""Helpers dùng chung để đọc header/giá trị từ file Excel và CSV (Google Sheets)
mà không phụ thuộc vào thứ tự cột cố định.
"""


def normalize_header(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ")
    text = " ".join(text.split())
    return text.strip().casefold()


def find_column(headers: list, candidates: list[str]) -> int | None:
    """Trả về index cột đầu tiên khớp (chính xác, rồi tới chứa-substring) với 1 trong các tên ứng viên."""

    normalized_headers = [normalize_header(h) for h in headers]
    normalized_candidates = [normalize_header(c) for c in candidates]

    for idx, header in enumerate(normalized_headers):
        if header and header in normalized_candidates:
            return idx

    for idx, header in enumerate(normalized_headers):
        for candidate in normalized_candidates:
            if candidate and candidate in header:
                return idx

    return None


def normalize_code(value) -> str:
    """Chuẩn hoá MNV/CCCD đọc từ Excel (có thể là int/float) hoặc CSV (luôn là str) về dạng str gọn."""

    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    return str(value).strip()


def locate_header_row(rows: list, candidate_groups: list[list[str]], max_scan: int = 10) -> int:
    """Dò dòng header thật trong vài dòng đầu bằng cách chấm điểm số nhóm cột nhận diện được,
    thay vì giả định cố định dòng 1 là header (file/sheet sống có thể lệch dòng theo thời gian).
    Trả về index (0-based) của dòng có điểm cao nhất; lỗi nếu không dòng nào khớp được nhóm nào.
    """

    best_idx = -1
    best_score = 0

    for idx, row in enumerate(rows[:max_scan]):
        score = sum(1 for group in candidate_groups if find_column(row, group) is not None)
        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx == -1:
        raise ValueError(f"Không tìm thấy dòng header phù hợp trong {max_scan} dòng đầu.")

    return best_idx


def is_numeric(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip()
    return text.isdigit()
