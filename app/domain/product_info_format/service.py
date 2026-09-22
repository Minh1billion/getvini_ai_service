import json

from app.infra.llm.client import LLMClient
from app.infra.llm.prompts import PRODUCT_INFO_FORMAT_SYSTEM

ALLOWED_BLOCK_TYPES = {"paragraph", "bullet_list", "numbered_list"}


def _escape(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def blocks_to_html(blocks):
    parts = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type not in ALLOWED_BLOCK_TYPES:
            continue
        if block_type == "paragraph":
            text = (block.get("text") or "").strip()
            if text:
                parts.append(f"<p>{_escape(text)}</p>")
        else:
            raw_items = block.get("items") or []
            items = [item.strip() for item in raw_items if isinstance(item, str) and item.strip()]
            if not items:
                continue
            tag = "ul" if block_type == "bullet_list" else "ol"
            lis = "".join(f"<li>{_escape(item)}</li>" for item in items)
            parts.append(f"<{tag}>{lis}</{tag}>")
    return "".join(parts)


def format_product_info(text, product_name=None, provider=None, model=None):
    llm = LLMClient(provider=provider, model=model)
    user_payload = {
        "product_name": product_name or "",
        "raw_text": text or "",
    }
    raw = llm.complete_json(PRODUCT_INFO_FORMAT_SYSTEM, json.dumps(user_payload, ensure_ascii=False))
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        blocks = parsed
    elif isinstance(parsed, dict):
        blocks = parsed.get("blocks")
        if not isinstance(blocks, list):
            blocks = []
    else:
        blocks = []
    return blocks_to_html(blocks)
