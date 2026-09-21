import json
import logging

from app.core.config import get_settings
from app.infra.llm import cache as cache_mod
from app.infra.llm.prompts import VERIFY_SYSTEM
from app.infra.llm.tokens import estimate_tokens

logger = logging.getLogger("qc.verify")

VERIFY_PROMPT_VERSION = "v2"

_JSON_WRAPPER_TOKENS = 20


def pack_batches(
    blocks,
    product_info,
    system_prompt=VERIFY_SYSTEM,
    *,
    context_window=None,
    reserved_output_tokens=None,
    min_scenarios_per_batch=None,
    max_scenarios_per_batch=None,
):
    settings = get_settings()
    context_window = context_window or settings.qc_llm_context_window
    reserved_output_tokens = (
        settings.qc_llm_reserved_output_tokens if reserved_output_tokens is None else reserved_output_tokens
    )
    min_scenarios_per_batch = max(1, min_scenarios_per_batch or settings.qc_llm_min_scenarios_per_batch)
    max_scenarios_per_batch = max(
        min_scenarios_per_batch, max_scenarios_per_batch or settings.qc_llm_max_scenarios_per_batch
    )

    fixed_overhead = (
        estimate_tokens(system_prompt)
        + estimate_tokens(json.dumps(product_info, ensure_ascii=False))
        + _JSON_WRAPPER_TOKENS
    )
    budget = context_window - reserved_output_tokens - fixed_overhead
    if budget <= 0:
        logger.warning(
            "QC batch budget <= 0 (context_window=%d, reserved_output=%d, fixed_overhead=%d) — "
            "product_info/system prompt tự nó đã gần lấp đầy context window, mỗi batch sẽ chỉ chứa "
            "đúng %d kịch bản.",
            context_window, reserved_output_tokens, fixed_overhead, min_scenarios_per_batch,
        )
        budget = 0

    batches = []
    current = []
    current_tokens = 0

    for block in blocks:
        block_tokens = estimate_tokens(json.dumps(block, ensure_ascii=False))

        if not current:
            if block_tokens > budget:
                logger.warning(
                    "Kịch bản '%s' (id=%s) ước lượng ~%d token, vượt budget %d token/batch — vẫn gửi "
                    "riêng 1 mình (min_scenarios_per_batch), có rủi ro model trả lỗi context length.",
                    block.get("scenario"), block.get("id"), block_tokens, budget,
                )
            current = [block]
            current_tokens = block_tokens
            continue

        would_be_tokens = current_tokens + block_tokens
        would_be_count = len(current) + 1
        fits_budget = would_be_tokens <= budget
        fits_count = would_be_count <= max_scenarios_per_batch
        below_min = len(current) < min_scenarios_per_batch

        if (fits_budget and fits_count) or below_min:
            current.append(block)
            current_tokens = would_be_tokens
        else:
            batches.append(current)
            current = [block]
            current_tokens = block_tokens

    if current:
        batches.append(current)

    logger.info(
        "QC pack_batches: %d kịch bản -> %d batch (context_window=%d, budget=%d token/batch, "
        "min=%d, max=%d/batch)",
        len(blocks), len(batches), context_window, budget, min_scenarios_per_batch, max_scenarios_per_batch,
    )
    return batches


def _call_batch(llm, batch, product_info, cache):
    user = json.dumps({"content_blocks": batch, "product_info": product_info}, ensure_ascii=False)
    key = cache_mod.make_key("verify", VERIFY_PROMPT_VERSION, llm.provider, llm.model, VERIFY_SYSTEM, user)
    raw = cache.get(key)
    cached = raw is not None
    if raw is None:
        raw = llm.complete_json(VERIFY_SYSTEM, user)
        cache.set(key, raw)

    scenario_ids = [b["id"] for b in batch]
    logger.info(
        "QC verify batch %s (%d blocks, cached=%s) raw response: %s",
        scenario_ids, len(batch), cached, raw,
    )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("QC verify batch %s: failed to parse JSON response (%s). Raw response: %s", scenario_ids, e, raw)
        return [], cached, raw

    mismatches = data.get("mismatches", [])
    logger.info("QC verify batch %s: %d mismatches found", scenario_ids, len(mismatches))
    return mismatches, cached, raw


def verify_blocks(
    llm,
    blocks,
    product_info,
    batch_size=None,
    cache=None,
    *,
    context_window=None,
    reserved_output_tokens=None,
    min_scenarios_per_batch=None,
    max_scenarios_per_batch=None,
):
    cache = cache or cache_mod.get_cache()
    batches = pack_batches(
        blocks,
        product_info,
        VERIFY_SYSTEM,
        context_window=context_window,
        reserved_output_tokens=reserved_output_tokens,
        min_scenarios_per_batch=min_scenarios_per_batch,
        max_scenarios_per_batch=max_scenarios_per_batch or batch_size,
    )

    all_mismatches = []
    for batch in batches:
        mismatches, _cached, _raw = _call_batch(llm, batch, product_info, cache)
        all_mismatches.extend(mismatches)
    return {"mismatches": all_mismatches}


def annotate_mismatches(report, content_blocks, sheet_name):
    blocks_by_range = {(b["sheet"], b["row_range"][0], b["row_range"][1]): b for b in content_blocks}
    for m in report.get("mismatches", []):
        row_range = m.get("row_range")
        key = (sheet_name, row_range[0], row_range[1]) if isinstance(row_range, list) and len(row_range) == 2 else None
        matched = blocks_by_range.get(key) if key else None
        m["sheet"] = sheet_name
        if matched:
            m["id"] = matched["id"]
            m["scenario"] = matched["scenario"]
            m["row_range"] = matched["row_range"]
    return report
