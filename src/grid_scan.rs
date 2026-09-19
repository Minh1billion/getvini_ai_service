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

fn find_markers(rows: &Rows, re: &Regex) -> Vec<Marker> {
    let mut markers = Vec::new();
    let mut seen: HashMap<String, usize> = HashMap::new();
    for (&row, vals) in rows {
        for (col, v) in vals.iter().enumerate() {
            let Some(s) = v else { continue };
            if s.trim().is_empty() || !re.is_match(&normalize(s)) {
                continue;
            }
            let raw = s.trim().to_string();
            let n = seen.entry(raw.clone()).or_insert(0);
            *n += 1;
            let label = if *n == 1 { raw } else { format!("{raw} ({n})") };
            markers.push(Marker { row, col, label });
        }
    }
    markers
}

fn scan(rows: &Rows, re: &Regex) -> Vec<Value> {
    let Some(&max_row) = rows.keys().next_back() else {
        return Vec::new();
    };
    let markers = find_markers(rows, re);
    let mut blocks = Vec::with_capacity(markers.len());

    for m in &markers {
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
            blocks.push(json!({
                "header_row": m.row,
                "header_col": m.col,
                "start_row": null,
                "end_row": null,
                "col_width": 0,
                "label": m.label,
            }));
            continue;
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

        blocks.push(json!({
            "header_row": m.row,
            "header_col": m.col,
            "start_row": start_row,
            "end_row": end_row,
            "col_width": col_width,
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
    fn invalid_input() {
        assert!(scan_marker_blocks("not json", PAT).is_err());
        assert!(scan_marker_blocks("[]", "(").is_err());
    }
}
