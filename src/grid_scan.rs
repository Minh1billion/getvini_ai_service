use regex::Regex;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap};
use unicode_normalization::UnicodeNormalization;

type Cell = Option<String>;
type Rows = BTreeMap<i64, Vec<Cell>>;

struct Marker {
    row: i64,
    col: usize,
    label: String,
    /// Phạm vi cột do người dùng khai báo tường minh, ví dụ "[A:B]" -> Some((0, 1)).
    /// None nghĩa là không khai báo, dùng lại cách đoán độ rộng như cũ.
    declared_range: Option<(usize, usize)>,
}

fn has_value(v: &Cell) -> bool {
    v.as_ref().is_some_and(|s| !s.trim().is_empty())
}

fn normalize(s: &str) -> String {
    s.trim().nfc().collect::<String>().to_lowercase()
}

fn tail(rows: &Rows, row: i64, col: usize) -> &[Cell] {
    rows.get(&row).and_then(|v| v.get(col..)).unwrap_or(&[])
}

/// Chuyển tên cột kiểu Excel ("A", "B", ..., "Z", "AA", ...) sang chỉ số 0-based.
fn col_letters_to_index(s: &str) -> Option<usize> {
    if s.is_empty() || !s.chars().all(|c| c.is_ascii_alphabetic()) {
        return None;
    }
    let mut idx: i64 = 0;
    for ch in s.chars() {
        idx = idx * 26 + (ch.to_ascii_uppercase() as i64 - 'A' as i64 + 1);
    }
    Some((idx - 1) as usize)
}

/// Tách phần khai báo phạm vi cột "[A:B]" hoặc "[A]" ở cuối tên kịch bản, nếu có.
/// Trả về (tên kịch bản đã bỏ phần khai báo, phạm vi cột nếu hợp lệ).
fn parse_declared_range(raw: &str) -> (String, Option<(usize, usize)>) {
    let trimmed = raw.trim();
    if trimmed.ends_with(']') {
        if let Some(open) = trimmed.rfind('[') {
            let inner = trimmed[open + 1..trimmed.len() - 1].trim();
            let label = trimmed[..open].trim().to_string();
            let range = match inner.split_once(':') {
                Some((a, b)) => match (col_letters_to_index(a.trim()), col_letters_to_index(b.trim())) {
                    (Some(x), Some(y)) => Some((x.min(y), x.max(y))),
                    _ => None,
                },
                None => col_letters_to_index(inner).map(|c| (c, c)),
            };
            if let Some(r) = range {
                return (label, Some(r));
            }
        }
    }
    (trimmed.to_string(), None)
}

fn find_markers(rows: &Rows, re: &Regex) -> Vec<Marker> {
    let mut markers = Vec::new();
    let mut seen: HashMap<String, usize> = HashMap::new();
    for (&row, vals) in rows {
        for (col, v) in vals.iter().enumerate() {
            let Some(s) = v else { continue };
            if s.trim().is_empty() || !re.is_match(&normalize(s)) {
                continue;
            }
            let (clean, declared_range) = parse_declared_range(s.trim());
            let n = seen.entry(clean.clone()).or_insert(0);
            *n += 1;
            let label = if *n == 1 { clean } else { format!("{clean} ({n})") };
            markers.push(Marker { row, col, label, declared_range });
        }
    }
    markers
}

/// "Thước" kiểm tra 1 dòng có còn dữ liệu hay không, giới hạn đúng trong [cs, ce].
fn window_has_value(rows: &Rows, row: i64, cs: usize, ce: usize) -> bool {
    rows.get(&row)
        .is_some_and(|vals| (cs..=ce).any(|c| vals.get(c).is_some_and(has_value)))
}

