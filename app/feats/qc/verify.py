import json
from app.feats.qc import cache
from app.feats.qc.prompts import VERIFY_SYSTEM

VERIFY_PROMPT_VERSION = "v1"


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
        if raw is None:
            raw = llm.complete_json(VERIFY_SYSTEM, user)
            cache.set(key, raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        all_mismatches.extend(data.get("mismatches", []))
    return {"mismatches": all_mismatches}