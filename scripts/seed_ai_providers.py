"""Seed ai_providers + ai_packages.

Keys are NOT seeded here — admin adds them via /admin/keys after seeding.
Run once after migrations:
    docker compose exec api python -m scripts.seed_ai_providers
"""

import asyncio

from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.pi_ai_cloud.models import AiPackage, AiProvider

# ─── 25 Providers — metadata only. API keys live in ai_provider_keys pool. ────
# Ordered by priority (lower = preferred). Free tier first, paid fallback last.
# All use openai_compat adapter unless noted.
PROVIDERS = [
    # ========== FREE — TOP PRIORITY ==========
    {
        "slug": "groq-llama-70b-free",
        "display_name": "Groq — Llama 3.3 70B (Free)",
        "base_url": "https://api.groq.com/openai/v1",
        "model_id": "llama-3.3-70b-versatile",
        "tier": "free", "priority": 10,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
        "max_rpm": 30, "max_tpd": 14_000_000,  # ~14M tokens/day/key
    },
    {
        "slug": "cerebras-llama-free",
        "display_name": "Cerebras — Llama 3.3 70B (Free)",
        "base_url": "https://api.cerebras.ai/v1",
        "model_id": "llama-3.3-70b",
        "tier": "free", "priority": 15,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.3,
        "max_rpm": 30, "max_tpd": 1_000_000,
    },
    {
        "slug": "gemini-2-flash-free",
        "display_name": "Google Gemini 2.0 Flash (Free)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model_id": "gemini-2.0-flash-exp",
        "tier": "free", "priority": 20,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
        "max_rpm": 15, "max_tpd": 3_000_000,
    },
    {
        "slug": "gemini-25-flash-free",
        "display_name": "Google Gemini 2.5 Flash (Free)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model_id": "gemini-2.5-flash",
        "tier": "free", "priority": 25,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
    },
    {
        "slug": "mistral-small-free",
        "display_name": "Mistral Small (Free)",
        "base_url": "https://api.mistral.ai/v1",
        "model_id": "mistral-small-latest",
        "tier": "free", "priority": 30,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
        "max_rpm": 60, "max_tpd": 30_000_000,
    },
    {
        "slug": "cohere-command-free",
        "display_name": "Cohere Command R (Free)",
        "base_url": "https://api.cohere.ai/compatibility/v1",
        "model_id": "command-r",
        "tier": "free", "priority": 35,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
        "max_rpm": 20,
    },
    {
        "slug": "openrouter-free",
        "display_name": "OpenRouter — Llama 3.3 70B (Free)",
        "base_url": "https://openrouter.ai/api/v1",
        "model_id": "meta-llama/llama-3.3-70b-instruct:free",
        "tier": "free", "priority": 40,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
        "max_rpm": 20,
    },
    {
        "slug": "siliconflow-qwen-free",
        "display_name": "SiliconFlow — Qwen 2.5 7B (Free)",
        "base_url": "https://api.siliconflow.cn/v1",
        "model_id": "Qwen/Qwen2.5-7B-Instruct",
        "tier": "free", "priority": 45,
        "pi_tokens_per_input": 0.8, "pi_tokens_per_output": 1.2,
        "max_rpm": 1000,
    },
    {
        "slug": "github-models-free",
        "display_name": "GitHub Models — Llama 3.1 70B (Free)",
        "base_url": "https://models.inference.ai.azure.com",
        "model_id": "Meta-Llama-3.1-70B-Instruct",
        "tier": "free", "priority": 50,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
        "max_rpm": 15,
    },
    {
        "slug": "cloudflare-llama-free",
        "display_name": "Cloudflare Workers AI (Free)",
        "base_url": "https://api.cloudflare.com/client/v4/accounts/REPLACE_ACCOUNT_ID/ai/v1",
        "model_id": "@cf/meta/llama-3.1-8b-instruct",
        "tier": "free", "priority": 55,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.2,
    },
    {
        "slug": "nvidia-nim-free",
        "display_name": "NVIDIA NIM — Llama 3.1 (Free)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model_id": "meta/llama-3.1-8b-instruct",
        "tier": "free", "priority": 60,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.3,
        "max_rpm": 40,
    },
    {
        "slug": "zhipu-glm-flash-free",
        "display_name": "Zhipu GLM-4.5 Flash (Free)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model_id": "glm-4.5-flash",
        "tier": "free", "priority": 65,
        "pi_tokens_per_input": 0.8, "pi_tokens_per_output": 1.2,
    },
    {
        "slug": "moonshot-kimi-free",
        "display_name": "Moonshot Kimi (Free credit)",
        "base_url": "https://api.moonshot.cn/v1",
        "model_id": "moonshot-v1-8k",
        "tier": "free", "priority": 70,
        "pi_tokens_per_input": 0.8, "pi_tokens_per_output": 1.2,
    },
    {
        "slug": "pollinations-free",
        "display_name": "Pollinations.ai (No key)",
        "base_url": "https://gen.pollinations.ai/v1",
        "model_id": "openai",
        "tier": "free", "priority": 75,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
    },
    {
        "slug": "llm7-free",
        "display_name": "LLM7.io — Multi-model (Free)",
        "base_url": "https://api.llm7.io/v1",
        "model_id": "gpt-4o-mini",
        "tier": "free", "priority": 80,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.5,
    },
    # ========== FREE — TRIAL CREDIT (needs signup) ==========
    {
        "slug": "deepseek-chat-trial",
        "display_name": "DeepSeek Chat (5M trial)",
        "base_url": "https://api.deepseek.com/v1",
        "model_id": "deepseek-chat",
        "tier": "free", "priority": 85,
        "pi_tokens_per_input": 0.5, "pi_tokens_per_output": 0.8,  # very cheap upstream
    },
    {
        "slug": "together-llama-free",
        "display_name": "Together AI — Llama 3.1 (Trial)",
        "base_url": "https://api.together.xyz/v1",
        "model_id": "meta-llama/Llama-3.1-8B-Instruct-Turbo",
        "tier": "free", "priority": 90,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.2,
    },
    {
        "slug": "fireworks-llama-free",
        "display_name": "Fireworks AI — Llama (Trial)",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "model_id": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "tier": "free", "priority": 95,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.3,
    },
    {
        "slug": "sambanova-llama-free",
        "display_name": "SambaNova — Llama 3.1 (Trial)",
        "base_url": "https://api.sambanova.ai/v1",
        "model_id": "Meta-Llama-3.1-8B-Instruct",
        "tier": "free", "priority": 100,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.3,
    },
    {
        "slug": "hyperbolic-llama-trial",
        "display_name": "Hyperbolic — DeepSeek V3 (Trial)",
        "base_url": "https://api.hyperbolic.xyz/v1",
        "model_id": "deepseek-ai/DeepSeek-V3",
        "tier": "free", "priority": 105,
        "pi_tokens_per_input": 0.6, "pi_tokens_per_output": 1.0,
    },
    {
        "slug": "qwen-turbo-trial",
        "display_name": "Alibaba Qwen Turbo (Trial)",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "model_id": "qwen-turbo",
        "tier": "free", "priority": 110,
        "pi_tokens_per_input": 0.8, "pi_tokens_per_output": 1.2,
    },
    {
        "slug": "nebius-llama-trial",
        "display_name": "Nebius — Llama (Trial)",
        "base_url": "https://api.studio.nebius.ai/v1",
        "model_id": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "tier": "free", "priority": 115,
        "pi_tokens_per_input": 1.0, "pi_tokens_per_output": 1.3,
    },
    # ========== PAID PREMIUM (quality=best fallback) ==========
    {
        "slug": "openai-gpt4o-paid",
        "display_name": "OpenAI GPT-4o (Paid)",
        "base_url": "https://api.openai.com/v1",
        "model_id": "gpt-4o",
        "tier": "paid", "priority": 200,
        "input_cost_per_mtok_cents": 500,
        "output_cost_per_mtok_cents": 1500,
        "pi_tokens_per_input": 5.0, "pi_tokens_per_output": 5.0,
        "is_enabled": False,  # enable only when keys are deposited
    },
    {
        "slug": "anthropic-sonnet-paid",
        "display_name": "Claude Sonnet 4.5 (Paid)",
        "base_url": "https://api.anthropic.com/v1",
        "model_id": "claude-sonnet-4-5-20250929",
        "tier": "paid", "priority": 210,
        "input_cost_per_mtok_cents": 300,
        "output_cost_per_mtok_cents": 1500,
        "pi_tokens_per_input": 3.0, "pi_tokens_per_output": 5.0,
        "is_enabled": False,
    },
    {
        "slug": "grok-4-paid",
        "display_name": "xAI Grok 4 (Paid)",
        "base_url": "https://api.x.ai/v1",
        "model_id": "grok-4",
        "tier": "paid", "priority": 220,
        "input_cost_per_mtok_cents": 300,
        "output_cost_per_mtok_cents": 1500,
        "pi_tokens_per_input": 3.0, "pi_tokens_per_output": 5.0,
        "is_enabled": False,
    },
]