fn scan(rows: &Rows, re: &Regex) -> Vec<Value> {
    let Some(&max_row) = rows.keys().next_back() else {
        return Vec::new();
    };
    let markers = find_markers(rows, re);
    let mut blocks = Vec::with_capacity(markers.len());

    for m in &markers {
        // Nếu người dùng đã khai báo phạm vi cột (vd "[A:B]"), chỉ được nhìn đúng
        // trong phạm vi đó. Nếu không khai báo, giữ nguyên cách cũ: nhìn từ cột
        // chứa tên kịch bản cho tới hết dòng (tail).
        let row_has_value = |r: i64| match m.declared_range {
            Some((cs, ce)) => window_has_value(rows, r, cs, ce),
            None => tail(rows, r, m.col).iter().any(has_value),
        };

        let mut start = None;
        let mut r = m.row + 1;
        while r <= max_row {
            if row_has_value(r) {
                start = Some(r);
                break;
            }
            r += 1;
        }

        let Some(start_row) = start else {
            let (col_start, col_width) = m.declared_range.map_or((m.col, 0), |(cs, ce)| (cs, ce - cs + 1));
            blocks.push(json!({
                "header_row": m.row,
                "header_col": m.col,
                "col_start": col_start,
                "start_row": null,
                "end_row": null,
                "col_width": if m.declared_range.is_some() { col_width } else { 0 },
                "range_declared": m.declared_range.is_some(),
                "label": m.label,
            }));
            continue;
        };

        let (col_start, col_end, col_width) = match m.declared_range {
            // Có khai báo: độ rộng cố định theo đúng những gì người dùng ghi,
            // không đoán, không bị ô lạc ở xa làm phình ra.
            Some((cs, ce)) => (cs, ce, ce - cs + 1),
            // Không khai báo: giữ nguyên cách cũ, đoán độ rộng theo dòng "rộng nhất".
            None => {
                let mut w = 0usize;
                let mut r = start_row;
                while r <= max_row {
                    let t = tail(rows, r, m.col);
                    if !t.iter().any(has_value) {
                        break;
                    }
                    w = w.max(t.iter().take_while(|v| has_value(v)).count());
                    r += 1;
                }
                (m.col, m.col + w - 1, w)
            }
        };

        let mut end_row = start_row;
        let mut r = start_row;
        while r <= max_row {
            if !row_has_value(r) {
                break;
            }
            end_row = r;
            r += 1;
        }

        let boundary = markers
            .iter()
            .find(|n| n.row > m.row && col_start <= n.col && n.col <= col_end)
            .map_or(end_row + 1, |n| n.row);
        if boundary <= end_row {
            end_row = boundary - 1;
        }

        blocks.push(json!({
            "header_row": m.row,
            "header_col": m.col,
            "col_start": col_start,
            "start_row": start_row,
            "end_row": end_row,
            "col_width": col_width,
            "range_declared": m.declared_range.is_some(),
            "label": m.label,
        }));
    }
    blocks
}

pub fn scan_marker_blocks(rows_json: &str, pattern: &str) -> Result<String, String> {
    let parsed: Vec<(i64, Vec<Cell>)> = serde_json::from_str(rows_json).map_err(|e| e.to_string())?;
    let re = Regex::new(pattern).map_err(|e| e.to_string())?;
    let rows: Rows = parsed.into_iter().collect();
    serde_json::to_string(&scan(&rows, &re)).map_err(|e| e.to_string())
}

/// (row_start, col_start, row_end, col_end) — tất cả inclusive, cùng hệ toạ độ
/// (row đã +1 để khớp Excel) với `rows` truyền vào từ scenario.py.
type MergeRect = (i64, usize, i64, usize);

/// Nếu (row, col) nằm trong một vùng gộp, trả về (col_start, col_end) của vùng đó.
/// Nếu không, trả về None — nghĩa là ô đơn, không gộp.
fn merge_col_range(row: i64, col: usize, merges: &[MergeRect]) -> Option<(usize, usize)> {
    merges
        .iter()
        .find(|&&(r0, c0, r1, c1)| row >= r0 && row <= r1 && col >= c0 && col <= c1)
        .map(|&(_, c0, _, c1)| (c0, c1))
}

/// Danh sách các đoạn cột "có dữ liệu thật" trên một dòng: mỗi ô rời có giá trị là
/// một đoạn 1 cột; mỗi vùng gộp phủ qua dòng này mà ô neo có giá trị là một đoạn
/// bằng đúng bề ngang của vùng gộp đó (kể cả khi vùng gộp gộp theo chiều dọc và ô
/// neo nằm ở một dòng khác phía trên).
fn occupied_segments(rows: &Rows, row: i64, merges: &[MergeRect]) -> Vec<(usize, usize)> {
    let mut segs = Vec::new();
    if let Some(vals) = rows.get(&row) {
        for (c, v) in vals.iter().enumerate() {
            if has_value(v) {
                segs.push(merge_col_range(row, c, merges).unwrap_or((c, c)));
            }
        }
    }
    for &(r0, c0, r1, c1) in merges {
        if row >= r0 && row <= r1 && rows.get(&r0).and_then(|v| v.get(c0)).is_some_and(has_value) {
            segs.push((c0, c1));
        }
    }
    segs
}

fn intersects(segs: &[(usize, usize)], cs: usize, ce: usize) -> bool {
    segs.iter().any(|&(s, e)| s <= ce && e >= cs)
}

