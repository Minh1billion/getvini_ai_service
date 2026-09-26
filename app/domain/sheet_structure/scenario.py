import json
import logging

import structural

from app.infra.sheet_reader import list_sheet_names, read_merges, read_sheet, rows_to_text

logger = logging.getLogger("scenario.scan")

# Sau chữ "bản" phải là: khoảng trắng, hết chuỗi (rỗng), hoặc một dấu câu
# (: . , ; ! ? - ... — dùng \p{P} để bắt luôn cả dấu câu Unicode, không chỉ ASCII).
# Ví dụ giờ đều được nhận là tên kịch bản hợp lệ: "Kịch bản", "Kịch bản 1",
# "Kịch bản:", "Kịch bản: ghi chú chung", "Kịch bản.", "Kịch bản-A".
# Vẫn KHÔNG nhận: "Kịch bảnx", "Kịch bản1" (chữ/số dính liền, không phải dấu câu).
MARKER_PATTERN = r"^kịch\s*bản(?:\s|$|\p{P})"


def _has_value(v) -> bool:
    return v is not None and str(v).strip() != ""


def scan_scenarios(rows, merges=None):
    """merges: danh sách (row_start, col_start, row_end, col_end) lấy từ
    sheet_reader.read_merges, hoặc None nếu không có/không muốn dùng.
    Khi có, phạm vi cột của mỗi kịch bản được lấy cố định theo đúng vùng gộp của
    ô tiêu đề "Kịch bản..." (nếu tiêu đề đó có gộp); tiêu đề không gộp thì tự
    rơi về cách đoán độ rộng cũ, không đổi hành vi so với trước."""
    payload = json.dumps(
        [[r, [None if v is None else str(v) for v in vals]] for r, vals in rows],
        ensure_ascii=False,
    )
    if merges:
        merges_payload = json.dumps(list(merges))
        blocks = json.loads(structural.scan_marker_blocks_by_merge(payload, merges_payload, MARKER_PATTERN))
    else:
        blocks = json.loads(structural.scan_marker_blocks(payload, MARKER_PATTERN))
    return [
        {
            "id": f"R{b['header_row']}C{b['header_col']}",
            "scenarioLabel": b["label"],
            "headerRow": b["header_row"],
            "headerCol": b["header_col"],
            # Cột bắt đầu thật sự của vùng dữ liệu. Khi người dùng khai báo phạm vi
            # tường minh (vd "Kịch bản E [A:B]"), giá trị này lấy theo đúng khai báo
            # đó chứ không mặc định trùng với headerCol.
            "colStart": b.get("col_start", b["header_col"]),
            "startRow": b["start_row"],
            "endRow": b["end_row"],
            "colWidth": b["col_width"],
            "rangeDeclared": b.get("range_declared", False),
        }
        for b in blocks
    ]


def block_rows(rows, block):
    if block["startRow"] is None:
        return []
    rows_map = dict(rows)
    start_col = block.get("colStart", block.get("headerCol", 0))
    end_col = start_col + block["colWidth"]
    return [(r, rows_map.get(r, [])[start_col:end_col]) for r in range(block["startRow"], block["endRow"] + 1)]


def scan_sheet(sheet_name, rows, merges=None):
    return [
        {
            "id": f"{sheet_name}::{b['id']}",
            "sheet": sheet_name,
            "scenarioLabel": b["scenarioLabel"],
            "headerRow": b["headerRow"],
            "colStart": b["colStart"],
            "startRow": b["startRow"],
            "endRow": b["endRow"],
            "colWidth": b["colWidth"],
            "rangeDeclared": b["rangeDeclared"],
        }
        for b in scan_scenarios(rows, merges)
        if b["startRow"] is not None
    ]


def scan_sheet_units(sheet_name, rows, multi_sheet, blocks=None, scenario_ids=None):
    blocks = blocks or []
    units = []
    for r, vals in rows:
        block = next((b for b in blocks if b["startRow"] is not None and b["startRow"] <= r <= b["endRow"]), None)
        if scenario_ids is not None and (block is None or block["id"] not in scenario_ids):
            continue
        for c, v in enumerate(vals):
            if not _has_value(v):
                continue
            location = f"R{r}C{c + 1}"
            if multi_sheet:
                location = f"{sheet_name}!{location}"
            units.append({
                "location": location,
                "text": str(v),
                "sheet": sheet_name,
                "scenario": block["scenarioLabel"] if block else None,
                "scenarioId": block["id"] if block else None,
            })
    return units


def scan_content_blocks(sheet_name, rows, scenario_ids=None, merges=None):
    blocks = []
    current_ids = []
    for b in scan_scenarios(rows, merges):
        if b["startRow"] is None:
            continue
        scenario_id = f"{sheet_name}::{b['id']}"
        current_ids.append(scenario_id)
        if scenario_ids is not None and scenario_id not in scenario_ids:
            continue
        blocks.append({
            "id": scenario_id,
            "sheet": sheet_name,
            "scenario": b["scenarioLabel"],
            "row_range": [b["startRow"], b["endRow"]],
            "content": rows_to_text(block_rows(rows, b)),
        })
    if scenario_ids is not None and not blocks:
        logger.warning(
            "[SCENARIO_DEBUG] scan_content_blocks sheet=%s requested_scenario_ids=%s current_scenario_ids=%s -> KHONG KHOP (0 block), co the file da bi thay doi/lech row so voi luc chon kich ban",
            sheet_name, sorted(scenario_ids), current_ids,
        )
    return blocks


def describe_workbook(path):
    names = list_sheet_names(path)
    return {
        "sheets": names,
        "scenarios": {name: scan_sheet(name, read_sheet(path, name), read_merges(path, name)) for name in names},
    }