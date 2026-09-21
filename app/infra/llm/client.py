import logging
import re
import time

from openai import BadRequestError, OpenAI, RateLimitError

from app.core.config import get_settings

logger = logging.getLogger("qc.llm")


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
    def __init__(self, provider=None, model=None, api_key=None):
        settings = get_settings()
        self.provider = provider or settings.qc_default_provider
        if self.provider == "groq":
            key = api_key or settings.groq_api_key
            self.client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
            self.model = model or settings.qc_model_groq
        elif self.provider == "openai":
            key = api_key or settings.openai_api_key
            self.client = OpenAI(api_key=key)
            self.model = model or settings.qc_model_openai
        elif self.provider == "openrouter":
            key = api_key or settings.openrouter_api_key
            self.client = OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://getvini.com",
                    "X-Title": "Getvini QC",
                },
            )
            self.model = model or settings.qc_model_openrouter
        else:
            raise ValueError(f"unknown provider: {self.provider}")

    def complete_json(self, system, user):
        settings = get_settings()
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
                    seed=settings.qc_llm_seed,
                    **kwargs,
                )
                content = resp.choices[0].message.content
                logger.info("QC LLM response (provider=%s, model=%s): %s", self.provider, self.model, content)
                return content
            except RateLimitError as e:
                rate_limit_attempt += 1
                wait_s = _parse_retry_seconds(str(e))
                if rate_limit_attempt > settings.qc_llm_max_retries or wait_s is None or wait_s > settings.qc_llm_max_wait_seconds:
                    logger.error("QC LLM rate limit exceeded: %s", e)
                    raise
                logger.warning("QC LLM rate limited, retrying in %.1fs: %s", wait_s, e)
                time.sleep(wait_s)
            except BadRequestError as e:
                if getattr(e, "code", None) != "json_validate_failed":
                    logger.error("QC LLM request failed: %s", e)
                    raise
                json_attempt += 1
                if json_attempt > settings.qc_llm_json_retries:
                    logger.error("QC LLM failed to produce valid JSON after %d attempts: %s", json_attempt, e)
                    raise
                logger.warning("QC LLM returned invalid JSON, retrying (attempt %d): %s", json_attempt, e)
                time.sleep(1)
