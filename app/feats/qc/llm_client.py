import os
import re
import time
from openai import OpenAI, BadRequestError, RateLimitError

QC_LLM_SEED = int(os.environ.get("QC_LLM_SEED", "7"))
QC_LLM_MAX_RETRIES = int(os.environ.get("QC_LLM_MAX_RETRIES", "3"))
QC_LLM_MAX_WAIT_SECONDS = float(os.environ.get("QC_LLM_MAX_WAIT_SECONDS", "30"))
QC_LLM_JSON_RETRIES = int(os.environ.get("QC_LLM_JSON_RETRIES", "2"))


def _parse_retry_seconds(message):
    match = re.search(r"try again in (?:(\d+(?:\.\d+)?)m)?\s*(\d+(?:\.\d+)?)s", message)
    if not match:
        return None
    minutes = float(match.group(1)) if match.group(1) else 0
    seconds = float(match.group(2))
    return minutes * 60 + seconds


def _is_gpt_oss(model):
    return model.startswith("openai/gpt-oss")


class LLMClient:
    def __init__(self, provider="groq", model=None, api_key=None):
        self.provider = provider
        if provider == "groq":
            key = api_key or os.environ.get("GROQ_API_KEY")
            self.client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
            self.model = model or "openai/gpt-oss-120b"
        elif provider == "openai":
            key = api_key or os.environ.get("OPENAI_API_KEY")
            self.client = OpenAI(api_key=key)
            self.model = model or "gpt-4o-mini"
        else:
            raise ValueError(f"unknown provider: {provider}")

    def complete_json(self, system, user):
        rate_limit_attempt = 0
        json_attempt = 0
        while True:
            kwargs = {}
            if _is_gpt_oss(self.model):
                kwargs["reasoning_effort"] = "low"
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    seed=QC_LLM_SEED,
                    **kwargs,
                )
                return resp.choices[0].message.content
            except RateLimitError as e:
                rate_limit_attempt += 1
                wait_s = _parse_retry_seconds(str(e))
                if rate_limit_attempt > QC_LLM_MAX_RETRIES or wait_s is None or wait_s > QC_LLM_MAX_WAIT_SECONDS:
                    raise
                time.sleep(wait_s)
            except BadRequestError as e:
                if getattr(e, "code", None) != "json_validate_failed":
                    raise
                json_attempt += 1
                if json_attempt > QC_LLM_JSON_RETRIES:
                    raise
                time.sleep(1)