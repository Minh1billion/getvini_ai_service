import os
from openai import OpenAI

QC_LLM_SEED = int(os.environ.get("QC_LLM_SEED", "7"))


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
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            seed=QC_LLM_SEED,
        )
        return resp.choices[0].message.content