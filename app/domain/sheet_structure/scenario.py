import json
import logging

import structural

from app.infra.sheet_reader import list_sheet_names, read_sheet, rows_to_text

logger = logging.getLogger("scenario.scan")

MARKER_PATTERN = r"^kịch\s*bản(?:\s|$)"


def _has_value(v) -> bool:
    return v is not None and str(v).strip() != ""


def scan_scenarios(rows):
    payload = json.dumps(
        [[r, [None if v is None else str(v) for v in vals]] for r, vals in rows],
        ensure_ascii=False,
    )
    blocks = json.loads(structural.scan_marker_blocks(payload, MARKER_PATTERN))
    return [
        {
            "id": f"R{b['header_row']}C{b['header_col']}",
            "scenarioLabel": b["label"],
            "headerRow": b["header_row"],
            "headerCol": b["header_col"],
            "startRow": b["start_row"],
            "endRow": b["end_row"],
            "colWidth": b["col_width"],
        }
        for b in blocks
    ]


def block_rows(rows, block):
    if block["startRow"] is None:
        return []
    rows_map = dict(rows)
    start_col = block.get("headerCol", 0)
    end_col = start_col + block["colWidth"]
    return [(r, rows_map.get(r, [])[start_col:end_col]) for r in range(block["startRow"], block["endRow"] + 1)]


def scan_sheet(sheet_name, rows):
    return [
        {
            "id": f"{sheet_name}::{b['id']}",
            "sheet": sheet_name,
            "scenarioLabel": b["scenarioLabel"],
            "headerRow": b["headerRow"],
            "startRow": b["startRow"],
            "endRow": b["endRow"],
            "colWidth": b["colWidth"],
        }
        for b in scan_scenarios(rows)
        if b["startRow"] is not None
    ]


def scan_sheet_units(sheet_name, rows, multi_sheet):
    units = []
    for r, vals in rows:
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
                "scenario": None,
                "scenarioId": None,
            })
    return units


def scan_content_blocks(sheet_name, rows, scenario_ids=None):
    blocks = []
    current_ids = []
    for b in scan_scenarios(rows):
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
    return {"sheets": names, "scenarios": {name: scan_sheet(name, read_sheet(path, name)) for name in names}}
