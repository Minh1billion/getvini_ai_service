from app.domain.sheet_structure.scenario import MARKER_PATTERN, block_rows, scan_content_blocks, scan_scenarios, scan_sheet, scan_sheet_units

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
        "colStart": 0,
        "startRow": 3,
        "endRow": 4,
        "colWidth": 2,
        "rangeDeclared": False,
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


def test_marker_pattern_accepts_punctuation_after_ban():
    # "Kịch bản:" trước đây KHÔNG được nhận (chỉ nhận khoảng trắng/hết chuỗi sau
    # chữ "bản"). Giờ dấu câu ngay sau "bản" cũng được coi là tên kịch bản hợp lệ.
    rows = [
        (1, ["Kịch bản: ghi chú chung"]),
        (2, ["x1", "x2"]),
    ]
    blocks = scan_scenarios(rows)
    assert len(blocks) == 1
    assert blocks[0]["scenarioLabel"] == "Kịch bản: ghi chú chung"
    assert blocks[0]["startRow"] == 2

    # Vẫn không nhận khi dính liền chữ/số, không phải dấu câu hay khoảng trắng.
    assert scan_scenarios([(1, ["Kịch bảnx"])]) == []
    assert scan_scenarios([(1, ["Kịch bản1"])]) == []


def test_declared_range_ignores_stray_cell_far_away():
    # Tái hiện "Ca 5": ô rác ở cột F (index 5) không được nằm trong phạm vi [A:B]
    # đã khai báo, nên không còn làm kịch bản bị nối nhầm sang dòng phía dưới nữa.
    rows = [
        (1, ["Kịch bản E [A:B]"]),
        (2, ["e1", "e2"]),
        (3, [None, None, None, None, None, "THỪA"]),
        (4, ["e3", "e4"]),
    ]
    block = scan_scenarios(rows)[0]
    assert block["scenarioLabel"] == "Kịch bản E"
    assert block["colStart"] == 0
    assert block["colWidth"] == 2
    assert block["rangeDeclared"] is True
    assert block["startRow"] == 2
    assert block["endRow"] == 2
    assert block_rows(rows, block) == [(2, ["e1", "e2"])]