import json
from app.feats.qc import cache
from app.feats.qc.prompts import EXTRACT_SYSTEM
from app.feats.qc.sheet_reader import rows_to_text

EXTRACT_PROMPT_VERSION = "v1"
MAX_CHUNK_CHARS = 40000


def _chunk_rows(rows, max_chars=MAX_CHUNK_CHARS):
    chunks = []
    current = []
    current_len = 0
    for row in rows:
        idx, vals = row
        line_len = len(str(idx)) + sum(len(str(v)) for v in vals if v is not None) + len(vals) + 8
        if current and current_len + line_len > max_chars:
            chunks.append(current)
            current = []
            current_len = 0
        current.append(row)
        current_len += line_len
    if current:
        chunks.append(current)
    return chunks or [[]]


def extract_blocks(llm, rows):
    all_blocks = []
    for chunk in _chunk_rows(rows):
        text = rows_to_text(chunk)
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
        all_blocks.extend(data.get("blocks", []))
    return {"blocks": all_blocks}