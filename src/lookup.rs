use std::collections::{HashMap, HashSet};
use std::fs;
use std::io;
use std::sync::{OnceLock, RwLock};

type Sets = HashMap<String, HashSet<String>>;

static SETS: OnceLock<RwLock<Sets>> = OnceLock::new();

fn sets() -> &'static RwLock<Sets> {
    SETS.get_or_init(|| RwLock::new(HashMap::new()))
}

pub fn register_set(name: &str, path: &str) -> io::Result<usize> {
    let set: HashSet<String> = fs::read_to_string(path)?
        .lines()
        .map(|l| l.trim().to_string())
        .filter(|l| !l.is_empty())
        .collect();
    let len = set.len();
    sets().write().unwrap().insert(name.to_string(), set);
    Ok(len)
}

pub fn contains_any(token: &str, set_names: &[String], ci: bool) -> bool {
    let guard = sets().read().unwrap();
    let lower = if ci { Some(token.to_lowercase()) } else { None };
    set_names.iter().filter_map(|n| guard.get(n)).any(|s| {
        s.contains(token) || lower.as_ref().is_some_and(|l| s.contains(l))
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn write_tmp(name: &str, content: &str) -> String {
        let path = std::env::temp_dir().join(format!("lookup_test_{name}.txt"));
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(content.as_bytes()).unwrap();
        path.to_string_lossy().into_owned()
    }

    fn names(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn empty_set() {
        let p = write_tmp("empty", "\n  \n");
        assert_eq!(register_set("t_empty", &p).unwrap(), 0);
        assert!(!contains_any("hello", &names(&["t_empty"]), true));
    }

    #[test]
    fn unknown_set() {
        assert!(!contains_any("hello", &names(&["t_missing"]), true));
        assert!(!contains_any("hello", &[], true));
    }

    #[test]
    fn case_insensitive() {
        let p = write_tmp("ci", "hello\nXin\n");
        register_set("t_ci", &p).unwrap();
        let n = names(&["t_ci"]);
        assert!(contains_any("Hello", &n, true));
        assert!(!contains_any("Hello", &n, false));
        assert!(contains_any("Xin", &n, false));
        assert!(!contains_any("xin", &n, false));
    }

    #[test]
    fn any_of_multiple() {
        let a = write_tmp("a", "foo\n");
        let b = write_tmp("b", "bar\n");
        register_set("t_a", &a).unwrap();
        register_set("t_b", &b).unwrap();
        let n = names(&["t_a", "t_b", "t_none"]);
        assert!(contains_any("foo", &n, true));
        assert!(contains_any("bar", &n, true));
        assert!(!contains_any("baz", &n, true));
    }

    #[test]
    fn missing_file() {
        assert!(register_set("t_x", "/nonexistent/file.txt").is_err());
    }
}
