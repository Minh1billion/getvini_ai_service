import logging
import re
import unicodedata

from app.feats.qc.sheet_reader import rows_to_text

logger = logging.getLogger("scenario.scan")

MARKER_RE = re.compile(r"^kịch\s*bản(?:\s|$)")


def normalize_text(value) -> str:
    text = unicodedata.normalize("NFC", str(value).strip())
    return text.casefold()


def _has_value(v) -> bool:
    return v is not None and str(v).strip() != ""


def _find_marker_cells(vals):
    """Scan every column in the row and return a list of (column_index, value)
    for every cell whose normalized text matches the scenario marker.
    A row can contain more than one marker (e.g. a main scenario column and
    a "Fix" variant column further to the right), so every match is returned,
    not just the first one."""
    return [(c, v) for c, v in enumerate(vals) if _has_value(v) and MARKER_RE.match(normalize_text(v))]


def scan_scenarios(rows):
    rows_map = dict(rows)
    if not rows_map:
        return []

    max_row = max(rows_map)

    all_markers = []
    label_seen = {}

    for r in sorted(rows_map):
        vals = rows_map[r]

        for header_col, marker_cell in _find_marker_cells(vals):
            raw_label = str(marker_cell).strip()

            label_seen[raw_label] = label_seen.get(raw_label, 0) + 1
            occurrence = label_seen[raw_label]

            label = (
                raw_label
                if occurrence == 1
                else f"{raw_label} ({occurrence})"
            )

            all_markers.append({
                "row": r,
                "col": header_col,
                "label": label,
            })

    blocks = []

    for i, marker in enumerate(all_markers):
        header_row = marker["row"]
        header_col = marker["col"]
        label = marker["label"]

        start_row = None

        r = header_row + 1

        while r <= max_row:
            vals = rows_map.get(r, [])

            values_from_header = vals[header_col:]

            if any(_has_value(v) for v in values_from_header):
                start_row = r
                break

            r += 1

        if start_row is None:
            blocks.append({
                "id": f"R{header_row}C{header_col}",
                "scenarioLabel": label,
                "headerRow": header_row,
                "headerCol": header_col,
                "startRow": None,
                "endRow": None,
                "colWidth": 0,
            })
            continue

        col_width = 0
        end_row = start_row

        r = start_row

        while r <= max_row:
            vals = rows_map.get(r, [])
            values_from_header = vals[header_col:]

            if not any(_has_value(v) for v in values_from_header):
                break

            row_width = 0

            for v in values_from_header:
                if _has_value(v):
                    row_width += 1
                else:
                    break

            col_width = max(col_width, row_width)
            end_row = r

            r += 1

        boundary = end_row + 1

        for next_marker in all_markers:
            next_row = next_marker["row"]
            next_col = next_marker["col"]

            if next_row <= header_row:
                continue

            if (
                header_col
                <= next_col
                < header_col + col_width
            ):
                boundary = next_row
                break

        if boundary <= end_row:
            end_row = boundary - 1

        blocks.append({
            "id": f"R{header_row}C{header_col}",
            "scenarioLabel": label,
            "headerRow": header_row,
            "headerCol": header_col,
            "startRow": start_row,
            "endRow": end_row,
            "colWidth": col_width,
        })

    return blocks


def block_rows(rows, block):
    if block["startRow"] is None:
        return []
    rows_map = dict(rows)
    start_col = block.get("headerCol", 0)
    end_col = start_col + block["colWidth"]
    return [(r, rows_map.get(r, [])[start_col:end_col]) for r in range(block["startRow"], block["endRow"] + 1)]


def scan_sheet(sheet_name, rows):
    blocks = scan_scenarios(rows)
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
        for b in blocks if b["startRow"] is not None
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


def scan_units(sheet_name, rows, multi_sheet, scenario_ids=None):
    units = []
    current_ids = []
    matched_any = False
    for b in scan_scenarios(rows):
        if b["startRow"] is None:
            continue
        scenario_id = f"{sheet_name}::{b['id']}"
        current_ids.append(scenario_id)
        if scenario_ids is not None and scenario_id not in scenario_ids:
            continue
        matched_any = True
        header_col = b.get("headerCol", 0)
        for r, vals in block_rows(rows, b):
            for c, v in enumerate(vals):
                if not _has_value(v):
                    continue
                location = f"R{r}C{header_col + c + 1}"
                if multi_sheet:
                    location = f"{sheet_name}!{location}"
                units.append({
                    "location": location,
                    "text": str(v),
                    "sheet": sheet_name,
                    "scenario": b["scenarioLabel"],
                    "scenarioId": scenario_id,
                })
    if scenario_ids is not None and not matched_any:
        logger.warning(
            "[SCENARIO_DEBUG] scan_units sheet=%s requested_scenario_ids=%s current_scenario_ids=%s -> KHONG KHOP (0 unit), co the file da bi thay doi/lech row so voi luc chon kich ban",
            sheet_name, sorted(scenario_ids), current_ids,
        )
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
