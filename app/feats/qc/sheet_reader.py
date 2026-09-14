import json
import structural as sc


def read_sheet(source, sheet_name):
    raw = sc.read_sheet(source, sheet_name)
    cells = json.loads(raw)
    rows_map = {}
    for cell in cells:
        rows_map.setdefault(cell["row"], []).append((cell["col"], cell["value"]))

    rows = []
    for r in sorted(rows_map):
        cols = rows_map[r]
        max_col = max(c for c, _ in cols)
        row_vals = [None] * (max_col + 1)
        for c, v in cols:
            row_vals[c] = v
        rows.append((r + 1, row_vals))
    return rows


def rows_to_text(rows):
    lines = []
    for idx, row in rows:
        cells = " | ".join("" if c is None else str(c) for c in row)
        lines.append(f"[row {idx}] {cells}")
    return "\n".join(lines)