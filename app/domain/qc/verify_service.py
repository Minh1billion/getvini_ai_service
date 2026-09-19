import json
import logging

from app.infra.llm import cache as cache_mod
from app.infra.llm.prompts import VERIFY_SYSTEM

logger = logging.getLogger("qc.verify")

VERIFY_PROMPT_VERSION = "v2"


def verify_blocks(llm, blocks, product_info, batch_size=20, cache=None):
    cache = cache or cache_mod.get_cache()
    all_mismatches = []
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        user = json.dumps({"content_blocks": batch, "product_info": product_info}, ensure_ascii=False)

        key = cache_mod.make_key("verify", VERIFY_PROMPT_VERSION, llm.provider, llm.model, VERIFY_SYSTEM, user)
        raw = cache.get(key)
        cached = raw is not None
        if raw is None:
            raw = llm.complete_json(VERIFY_SYSTEM, user)
            cache.set(key, raw)

        logger.info("QC verify batch %d-%d (%d blocks, cached=%s) raw response: %s", i, i + len(batch), len(batch), cached, raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("QC verify batch %d-%d: failed to parse JSON response (%s). Raw response: %s", i, i + len(batch), e, raw)
            continue

        mismatches = data.get("mismatches", [])
        logger.info("QC verify batch %d-%d: %d mismatches found", i, i + len(batch), len(mismatches))
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
