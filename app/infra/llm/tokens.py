
import math
import re

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

_SAFETY_FACTOR = 1.15

_CHARS_PER_TOKEN = 3.3

_TOKENS_PER_WORD = 1.3


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    chars = len(text)
    words = len(_TOKEN_RE.findall(text))
    raw = max(chars / _CHARS_PER_TOKEN, words * _TOKENS_PER_WORD)
    return math.ceil(raw * _SAFETY_FACTOR)
