from app.domain.spellcheck.service import check_unit, is_error, parse_whitelist


def test_whitelist_wins():
    assert is_error("zzzqq", set(), "both")
    assert not is_error("zzzqq", {"zzzqq"}, "both")


def test_lang_mapping():
    assert not is_error("hello", set(), "en")
    assert is_error("hello", set(), "vi")
    assert not is_error("hello", set(), "both")
    assert not is_error("hello", set(), "unknown")


def test_case_insensitive():
    assert not is_error("Hello", set(), "en")


def test_parse_whitelist():
    assert parse_whitelist(None) == set()
    assert parse_whitelist("a, b ,c") == {"a", "b", "c"}


def test_check_unit_only_words():
    unit = {"location": "R1C1", "text": "hello wrold 123 https://a.com", "sheet": "S", "scenario": None, "scenarioId": None}
    errors = check_unit(unit, set(), "en")
    assert [e["token"] for e in errors] == ["wrold"]
    assert errors[0]["location"] == "R1C1"
    assert errors[0]["sheet"] == "S"
