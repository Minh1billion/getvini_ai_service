from app.domain.sheet_structure.scenario import block_rows, scan_content_blocks, scan_scenarios, scan_sheet, scan_sheet_units

ROWS = [
    (2, ["Kịch bản 1", None, None, "Kịch bản Fix"]),
    (3, ["a", "b", None, "c", "d"]),
    (4, ["e", None, None, "f"]),
    (7, ["Kịch bản 1"]),
    (8, ["g"]),
    (10, ["Kịch bản 3"]),
]


def test_scan_scenarios_shape():
    blocks = scan_scenarios(ROWS)
    assert [b["id"] for b in blocks] == ["R2C0", "R2C3", "R7C0", "R10C0"]
    assert blocks[0] == {
        "id": "R2C0",
        "scenarioLabel": "Kịch bản 1",
        "headerRow": 2,
        "headerCol": 0,
        "startRow": 3,
        "endRow": 4,
        "colWidth": 2,
    }
    assert blocks[2]["scenarioLabel"] == "Kịch bản 1 (2)"
    assert blocks[3]["startRow"] is None


def test_scan_sheet_skips_empty_blocks():
    result = scan_sheet("S", ROWS)
    assert [b["id"] for b in result] == ["S::R2C0", "S::R2C3", "S::R7C0"]


def test_scan_content_blocks_filter():
    blocks = scan_content_blocks("S", ROWS, {"S::R2C3"})
    assert len(blocks) == 1
    assert blocks[0]["row_range"] == [3, 4]
    assert blocks[0]["content"] == "[row 3] c | d\n[row 4] f"


def test_block_rows_offset():
    block = scan_scenarios(ROWS)[1]
    assert block_rows(ROWS, block) == [(3, ["c", "d"]), (4, ["f"])]


def test_scan_sheet_units_locations():
    units = scan_sheet_units("S", [(1, ["a", None, "b"])], True)
    assert [u["location"] for u in units] == ["S!R1C1", "S!R1C3"]


def test_no_markers():
    assert scan_scenarios([(1, ["x"])]) == []
    assert scan_scenarios([]) == []
