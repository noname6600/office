def build_fallback_conclusion(
    mnv: str,
    baocao_index: dict[str, dict],
    recruit_index: dict[str, dict],
    received_index: dict[str, dict],
    checklist_mnv_set: set[str],
) -> dict:
    """Logic fallback khi không tìm thấy PDF theo MNV trong 2 folder Drive — đã chốt với user:

    1. Tra MNV trong báo cáo đào tạo -> CCCD. Không có -> kết luận dừng ở đây.
    2. Dùng CCCD tra 2 sheet (recruit / received) -> "Phòng tuyển dụng có" / "Đã nhận hồ sơ",
       kèm Ngày viết hồ sơ + Nguồn. Không thấy ở cả 2 -> "Không tìm thấy hồ sơ".
    3. Độc lập: tra MNV gốc (không phải CCCD) trong sheet checklist -> "Có mã" / "Không có mã".
    """

    result = {
        "cccd": None,
        "phong_tuyen_dung": None,
        "da_nhan_ho_so": None,
        "nguon": None,
        "ngay_viet_ho_so": None,
        "co_ma_checklist": "Có mã" if mnv in checklist_mnv_set else "Không có mã",
        "ket_luan": None,
    }

    baocao_row = baocao_index.get(mnv)
    if baocao_row is None or not baocao_row.get("cccd"):
        result["ket_luan"] = "Không tìm thấy nhân viên trong báo cáo đào tạo"
        return result

    cccd = baocao_row["cccd"]
    result["cccd"] = cccd

    recruit_row = recruit_index.get(cccd)
    received_row = received_index.get(cccd)

    if recruit_row:
        result["phong_tuyen_dung"] = "Phòng tuyển dụng có"
        result["nguon"] = recruit_row.get("nguon") or None
        result["ngay_viet_ho_so"] = recruit_row.get("ngay_viet_ho_so") or None

    if received_row:
        result["da_nhan_ho_so"] = "Đã nhận hồ sơ"
        result["nguon"] = result["nguon"] or received_row.get("nguon") or None
        result["ngay_viet_ho_so"] = result["ngay_viet_ho_so"] or received_row.get("ngay_viet_ho_so") or None

    conclusion_parts = [part for part in (result["phong_tuyen_dung"], result["da_nhan_ho_so"]) if part]
    result["ket_luan"] = "; ".join(conclusion_parts) if conclusion_parts else "Không tìm thấy hồ sơ"

    return result
