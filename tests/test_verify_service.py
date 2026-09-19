import json

from app.domain.qc.verify_service import annotate_mismatches, verify_blocks


class FakeLLM:
    provider = "fake"
    model = "m"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, system, user):
        self.calls += 1
        return self.responses.pop(0)


class MemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value


def blocks(n):
    return [{"id": f"S::R{i}C0", "sheet": "S", "scenario": f"k{i}", "row_range": [i, i], "content": "x"} for i in range(n)]


def test_batching_and_cache():
    llm = FakeLLM([json.dumps({"mismatches": [{"n": 1}]}), json.dumps({"mismatches": [{"n": 2}]})])
    cache = MemoryCache()
    result = verify_blocks(llm, blocks(3), [], batch_size=2, cache=cache)
    assert result == {"mismatches": [{"n": 1}, {"n": 2}]}
    assert llm.calls == 2
    again = verify_blocks(llm, blocks(3), [], batch_size=2, cache=cache)
    assert again == result
    assert llm.calls == 2


def test_invalid_json_batch_skipped():
    llm = FakeLLM(["not json", json.dumps({"mismatches": [{"n": 2}]})])
    result = verify_blocks(llm, blocks(2), [], batch_size=1, cache=MemoryCache())
    assert result == {"mismatches": [{"n": 2}]}


def test_annotate_mismatches():
    content = blocks(2)
    report = {"mismatches": [{"row_range": [1, 1], "id": "wrong"}, {"row_range": [9, 9]}, {}]}
    out = annotate_mismatches(report, content, "S")
    first, second, third = out["mismatches"]
    assert first["id"] == "S::R1C0" and first["scenario"] == "k1"
    assert second["sheet"] == "S" and "scenario" not in second
    assert third == {"sheet": "S"}
