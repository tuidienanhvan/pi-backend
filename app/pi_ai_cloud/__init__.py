"""Pi AI Cloud — the ONLY paid component of Pi's AI stack.

──────────────────────────────────────────────────────────────
How the money works:
──────────────────────────────────────────────────────────────

  [FREE, internal tool]                [PAID product]
  Pi AI Provider plugin          ──►   Pi AI Cloud (this module)
  (25 free providers)                   sells TOKENS to end users
  - Gemini free tier                    - $10 = 100k tokens
  - Cohere, Mistral, Groq               - Stripe checkout
  - Together, DeepInfra, etc.           - Wallet + ledger
                                        - Deduct per AI call

──────────────────────────────────────────────────────────────

  Pi does NOT sell access to the providers themselves.
  Pi sells TOKENS — an abstract credit unit.

  Customer sees:    "Buy 100k Pi tokens for $10"
  Customer calls:   POST /v1/ai/complete  (deducts tokens from wallet)
  Pi internally:    picks cheapest healthy provider → usually $0 cost
  Pi margin:        ~90% (free tier providers) to 50% (paid fallback)

──────────────────────────────────────────────────────────────

This is the PRIMARY profit engine of the Pi ecosystem.
All other Pi Pro plugins (SEO Bot, Chatbot, Leads AI scoring) consume
tokens from the same wallet — single currency, single top-up, single
billing experience.

See docs/PI_AI_CLOUD.md for pricing strategy + routing algorithm.
"""