fn scan_by_merge(rows: &Rows, re: &Regex, merges: &[MergeRect]) -> Vec<Value> {
    let Some(&max_row) = rows.keys().next_back() else {
        return Vec::new();
    };
    let markers = find_markers(rows, re);
    // Phạm vi cột thật sự của mỗi marker: theo vùng gộp của chính ô tiêu đề, nếu có.
    let ranges: Vec<Option<(usize, usize)>> = markers
        .iter()
        .map(|m| merge_col_range(m.row, m.col, merges))
        .collect();

    let mut blocks = Vec::with_capacity(markers.len());
    for (i, m) in markers.iter().enumerate() {
        let Some((cs, ce)) = ranges[i] else {
            // Tiêu đề không gộp -> giữ nguyên cách đoán độ rộng cũ cho ô này,
            // để không phá các sheet chưa dùng merge.
            blocks.push(scan_one_legacy(rows, &markers, m));
            continue;
        };

        let mut start = None;
        let mut end_row = m.row;
        let mut r = m.row + 1;
        while r <= max_row {
            // Luật 4: một tiêu đề "Kịch bản..." khác giao cột -> dừng ngay, không tính dòng này.
            let blocked = markers.iter().enumerate().any(|(j, n)| {
                j != i
                    && n.row == r
                    && ranges[j].map_or((n.col, n.col), |x| x).0 <= ce
                    && ranges[j].map_or((n.col, n.col), |x| x).1 >= cs
            });
            if blocked {
                break;
            }
            // Luật 3: toàn bộ trống trong đúng phạm vi cột -> dừng.
            if !intersects(&occupied_segments(rows, r, merges), cs, ce) {
                if start.is_some() {
                    break; // đã có dữ liệu trước đó -> dừng hẳn (Ca 2)
                }
                r += 1; // chưa có dữ liệu -> bỏ qua dòng trống, dò tiếp (Ca 1)
                continue;
            }
            if start.is_none() {
                start = Some(r);
            }
            end_row = r;
            r += 1;
        }

        blocks.push(json!({
            "header_row": m.row,
            "header_col": m.col,
            "col_start": cs,
            "start_row": start,
            "end_row": if start.is_some() { Some(end_row) } else { None },
            "col_width": ce - cs + 1,
            "range_declared": true,
            "label": m.label,
        }));
    }
    blocks
}

/// Đúng logic scan() cũ (đoán độ rộng theo dòng rộng nhất), dùng khi tiêu đề không gộp.
fn scan_one_legacy(rows: &Rows, markers: &[Marker], m: &Marker) -> Value {
    let Some(&max_row) = rows.keys().next_back() else {
        return json!({
            "header_row": m.row, "header_col": m.col, "col_start": m.col,
            "start_row": null, "end_row": null, "col_width": 0,
            "range_declared": false, "label": m.label,
        });
    };
    let mut start = None;
    let mut r = m.row + 1;
    while r <= max_row {
        if tail(rows, r, m.col).iter().any(has_value) {
            start = Some(r);
            break;
        }
        r += 1;
    }
    let Some(start_row) = start else {
        return json!({
            "header_row": m.row, "header_col": m.col, "col_start": m.col,
            "start_row": null, "end_row": null, "col_width": 0,
            "range_declared": false, "label": m.label,
        });
    };
    let mut col_width = 0usize;
    let mut end_row = start_row;
    let mut r = start_row;
    while r <= max_row {
        let t = tail(rows, r, m.col);
        if !t.iter().any(has_value) {
            break;
        }
        col_width = col_width.max(t.iter().take_while(|v| has_value(v)).count());
        end_row = r;
        r += 1;
    }
    let boundary = markers
        .iter()
        .find(|n| n.row > m.row && m.col <= n.col && n.col < m.col + col_width)
        .map_or(end_row + 1, |n| n.row);
    if boundary <= end_row {
        end_row = boundary - 1;
    }
    json!({
        "header_row": m.row, "header_col": m.col, "col_start": m.col,
        "start_row": start_row, "end_row": end_row, "col_width": col_width,
        "range_declared": false, "label": m.label,
    })
}

