import json
from app.feats.qc.prompts import EXTRACT_SYSTEM
from app.feats.qc.sheet_reader import rows_to_text, chunk_rows


def extract_blocks(llm, rows, chunk_size=80):
    all_blocks = []
    for chunk in chunk_rows(rows, chunk_size):
        text = rows_to_text(chunk)
        user = f"Nội dung sheet:\n{text}"
        raw = llm.complete_json(EXTRACT_SYSTEM, user)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        all_blocks.extend(data.get("blocks", []))
    return {"blocks": all_blocks}
