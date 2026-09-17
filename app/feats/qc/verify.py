import json
import logging
from app.feats.qc import cache
from app.feats.qc.prompts import VERIFY_SYSTEM

logger = logging.getLogger("qc.verify")

VERIFY_PROMPT_VERSION = "v2"


def verify_blocks(llm, blocks, product_info, batch_size=20):
    all_mismatches = []
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        user = json.dumps(
            {"content_blocks": batch, "product_info": product_info},
            ensure_ascii=False,
        )

        key = cache.make_key(
            "verify", VERIFY_PROMPT_VERSION, llm.provider, llm.model, VERIFY_SYSTEM, user
        )
        raw = cache.get(key)
        cached = raw is not None
        if raw is None:
            raw = llm.complete_json(VERIFY_SYSTEM, user)
            cache.set(key, raw)

        logger.info(
            "QC verify batch %d-%d (%d blocks, cached=%s) raw response: %s",
            i, i + len(batch), len(batch), cached, raw
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(
                "QC verify batch %d-%d: failed to parse JSON response (%s). Raw response: %s",
                i, i + len(batch), e, raw
            )
            continue

        mismatches = data.get("mismatches", [])
        logger.info("QC verify batch %d-%d: %d mismatches found", i, i + len(batch), len(mismatches))
        all_mismatches.extend(mismatches)
    return {"mismatches": all_mismatches}