# Default adapter is openai_compat
for p in PROVIDERS:
    p.setdefault("adapter", "openai_compat")
    p.setdefault("is_enabled", True)
    p.setdefault("input_cost_per_mtok_cents", 0)
    p.setdefault("output_cost_per_mtok_cents", 0)
    p.setdefault("health_status", "healthy")


# ─── 5 Packages (customer-facing subscription tiers) ─────────
PACKAGES = [
    {
        "slug": "free",
        "display_name": "Free",
        "description": "Dùng thử — đủ test tính năng 14 ngày.",
        "price_cents_monthly": 0,
        "price_cents_yearly": 0,
        "token_quota_monthly": 20_000,
        "allowed_qualities": ["fast"],
        "features": [
            "20K Pi tokens/tháng",
            "Chỉ dùng free model (Groq / Gemini)",
            "Support cộng đồng",
        ],
        "sort_order": 10,
    },
    {
        "slug": "starter",
        "display_name": "Starter",
        "description": "Website cá nhân hoặc blog 1 site.",
        "price_cents_monthly": 900,    # $9/mo
        "price_cents_yearly": 9000,    # $90/yr = 2 months free
        "token_quota_monthly": 200_000,
        "allowed_qualities": ["fast", "balanced"],
        "features": [
            "200K Pi tokens/tháng",
            "Mix free + balanced models",
            "Email support (24h)",
            "pi-seo + pi-chatbot",
        ],
        "sort_order": 20,
    },
    {
        "slug": "pro",
        "display_name": "Pro",
        "description": "Agency nhỏ, 3-5 websites.",
        "price_cents_monthly": 2900,   # $29/mo
        "price_cents_yearly": 29000,
        "token_quota_monthly": 2_000_000,
        "allowed_qualities": ["fast", "balanced"],
        "features": [
            "2M Pi tokens/tháng",
            "Quality balanced (mix providers)",
            "Priority support (8h)",
            "Tất cả 7 plugin Pro",
            "API keys cấp riêng theo license",
        ],
        "sort_order": 30,
    },
    {
        "slug": "agency",
        "display_name": "Agency",
        "description": "Agency lớn, 20+ websites.",
        "price_cents_monthly": 9900,   # $99/mo
        "price_cents_yearly": 99000,
        "token_quota_monthly": 10_000_000,
        "allowed_qualities": ["fast", "balanced", "best"],
        "features": [
            "10M Pi tokens/tháng",
            "Truy cập Claude / GPT-4o (quality=best)",
            "White-label plugin branding",
            "Dedicated Slack channel",
            "Giảm 40% khi trả theo năm",
        ],
        "sort_order": 40,
    },
    {
        "slug": "enterprise",
        "display_name": "Enterprise",
        "description": "SaaS doanh nghiệp, SLA, volume custom.",
        "price_cents_monthly": 0,  # contact sales
        "price_cents_yearly": 0,
        "token_quota_monthly": 100_000_000,
        "allowed_qualities": ["fast", "balanced", "best"],
        "features": [
            "100M+ Pi tokens/tháng",
            "SLA 99.9% + dedicated infra",
            "On-premise deployment option",
            "Custom AI provider integrations",
            "Kỹ sư Pi support riêng",
        ],
        "sort_order": 50,
    },
]


