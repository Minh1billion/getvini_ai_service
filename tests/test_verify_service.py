import json

from app.domain.qc.verify_service import (
    annotate_mismatches,
    pack_batches,
    verify_blocks,
    verify_blocks_stream,
)


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


def blocks(n, content="x"):
    return [
        {"id": f"S::R{i}C0", "sheet": "S", "scenario": f"k{i}", "row_range": [i, i], "content": content}
        for i in range(n)
    ]


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


def test_pack_batches_never_exceeds_max_4_even_with_huge_context_window():
    batches = pack_batches(blocks(10), [], context_window=1_000_000, reserved_output_tokens=0)
    assert all(1 <= len(b) <= 4 for b in batches)
    assert sum(len(b) for b in batches) == 10
    assert len(batches) == 3


def test_pack_batches_always_at_least_1_scenario_even_if_it_alone_overflows_budget():
    huge_block = blocks(1, content="x" * 100_000)
    small_blocks = blocks(3)
    all_blocks = huge_block + small_blocks
    batches = pack_batches(all_blocks, [], context_window=200, reserved_output_tokens=0)
    assert all(len(b) >= 1 for b in batches)
    total_sent = sum(len(b) for b in batches)
    assert total_sent == len(all_blocks)


def test_pack_batches_shrinks_below_max_when_window_is_tight():
    batches = pack_batches(blocks(8), [], context_window=1764, reserved_output_tokens=0)
    assert sum(len(b) for b in batches) == 8
    assert all(1 <= len(b) <= 3 for b in batches)
    assert len(batches) == 3


def test_pack_batches_respects_custom_min_max():
    batches = pack_batches(blocks(6), [], context_window=1_000_000, reserved_output_tokens=0, max_scenarios_per_batch=2)
    assert all(len(b) <= 2 for b in batches)
    assert sum(len(b) for b in batches) == 6


def test_verify_blocks_stream_yields_progress_per_batch():
    llm = FakeLLM([
        json.dumps({"mismatches": [{"n": 1}]}),
        json.dumps({"mismatches": [{"n": 2}]}),
        json.dumps({"mismatches": []}),
    ])
    cache = MemoryCache()
    events = list(
        verify_blocks_stream(
            llm, blocks(6), [], cache=cache,
            context_window=1_000_000, reserved_output_tokens=0, max_scenarios_per_batch=2,
        )
    )
    assert len(events) == 3
    assert events[0]["batch_index"] == 0
    assert events[0]["total_batches"] == 3
    assert events[-1]["progress"] == 1.0
    assert events[0]["mismatches_so_far"] == [{"n": 1}]
    assert events[1]["mismatches_so_far"] == [{"n": 1}, {"n": 2}]
    assert events[2]["mismatches_so_far"] == [{"n": 1}, {"n": 2}]


def test_verify_blocks_stream_continues_after_batch_error():
    llm = FakeLLM([json.dumps({"mismatches": [{"n": 1}]})])

    class ExplodingLLM(FakeLLM):
        def complete_json(self, system, user):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("boom")
            return super().complete_json(system, user)

    exploding = ExplodingLLM([json.dumps({"mismatches": [{"n": 2}]})])
    events = list(
        verify_blocks_stream(
            exploding, blocks(2), [], cache=MemoryCache(),
            context_window=1_000_000, reserved_output_tokens=0, max_scenarios_per_batch=1,
        )
    )
    assert len(events) == 2
    assert "error" in events[0]
    assert events[1]["batch_mismatches"] == [{"n": 2}]


def test_verify_blocks_default_caps_at_4_scenarios_per_batch():
    llm = FakeLLM([json.dumps({"mismatches": []})] * 3)
    verify_blocks(llm, blocks(10), [], cache=MemoryCache(), context_window=1_000_000, reserved_output_tokens=0)
    assert llm.calls == 3
