use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::prelude::*;

mod grid_scan;
mod io;
mod lookup;
mod tagger;
mod tokenizer;

#[pymodule]
mod structural {
    use super::*;

    #[pyfunction]
    fn read_sheet(source: &str, sheet_name: &str) -> PyResult<String> {
        io::read_sheet(source, sheet_name)
    }

    #[pyfunction]
    fn tokenize(text: &str) -> Vec<String> {
        tokenizer::tokenize(text)
    }

    #[pyfunction]
    fn tag(token: &str) -> Vec<(String, &'static str)> {
        tagger::tag(token)
    }

    #[pyfunction]
    fn register_set(name: &str, path: &str) -> PyResult<usize> {
        lookup::register_set(name, path).map_err(|e| PyIOError::new_err(format!("{path}: {e}")))
    }

    #[pyfunction]
    #[pyo3(signature = (token, set_names, ci=true))]
    fn contains_any(token: &str, set_names: Vec<String>, ci: bool) -> bool {
        lookup::contains_any(token, &set_names, ci)
    }

    #[pyfunction]
    fn scan_marker_blocks(rows_json: &str, pattern: &str) -> PyResult<String> {
        grid_scan::scan_marker_blocks(rows_json, pattern).map_err(PyValueError::new_err)
    }
}
