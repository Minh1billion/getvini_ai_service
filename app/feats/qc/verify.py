import json
from app.feats.qc.prompts import VERIFY_SYSTEM


def verify_blocks(llm, blocks, product_info, batch_size=20):
    all_mismatches = []
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        user = json.dumps(
            {"content_blocks": batch, "product_info": product_info},
            ensure_ascii=False,
        )
        raw = llm.complete_json(VERIFY_SYSTEM, user)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        all_mismatches.extend(data.get("mismatches", []))
    return {"mismatches": all_mismatches}