async def seed_providers(db) -> tuple[int, int]:
    added, updated = 0, 0
    for cfg in PROVIDERS:
        slug = cfg["slug"]
        existing = (await db.execute(select(AiProvider).where(AiProvider.slug == slug))).scalar_one_or_none()
        if existing is None:
            db.add(AiProvider(**cfg))
            added += 1
            print(f"  + {slug}")
        else:
            for k, v in cfg.items():
                setattr(existing, k, v)
            updated += 1
            print(f"  ↻ {slug}")
    return added, updated


async def seed_packages(db) -> tuple[int, int]:
    added, updated = 0, 0
    for cfg in PACKAGES:
        slug = cfg["slug"]
        existing = await db.get(AiPackage, slug)
        if existing is None:
            db.add(AiPackage(**cfg))
            added += 1
            print(f"  + package/{slug}")
        else:
            for k, v in cfg.items():
                setattr(existing, k, v)
            updated += 1
            print(f"  ↻ package/{slug}")
    return added, updated


async def main() -> None:
    async with AsyncSessionLocal() as db:
        print("── Providers ──")
        pa, pu = await seed_providers(db)
        print("── Packages ──")
        ka, ku = await seed_packages(db)
        await db.commit()
        print(f"\nDone. Providers: {pa} added, {pu} updated. Packages: {ka} added, {ku} updated.")
        print("\nNext: go to /admin/keys to deposit API keys into the pool.")


if __name__ == "__main__":
    asyncio.run(main())
