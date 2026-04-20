"""OpenAI-compatible adapter — covers most free providers.

Works with: Groq, Together, DeepInfra, Mistral, Fireworks, Lepton, Cohere-compat,
Gemini-OpenAI-compatibility-endpoint, HuggingFace TGI, LocalAI, Ollama, etc.
"""

import httpx

from app.pi_ai_cloud.providers.base import CompletionResult, ProviderAdapter


class OpenAICompatAdapter(ProviderAdapter):
    slug = "openai_compat"
    adapter_type = "openai_compat"

    async def complete(
        self,
        *,
        messages: list[dict],
        model_id: str,
        max_tokens: int,
        temperature: float,
        api_key: str,
        base_url: str,
    ) -> CompletionResult:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )

        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("No choices in response")

        text = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})

        return CompletionResult(
            text=str(text).strip(),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            upstream_cost_cents=0,  # filled in by router based on provider pricing
        )