pub fn scan_marker_blocks_by_merge(rows_json: &str, merges_json: &str, pattern: &str) -> Result<String, String> {
    let parsed: Vec<(i64, Vec<Cell>)> = serde_json::from_str(rows_json).map_err(|e| e.to_string())?;
    let merges: Vec<MergeRect> = serde_json::from_str(merges_json).map_err(|e| e.to_string())?;
    let re = Regex::new(pattern).map_err(|e| e.to_string())?;
    let rows: Rows = parsed.into_iter().collect();
    serde_json::to_string(&scan_by_merge(&rows, &re, &merges)).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    const PAT: &str = r"^kịch\s*bản(?:\s|$)";

    fn run(rows: Value) -> Vec<Value> {
        serde_json::from_str(&scan_marker_blocks(&rows.to_string(), PAT).unwrap()).unwrap()
    }

    #[test]
    fn empty() {
        assert!(run(json!([])).is_empty());
    }

    #[test]
    fn multiple_markers_same_row() {
        let b = run(json!([
            [2, ["Kịch bản 1", null, null, "Kịch bản Fix"]],
            [3, ["a", "b", null, "c", "d"]],
            [4, ["e", null, null, "f"]],
        ]));
        assert_eq!(b.len(), 2);
        assert_eq!(b[0]["header_col"], 0);
        assert_eq!(b[0]["start_row"], 3);
        assert_eq!(b[0]["end_row"], 4);
        assert_eq!(b[0]["col_width"], 2);
        assert_eq!(b[1]["header_col"], 3);
        assert_eq!(b[1]["col_width"], 2);
    }

    #[test]
    fn marker_without_data() {
        let b = run(json!([[1, [null, "Kịch bản 1"]], [2, ["x", null]]]));
        assert_eq!(b.len(), 1);
        assert!(b[0]["start_row"].is_null());
        assert_eq!(b[0]["col_width"], 0);
    }

    #[test]
    fn adjacent_blocks() {
        let b = run(json!([
            [2, ["Kịch bản X"]],
            [3, ["a"]],
            [4, ["b"]],
            [5, ["Kịch bản Y"]],
            [6, ["c"]],
        ]));
        assert_eq!(b.len(), 2);
        assert_eq!(b[0]["end_row"], 4);
        assert_eq!(b[1]["start_row"], 6);
    }

    #[test]
    fn duplicate_labels() {
        let b = run(json!([
            [1, ["Kịch bản 1"]],
            [2, ["a"]],
            [4, ["Kịch bản 1"]],
            [5, ["b"]],
        ]));
        assert_eq!(b[0]["label"], "Kịch bản 1");
        assert_eq!(b[1]["label"], "Kịch bản 1 (2)");
    }

    #[test]
    fn normalization_and_non_marker() {
        let b = run(json!([
            [1, ["  KỊCH  BẢN 3 ", "kịch bản"]],
            [2, ["kịch bảnx", "x"]],
        ]));
        assert_eq!(b.len(), 2);
        assert_eq!(b[0]["label"], "KỊCH  BẢN 3");
    }

    #[test]
    fn declared_range_ignores_stray_cell_far_away() {
        // Tái hiện đúng "Ca 5": có ô rác THỪA ở cột F, cách xa bảng Kịch bản E (cột A:B).
        // Nếu không khai báo phạm vi cột -> bị nối nhầm (hành vi cũ, xem test dưới).
        // Nếu khai báo "[A:B]" -> ô rác ở cột F không còn ảnh hưởng gì nữa.
        let b = run(json!([
            [1, ["Kịch bản E [A:B]"]],
            [2, ["e1", "e2"]],
            [3, [null, null, null, null, null, "THỪA"]],
            [4, ["e3", "e4"]],
        ]));
        assert_eq!(b.len(), 1);
        assert_eq!(b[0]["label"], "Kịch bản E");
        assert_eq!(b[0]["start_row"], 2);
        assert_eq!(b[0]["end_row"], 2); // dừng đúng tại dòng trống, không bị nối sang dòng 4
        assert_eq!(b[0]["col_width"], 2);
        assert_eq!(b[0]["col_start"], 0);
        assert_eq!(b[0]["range_declared"], true);
    }

    #[test]
    fn without_declared_range_stray_cell_still_merges_old_behavior() {
        // Không khai báo phạm vi -> giữ nguyên hành vi cũ (vẫn còn lỗi Ca 5) để không phá
        // các sheet chưa kịp cập nhật sang cách khai báo mới.
        let b = run(json!([
            [1, ["Kịch bản E"]],
            [2, ["e1", "e2"]],
            [3, [null, null, null, null, null, "THỪA"]],
            [4, ["e3", "e4"]],
        ]));
        assert_eq!(b[0]["end_row"], 4);
        assert_eq!(b[0]["range_declared"], false);
    }

    #[test]
    fn declared_single_column() {
        let b = run(json!([
            [1, ["Kịch bản Z [C]"]],
            [2, [null, null, "z1"]],
        ]));
        assert_eq!(b[0]["col_start"], 2);
        assert_eq!(b[0]["col_width"], 1);
    }

    fn run_merge(rows: Value, merges: Value) -> Vec<Value> {
        serde_json::from_str(&scan_marker_blocks_by_merge(&rows.to_string(), &merges.to_string(), PAT).unwrap()).unwrap()
    }

    #[test]
    fn merge_header_fixes_width_no_guessing() {
        // Tiêu đề "Kịch bản 1" gộp A1:B1 -> phạm vi cố định A:B, dù dòng dữ liệu có
        // rộng hơn hay hẹp hơn cũng mặc kệ, không đoán theo dữ liệu nữa.
        let b = run_merge(
            json!([
                [1, ["Kịch bản 1"]],
                [2, ["a", "b", "thua"]],
            ]),
            json!([[1, 0, 1, 1]]),
        );
        assert_eq!(b[0]["col_start"], 0);
        assert_eq!(b[0]["col_width"], 2);
        assert_eq!(b[0]["range_declared"], true);
        assert_eq!(b[0]["end_row"], 2);
    }

    #[test]
    fn merge_stray_cell_outside_range_ignored() {
        // Tái hiện Ca 5: ô THỪA ở cột F nằm ngoài phạm vi gộp A:B của tiêu đề
        // -> không kích hoạt luật "giao ít nhất 1 cột", dòng trống vẫn bị coi là kết thúc.
        let b = run_merge(
            json!([
                [1, ["Kịch bản E"]],
                [2, ["e1", "e2"]],
                [3, [null, null, null, null, null, "THỪA"]],
                [4, ["e3", "e4"]],
            ]),
            json!([[1, 0, 1, 1]]),
        );
        assert_eq!(b[0]["start_row"], 2);
        assert_eq!(b[0]["end_row"], 2); // dừng đúng, không nối nhầm sang dòng 4
    }

    #[test]
    fn merge_overlapping_stray_cell_counts_as_data() {
        // Ô rác ở cột B (giao với phạm vi A:B) khiến dòng được tính là còn dữ liệu.
        let b = run_merge(
            json!([
                [1, ["Kịch bản E"]],
                [2, ["e1", "e2"]],
                [3, [null, "vẫn tính vì giao cột B"]],
                [4, ["e3", "e4"]],
            ]),
            json!([[1, 0, 1, 1]]),
        );
        assert_eq!(b[0]["end_row"], 4);
    }

    #[test]
    fn merge_new_marker_intersecting_range_cuts_off() {
        // "Kịch bản M" ở dòng 3 cột A -> giao với phạm vi A:B của "Kịch bản K" -> cắt tại đó.
        let b = run_merge(
            json!([
                [1, ["Kịch bản K"]],
                [2, ["k1", "k2"]],
                [3, ["Kịch bản M"]],
                [4, ["m1", "m2"]],
            ]),
            json!([[1, 0, 1, 1], [3, 0, 3, 1]]),
        );
        assert_eq!(b.len(), 2);
        assert_eq!(b[0]["label"], "Kịch bản K");
        assert_eq!(b[0]["end_row"], 2);
        assert_eq!(b[1]["label"], "Kịch bản M");
        assert_eq!(b[1]["start_row"], 4);
    }

    #[test]
    fn merge_no_intersection_independent_blocks() {
        // "Kịch bản M" nằm ở cột D:E, không giao với A:B của K -> hoàn toàn độc lập.
        let b = run_merge(
            json!([
                [1, ["Kịch bản K", null, null, "Kịch bản M"]],
                [2, ["k1", "k2", null, "m1", "m2"]],
                [3, ["k3", "k4"]],
            ]),
            json!([[1, 0, 1, 1], [1, 3, 1, 4]]),
        );
        assert_eq!(b.len(), 2);
        assert_eq!(b[0]["end_row"], 3);
        assert_eq!(b[1]["end_row"], 2); // dòng 3 không có gì ở cột D:E -> M dừng ở dòng 2
    }

    #[test]
    fn unmerged_header_falls_back_to_legacy() {
        // Không có merge nào cho header -> giữ nguyên hành vi đoán độ rộng cũ.
        let b = run_merge(
            json!([
                [1, ["Kịch bản 1"]],
                [2, ["a", "b"]],
            ]),
            json!([]),
        );
        assert_eq!(b[0]["range_declared"], false);
        assert_eq!(b[0]["col_width"], 2);
    }

    #[test]
    fn invalid_input() {
        assert!(scan_marker_blocks("not json", PAT).is_err());
        assert!(scan_marker_blocks("[]", "(").is_err());
    }
}
