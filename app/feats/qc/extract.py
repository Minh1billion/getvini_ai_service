import json
from app.feats.qc import cache
from app.feats.qc.prompts import EXTRACT_SYSTEM
from app.feats.qc.sheet_reader import rows_to_text

EXTRACT_PROMPT_VERSION = "v1"


def extract_blocks(llm, rows):
    text = rows_to_text(rows)
    user = f"Nội dung sheet:\n{text}"

    key = cache.make_key(
        "extract", EXTRACT_PROMPT_VERSION, llm.provider, llm.model, EXTRACT_SYSTEM, user
    )
    raw = cache.get(key)
    if raw is None:
        raw = llm.complete_json(EXTRACT_SYSTEM, user)
        cache.set(key, raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {"blocks": data.get("blocks", [])}