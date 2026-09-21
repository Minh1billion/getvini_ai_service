import json

from app.domain.qc.verify_service import (
    _JSON_WRAPPER_TOKENS,
    annotate_mismatches,
    pack_batches,
    verify_blocks,
)
from app.infra.llm.prompts import VERIFY_SYSTEM
from app.infra.llm.tokens import estimate_tokens


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
    sample = blocks(8)
    block_tokens = max(estimate_tokens(json.dumps(b, ensure_ascii=False)) for b in sample)
    fixed_overhead = (
        estimate_tokens(VERIFY_SYSTEM)
        + estimate_tokens(json.dumps([], ensure_ascii=False))
        + _JSON_WRAPPER_TOKENS
    )
    context_window = fixed_overhead + 3 * block_tokens + block_tokens // 2
    batches = pack_batches(sample, [], context_window=context_window, reserved_output_tokens=0)
    assert sum(len(b) for b in batches) == 8
    assert all(1 <= len(b) <= 3 for b in batches)
    assert len(batches) == 3


def test_pack_batches_respects_custom_min_max():
    batches = pack_batches(blocks(6), [], context_window=1_000_000, reserved_output_tokens=0, max_scenarios_per_batch=2)
    assert all(len(b) <= 2 for b in batches)
    assert sum(len(b) for b in batches) == 6


def test_verify_blocks_default_caps_at_4_scenarios_per_batch():
    llm = FakeLLM([json.dumps({"mismatches": []})] * 3)
    verify_blocks(llm, blocks(10), [], cache=MemoryCache(), context_window=1_000_000, reserved_output_tokens=0)
    assert llm.calls == 3