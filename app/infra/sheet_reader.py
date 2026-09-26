import json
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional

import structural

_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def list_sheet_names(path: str):
    with zipfile.ZipFile(path) as z:
        with z.open("xl/workbook.xml") as f:
            tree = ET.parse(f)
    return [el.get("name") for el in tree.getroot().findall(".//main:sheets/main:sheet", _NS)]


def resolve_sheet_names(path: str, sheet_names: Optional[str]):
    all_names = list_sheet_names(path)
    if not all_names:
        raise ValueError("Không tìm thấy sheet nào trong file")
    if not sheet_names:
        return [all_names[0]]
    normalized_all = {name.strip(): name for name in all_names}
    requested = [s.strip() for s in sheet_names.split(",") if s.strip()]
    resolved = []
    unmatched = []
    for name in requested:
        if name in normalized_all:
            resolved.append(normalized_all[name])
        else:
            unmatched.append(name)
    if unmatched:
        raise ValueError(f"Không tìm thấy sheet: {', '.join(unmatched)}")
    if not resolved:
        raise ValueError("Không có sheet hợp lệ nào được chọn")
    return resolved


def read_sheet(source, sheet_name):
    cells = json.loads(structural.read_sheet(source, sheet_name))
    rows_map = {}
    for cell in cells:
        rows_map.setdefault(cell["row"], []).append((cell["col"], cell["value"]))

    rows = []
    for r in sorted(rows_map):
        cols = rows_map[r]
        row_vals = [None] * (max(c for c, _ in cols) + 1)
        for c, v in cols:
            row_vals[c] = v
        rows.append((r + 1, row_vals))
    return rows


def read_merges(source, sheet_name):
    """Trả về danh sách vùng ô gộp: [(row_start, col_start, row_end, col_end), ...],
    row đã +1 để khớp với hệ toạ độ của read_sheet/rows ở trên, col giữ 0-based."""
    raw = json.loads(structural.read_merges(source, sheet_name))
    return [(r0 + 1, c0, r1 + 1, c1) for r0, c0, r1, c1 in raw]


def rows_to_text(rows):
    lines = []
    for idx, row in rows:
        cells = " | ".join("" if c is None else str(c) for c in row)
        lines.append(f"[row {idx}] {cells}")
    return "\n".join(lines)
