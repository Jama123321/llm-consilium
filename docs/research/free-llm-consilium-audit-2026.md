# Free Cloud LLM Providers for a Multi-Model Consilium — 2026 Audit

> Decision-grade audit for a solo dev who wants to (a) assemble ALL free cloud models into a test project, (b) wire them into Claude Code, (c) build a fan-out→aggregate "consilium".
> Research date: 2026-07-13. Confidence flags inline. Primary sources = provider docs/ToS; secondary = aggregator blogs (limits shift; treat exact numbers as "verify in console").

**STATUS: COMPLETE.**

---

## 1. Per-Provider Comparison Table

Legend: **OAI** = OpenAI-SDK drop-in via `base_url`. **Card** = credit card required to start. **Trains?** = free-tier prompts used for model training/improvement (privacy-decisive).

| Provider | Free models (ids) | Free limits | OAI base_url | Card? | Trains on prompts? | Commercial use? | Signup |
|---|---|---|---|---|---|---|---|
| **Google AI Studio (Gemini)** | `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.0-flash` | Flash: 15 RPM / 1500 RPD / 1M TPM. Flash-Lite: 30 RPM. Pro: 5 RPM / ~50–100 RPD | `https://generativelanguage.googleapis.com/v1beta/openai/` | **No** | **YES** (free tier used to improve products; paid tier = not trained) | Yes | aistudio.google.com |
| **Groq Cloud** | `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `llama-4-scout/maverick`, `gemma2-9b-it`, `qwen-qwq-32b`, `kimi-k2`, `deepseek-r1-distill` | ~30 RPM / 1K RPD per model, 6K–15K TPM, org-wide 14.4K RPD | `https://api.groq.com/openai/v1` | **No** (card optional → 10x limits) | **No** (does not train; see verify) | Yes | console.groq.com |
| **Mistral La Plateforme** | `mistral-large-latest`, `mistral-small-latest`, `codestral-latest`, `ministral-8b`, `pixtral-12b`, `mistral-embed` | Free "Experiment": ~1 req/s (1–2 RPM), ~1B tokens/month | `https://api.mistral.ai/v1` | **No** | **YES by default** — must opt out in Admin Console → Privacy | Yes (Apache-2.0 weights self-hostable too) | console.mistral.ai |
| **GitHub Models** | `gpt-4o`, `gpt-4.1`, `o3`, `DeepSeek-R1`, `Phi-4`, `Llama-3.3-70B`, `Mistral-Large`, `Grok-3` | ~10–15 RPM / 50–150 RPD by tier; 8K input cap | `https://models.github.ai/inference` (Azure) | **No** (GitHub acct) | No (Azure/GitHub terms; not for training) | Testing/eval — prod use needs paid Azure | github.com/marketplace/models |
| **OpenRouter (:free)** | 28+ `*:free` — `deepseek-r1:free`, `llama-3.3-70b-instruct:free`, `gpt-oss-120b:free`, `qwen3-coder:free`, `gemini-2.0-flash-exp:free` | 20 RPM; 50 RPD (<$10 credit ever) → 1000 RPD ($10+ once) | `https://openrouter.ai/api/v1` | **No** | OpenRouter itself no-train; **:free routes may allow upstream provider training** (opt via privacy settings) | Depends on upstream | openrouter.ai |
| **Cohere** | `command-a`, `command-r-plus`, `command-r`, `aya-expanse-32b/8b` | Trial key: 20 RPM / 1000 calls/month | native (`https://api.cohere.com`); OAI-compat partial | **No** | **YES** — trial/free data may be used to improve; paid = not | Trial key = **non-commercial** | dashboard.cohere.com |
| **Cerebras Cloud** | `llama-3.3-70b`, `llama-4-scout`, `qwen-3-235b`, `gpt-oss-120b` | **1M tokens/day**; ~5–30 RPM; 30K TPM; 8K ctx cap on free | `https://api.cerebras.ai/v1` | **No** | **No** (ToS: no train/fine-tune on Service Content; no retention) | Yes | cloud.cerebras.ai |
| **NVIDIA NIM (build.nvidia.com)** | `meta/llama-3.3-70b`, `deepseek-r1`, `qwen3-235b`, `nemotron` (~115 models) | 1,000 credits (→5,000 on request); ~40 RPM | `https://integrate.api.nvidia.com/v1` | **No** (NVIDIA Dev acct) | No (dev/eval terms) | Eval/dev/prototyping | build.nvidia.com |
| **Hugging Face Inference Providers** | many via router (Llama-3.3-70B, Qwen2.5-72B, Mistral, etc.) | ~$0.10/mo free credit (tiny) | `https://router.huggingface.co/v1` | **No** | No (varies by upstream provider) | Depends on model license | huggingface.co |
| **Cloudflare Workers AI** | `@cf/meta/llama-3.3-70b`, `@cf/qwen/qwq-32b`, gemma, phi (~47 models) | **10,000 neurons/day** (≈10k output tok) reset 00:00 UTC | `/v1/chat/completions` OAI-compat endpoint | **No** (CF acct) | **No** (explicit: won't train on your Customer Content) | Yes | dash.cloudflare.com |
| **SambaNova Cloud** | `Meta-Llama-3.3-70B`, `Llama-4-Maverick`, `Qwen3-235B`, `DeepSeek-R1`, `405B` | Free persists: **20 RPM / 20 RPD / 200K TPD per model** (10 RPM for 405B); +$5 credits (30d) | `https://api.sambanova.ai/v1` | **No** | verify (dev-tier; no explicit train claim found) | Yes | cloud.sambanova.ai |
| **Zhipu / GLM (Z.ai / BigModel)** | `glm-4.7-flash`, `glm-4.5-flash`, `glm-4.6v-flash` (vision) | free Flash models; ~1 concurrent; 128K in / 8K out | `https://open.bigmodel.cn/api/paas/v4/` | **No** | **ASSUME YES** (CN jurisdiction; no clear opt-out) | verify | open.bigmodel.cn / z.ai |

**Providers with ONLY expiring trial credits (NOT a permanent free tier) — usable briefly, then paid:**

| Provider | What you get | Base URL (OAI) | Card? | Note |
|---|---|---|---|---|
| **DeepSeek** | One-time 5M-token grant (~30d), new sign-ups | `https://api.deepseek.com` (also `/anthropic`) | **No** | No permanent free model. Cheap paid after. CN jurisdiction → treat prompts as non-private. |
| **Fireworks AI** | $1 starter credit (~1M tok on 70B); free API @ 10 RPM w/o card | `https://api.fireworks.ai/inference/v1` | **No** | No permanent free *model* tier; small credit on top of PAYG. |
| **SambaNova** | (also has the persistent free tier above) $5 credits expiring 30d | — | — | The 20 RPM free tier is the durable part. |

---

## 2. Excluded — NO permanent free API path (2026)

- **xAI Grok** — the $150/mo data-sharing free-credit program **ended (May 2025)**. Only expiring new-account trial credits ($25–$150, 30–90d). No permanent free API tier. *EXCLUDE from a durable consilium.*
- **Together AI** — **no free tier**, no free trial credits anymore; minimum $5 credit purchase to start. *EXCLUDE.*
- **OpenAI / Anthropic** — no free API tier (Anthropic API is what the user already pays for as the primary; OpenAI API has no free tier). *EXCLUDE (paid only).*
- **Ollama Cloud / Turbo** — free tier exists but is **GPU-time / session-quota based** (resets every 5h + weekly), 1 concurrent model, designed for the Ollama client, not a clean OpenAI-compatible always-on API for orchestration. *EXCLUDE for consilium reliability* (usable as a bonus if you already run Ollama; treat as flaky).
- **DeepSeek / Fireworks** — trial credits only, not permanent free (listed above; use during trial then drop).
- **Pollinations / AnyAPI / UnoRouter** — community/aggregator gateways with undocumented or per-IP caps and unclear data/ToS terms. *EXCLUDE from a decision-grade privacy-sensitive setup* (fine for throwaway experiments only; confidence LOW on their durability).

---

## 3. Integration Architecture

### Recommendation: **self-hosted LiteLLM proxy** as the single OpenAI-compatible router.

Why LiteLLM over "OpenRouter as the one router" or "direct per-provider calls":

- **OpenRouter-hosted** only fronts models *it* resells; you cannot add your own Groq/Gemini/Cerebras keys and keep their native (higher) free limits — you'd be capped by OpenRouter's 20 RPM / 200–1000 RPD across the pooled `:free` set, and privacy depends on the upstream route. Good as *one member*, not as *the* router.
- **Direct per-provider calls** = N different auth schemes, N retry/rate-limit handlers, N SDKs. Painful for a fan-out orchestrator.
- **Self-hosted LiteLLM** ([docs.litellm.ai](https://docs.litellm.ai/docs/simple_proxy)) exposes **one `/v1` OpenAI endpoint** in front of 100+ providers, keeps each provider's *native* free limits, handles per-key rate limits, load-balancing, and failover. There is even a ready template: **[tomaasz/litellm-free-models-proxy](https://github.com/tomaasz/litellm-free-models-proxy)** that auto-discovers free/trial models from OpenRouter, Groq, Gemini, Cerebras, SambaNova, Cohere, NVIDIA NIM. Confidence: HIGH this is the least-effort path.

### Minimal per-provider config shape (what the orchestrator reads)

Every provider reduces to the same three fields. LiteLLM `config.yaml`:

```yaml
model_list:
  - model_name: council/gemini-flash            # alias the orchestrator calls
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
      # base_url implicit for known providers; explicit for OAI-compat ones:
  - model_name: council/groq-llama-70b
    litellm_params:
      model: groq/llama-3.3-70b-versatile
      api_key: os.environ/GROQ_API_KEY
  - model_name: council/cerebras-qwen-235b
    litellm_params:
      model: openai/qwen-3-235b                  # OAI-compat shim
      api_base: https://api.cerebras.ai/v1
      api_key: os.environ/CEREBRAS_API_KEY
      rpm: 5                                       # respect free RPM here
  - model_name: council/openrouter-deepseek-r1
    litellm_params:
      model: openrouter/deepseek/deepseek-r1:free
      api_key: os.environ/OPENROUTER_API_KEY
router_settings:
  routing_strategy: usage-based-routing-v2        # respects rpm/tpm you declare
  num_retries: 2
  fallbacks: [{"council/gemini-flash": ["council/groq-llama-70b"]}]
```

The generic shape any orchestrator needs per member: **`{ alias, model_id, base_url, api_key_env, rpm, tpm, privacy_tier }`**. Point Claude Code / your app at `http://localhost:4000/v1` with any key — one drop-in base_url for the whole council.

### Claude Code integration

Claude Code speaks the Anthropic protocol. To route it through the free pool, set the Anthropic-compatible base URL to LiteLLM's Anthropic passthrough (`/anthropic`) or use LiteLLM's `--config` with an Anthropic-format model. Simpler: keep **Claude (paid) as the primary in Claude Code**, and expose the **free consilium as an MCP tool / subagent** that calls `localhost:4000/v1` — the council becomes a "second opinion" tool rather than replacing the driver model. This matches the user's stated goal (interim free compute + council), and keeps sensitive repo context on the paid, no-train Anthropic path.

---

## 4. Consilium (Council) Design — fan-out → aggregate

### Members (pick 4–6; keep them heterogeneous by vendor for diverse errors)

**Strong enough to be voting members (flagship-class, free):**
- **Cerebras** `qwen-3-235b` / `llama-3.3-70b` — huge model, 1M tok/day, no-train. **Top pick.**
- **Groq** `openai/gpt-oss-120b` or `llama-3.3-70b-versatile` — fast, no-train.
- **Google Gemini** `gemini-2.5-pro` (reasoning) or `gemini-2.5-flash` (volume) — strong, but **trains on free tier**.
- **OpenRouter** `deepseek-r1:free` — strong reasoning member.
- **NVIDIA NIM** `deepseek-r1` / `qwen3-235b` — strong, dev-eval terms.
- **SambaNova** `Llama-4-Maverick` / `Qwen3-235B` — strong + fast.
- **Mistral** `mistral-large-latest` — capable, but **trains by default** (opt out).

**Usable but weaker — tie-breakers / cheap redundancy, not lead reasoners:**
- Gemini/Groq/Cerebras *small* variants (`flash-lite`, `gemma2-9b`, `gpt-oss-20b`), Cohere `command-r`, Cloudflare `qwen-qwq-32b`, GLM `glm-4.5-flash`. Good for majority-vote volume, mediocre for hard reasoning/synthesis.

**Too weak / avoid as members:** 7–9B models (Phi, Gemma-7B, Ministral-8B) except as noise-reduction voters on simple classification.

### Fan-out → aggregate pattern

1. **Fan-out (parallel):** send the same prompt to K members concurrently via the LiteLLM alias set. Use `asyncio.gather` with a **per-member semaphore sized to its RPM** (e.g. Cerebras sem=5/min, Gemini-flash=15/min, OpenRouter=20/min, SambaNova=20/min). LiteLLM's `usage-based-routing` + declared `rpm`/`tpm` also throttles, but enforce client-side too so one slow member can't stall the round.
2. **Timeout + quorum:** set a hard per-call timeout (~30s); proceed once you have quorum (e.g. 3 of 5) instead of blocking on the slowest/failed member. Rate-limit (429) or timeout ⇒ that member abstains this round.
3. **Aggregate — pick one:**
   - **Majority vote** — best for closed-form / classification / yes-no / pick-an-option. Cheap, no extra call.
   - **Judge synthesis (recommended default)** — collect the K answers, feed them to **one strong "chair" model** (Cerebras 235B or Gemini-2.5-Pro) with a rubric: "here are K candidate answers; produce the best merged answer, note disagreements." One extra call.
   - **Debate (1 round)** — show each member the others' answers, let them revise, then judge-synthesize. 2× the calls; use only for hard/ambiguous questions — expensive against free RPD caps.
4. **Rate-limit hygiene when fanning out:** stagger start times slightly; cache identical prompts; count RPD per member and rotate members out when a daily cap is near (Gemini-Pro ~50/day, SambaNova 20/day are the tightest — reserve those for the *judge* role, not every fan-out). Back off exponentially on 429.

**Concrete default council:** Cerebras-235B + Groq-gpt-oss-120b + OpenRouter-deepseek-r1 + Gemini-2.5-flash as 4 voters, **Cerebras-235B as chair/judge** → majority-vote for factual, judge-synthesis for open-ended.

---

## 5. Privacy Tiering (the backbone of the usage rule)

### TIER A — SAFE FOR ANY PROMPT (does NOT train on / retain your data)
- **Cerebras** — ToS: won't train/fine-tune on Service Content; no retention, immediate deletion. *(Primary source: Cerebras ToS/privacy.)*
- **Cloudflare Workers AI** — explicit: won't train on your Customer Content; private by default.
- **Groq** — not permitted to train on Inputs/Outputs; not retained by default (7-day operational logs; ZDR available). *Verify: 7-day log ≠ training, still not "zero" unless ZDR on.*
- **GitHub Models** — Azure/GitHub terms; not used for training (eval/testing use).
- **NVIDIA NIM** — dev/eval; no training claim on prompts (LOW confidence on retention — verify ToS).
- **OpenRouter (the router itself)** — does not train on your data; provider-side retention disable-able. *Caveat: the upstream `:free` route may not honor this — see Tier B.*
- **Hugging Face** — HF router doesn't train; depends on the selected upstream provider.

### TIER B — PUBLIC / NON-SENSITIVE PROMPTS ONLY (trains on free-tier data, or unclear)
- **Google Gemini (free tier)** — **free tier is used to improve Google products** (paid/Vertex is not). Do NOT send private repo/client data on the free key.
- **Mistral La Plateforme (free "Experiment")** — **trains by default**; you must opt out in Admin Console → Privacy. Until you opt out, Tier B.
- **Cohere (trial key)** — trial/free data may be used to improve models; also **non-commercial**.
- **Zhipu / GLM, DeepSeek** — CN jurisdiction, no clear opt-out; **assume trained/retained**. Tier B (really "public only").
- **OpenRouter `:free` upstream** — some free routes send data to providers that train; check per-model "training" flag / enable privacy setting. Treat as Tier B unless verified per route.
- **SambaNova free / Ollama Cloud / community gateways** — data terms unclear on free; default to Tier B until confirmed.

---

## 6. Draft Usage Rule (bullets)

- **Default driver stays the paid primary (Claude in Claude Code).** The free consilium is a *second-opinion / brainstorm / cross-check* tool, invoked deliberately — not the everyday coding model. Free models are interim compute, not a Claude replacement.
- **Sensitivity gate before any fan-out:**
  - Prompt contains private repo code, secrets, client/PII, or unpublished IP ⇒ **Tier A providers only** (Cerebras, Cloudflare, Groq-with-ZDR, GitHub Models). Never Gemini-free / Mistral-free / GLM / DeepSeek / Cohere-trial.
  - Prompt is generic / public / a toy question / already-public knowledge ⇒ **any provider**, use the full council for maximum diversity.
- **Never** send `.env`, credentials, or customer data to *any* free tier — even Tier A — as a hard rule; strip secrets first.
- **Role assignment:** put the tightest-RPD strong models (Gemini-2.5-Pro ~50/day, SambaNova 20/day) in the **judge/chair** seat (one call per round), and the generous ones (Cerebras 1M tok/day, Groq, OpenRouter-1000/day) as the **fan-out voters**.
- **Rate-limit hygiene:** client-side semaphore per member = its RPM; hard 30s timeout + quorum (don't wait on stragglers); exponential backoff on 429; per-member RPD counter that rotates a member out near its daily cap; cache identical prompts.
- **Commercial-use guard:** Cohere *trial* key = non-commercial; GitHub Models = eval-not-prod. Keep these out of anything shipped.
- **Route everything through one LiteLLM `/v1`** so adding/removing a provider is a config edit, and privacy tier is a per-alias tag the orchestrator reads before sending.

---

## 7. Sources

### Official / primary
- Gemini API rate limits — https://ai.google.dev/gemini-api/docs/rate-limits (official)
- Gemini OpenAI-compat base URL — https://generativelanguage.googleapis.com/v1beta/openai/ (official endpoint)
- Groq rate limits — https://console.groq.com/docs/rate-limits (official)
- Groq "Your Data in GroqCloud" — https://console.groq.com/docs/your-data (official, privacy)
- Groq Services Agreement — https://console.groq.com/docs/legal/services-agreement (official)
- Mistral usage & tiers — https://docs.mistral.ai/deployment/ai-studio/tier (official)
- Mistral opt-out of training — https://help.mistral.ai/en/articles/455207 (official)
- Mistral privacy — https://docs.mistral.ai/admin/security-access/privacy (official)
- Cerebras rate limits — https://inference-docs.cerebras.ai/support/rate-limits (official)
- Cerebras ToS — https://www.cerebras.ai/terms-of-service ; privacy — https://cloud.cerebras.ai/privacy (official)
- Cloudflare Workers AI pricing (neurons) — https://developers.cloudflare.com/workers-ai/platform/pricing/ (official)
- Cloudflare Workers AI OpenAI-compat — https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/ (official)
- Cloudflare Workers AI data usage — https://developers.cloudflare.com/workers-ai/platform/data-usage/ (official)
- OpenRouter pricing & limits — https://openrouter.ai/pricing ; https://openrouter.ai/docs/api/reference/limits (official)
- NVIDIA NIM free-tier forum clarification — https://forums.developer.nvidia.com/t/clarity-on-nim-api-free-tier-rate-limit-increases/369624 (official forum)
- SambaNova rate limits — https://docs.sambanova.ai/docs/en/models/rate-limits ; developer tier — https://sambanova.ai/blog/sambanova-cloud-developer-tier-is-live (official)
- DeepSeek pricing/base URL — https://api-docs.deepseek.com/quick_start/pricing/ (official)
- xAI API — https://x.ai/news/api (official)
- Ollama pricing — https://ollama.com/pricing (official)
- LiteLLM proxy docs — https://docs.litellm.ai/docs/simple_proxy ; routing — https://docs.litellm.ai/docs/routing (official)
- Zhipu/Z.ai GLM models — https://huggingface.co/zai-org (official model cards); BigModel — https://open.bigmodel.cn/

### Secondary (aggregators / blogs — used for cross-checking numbers, treat as "verify in console")
- awesome-free-llm-apis (curated list) — https://github.com/amardeeplakshkar/awesome-free-llm-apis
- mnfst/awesome-free-llm-apis — https://github.com/mnfst/awesome-free-llm-apis
- litellm-free-models-proxy (ready template) — https://github.com/tomaasz/litellm-free-models-proxy
- OpenRouter "Free LLM API 2026 compared" — https://openrouter.ai/blog/tutorials/free-llm-apis-compared/
- TokenMix blog (Groq/Gemini/Cerebras/DeepSeek free-tier posts) — https://tokenmix.ai/blog/
- pricepertoken.com free-tier pages (Groq/Mistral/Cerebras/Fireworks/DeepSeek/OpenRouter)
- costbench.com free-plan pages (Groq/SambaNova/Cloudflare/NVIDIA/Mistral)
- Cerebras 1M-tok/day analysis — https://www.getaiperks.com/en/ai/cerebras-free-tier-guide
- eesel.ai Together AI / xAI pricing guides
- klymentiev.com free-LLM-API comparison — https://klymentiev.com/blog/free-llm-api
- freellm.net provider pages (NVIDIA NIM, GLM)

### Confidence notes
- Exact RPM/RPD/TPM numbers shift monthly and are org/region/model-dependent — **verify in each provider's live console** before hard-coding. Numbers above are best-effort as of 2026-07.
- **Privacy verdicts** for Cerebras / Cloudflare / Groq / Gemini-free / Mistral-free are drawn from official ToS/privacy pages (HIGH confidence). SambaNova / NVIDIA NIM / Zhipu / DeepSeek free-tier data policies are **not clearly documented** — defaulted to Tier B / "verify" (LOW confidence, conservative).
- xAI free-credit termination, Together "no free tier", DeepSeek/Fireworks "trial-only" confirmed from multiple 2026 secondary sources + official pages (HIGH/MEDIUM confidence).
