# Borrow Map — LLM Consilium (2026-07-14)

> Background-agent research. Actionable reuse plan from deep reads of DUH, ai-council-mcp, PAL/zen, karpathy/llm-council, FreeLLMAPI + provider privacy-tier verification.
> License rule: MIT/Apache = copy with attribution; AGPL / no-license = **reimplement design only**.

## 1. Reusable components / patterns (prioritized)
| Item | Source | License | Fits | Effort | Verdict |
|---|---|---|---|---|---|
| Anonymized synthesis prompt (equal-weight, 3-step critique, code-names only) | ai-council-mcp `synthesis.py` | MIT — copy (NOTICE Akuti) | aggregation | S | **Adopt** |
| Code-name anonymization (`DEFAULT_CODE_NAMES` + `_assign_code_names`) | ai-council-mcp `config.py` | MIT — copy | aggregation debias | S | **Adopt** |
| Fusion judge prompt (rewrite standalone, reason not average, never cite "Response N") | FreeLLMAPI `fusion.ts` | MIT — copy (TS→Py) | aggregation | S | **Adopt** |
| Provider-diversity fan-out (`diversifyChain` prefer distinct provider/family) + `best_of` + ≥2-survivors quorum | FreeLLMAPI `fusion.ts` | MIT — copy | router (council members) | M | **Adopt** |
| Anonymized peer-rank before synthesis (positional labels, `FINAL RANKING:` contract, mean-ordinal) | karpathy `council.py` | **NO LICENSE — reimplement design** | aggregation (3rd "peer-rank" mode) | M | **Adapt** (+ exclude self-vote) |
| Stance-steering consensus (for/against/neutral + "stance ≠ license to lie" guardrail) | PAL `consensus.py`/`consensus_prompt.py` | Apache-2.0 — copy (keep header) | aggregation / MCP (debate mode) | M | **Adopt** |
| Classify-then-route (reasoning→debate, judgment→vote) + cost-as-capability | DUH `classifier.py`/`voting.py` | **AGPL — reimplement** | router protocol pick | M | **Adapt** |
| PROPOSE→CHALLENGE→REVISE→COMMIT debate (4 framings, sycophancy filter) | DUH `machine.py` | **AGPL — reimplement** | aggregation (advanced) | L | **Adapt (later)** |
| Jaccard convergence (word-set, ≥0.7, skip r1, cap 3) | DUH `convergence.py` | **AGPL — reimplement** (std math) | debate early-exit | S | **Adapt** |
| Confidence = adversarial-rigor capped by domain | DUH `handlers.py` | **AGPL — reimplement** | aggregation returns | S | **Adapt** |
| Capability registry as data (per-model JSON: ctx window, json-mode, intelligence_score) + key-presence activation | PAL `conf/*_models.json` | Apache-2.0 — copy | router/config (add our `privacy_tier`) | M | **Adopt** |
| Escalating cooldown ladder by error class (transient 90s vs daily 2m→10m→1h→1d) | FreeLLMAPI `ratelimit.ts` | MIT — copy | telemetry/rotation | M | **Adapt** (LiteLLM covers basics) |
| MCP structured returns (`status`+`next_steps`, `continuation_id`) | PAL `base_models.py` | Apache-2.0 — copy | MCP surface | S | **Adopt** |
| Random-chair selection (rotate the judge) | ai-council-mcp `synthesis.py` | MIT — copy | aggregation | S | **Adopt** |
| Dashboard, sequential consensus, string-magic errors | FreeLLMAPI / PAL / ai-council | — | — | — | **Skip** (MCP-driven; parallel; typed errors) |

## 2. Best practices to adopt
- **Rate-limit:** LiteLLM natively has per-deployment `rpm`/`tpm`, `allowed_fails`+`cooldown_time`, per-error `retry_policy`, `fallbacks=[{...}]` — configure in `config.yaml` instead of hand-rolling; reserve custom code for the error-class cooldown ladder. (LiteLLM reliability/routing docs.)
- **Aggregation quality:** anonymize before judging/ranking (kills brand-halo bias); peer-rank before synthesis (+ exclude self-votes); forced-disagreement framings + sycophancy filter; convergence early-exit; judge rewrites standalone & reasons (not averages); "stance ≠ license to lie."
- **MCP design:** lowercase tool names, tight param descriptions, absolute file paths, machine-readable `status`+`next_steps` returns, cap per-member response tokens for transport.
- **Setup UX:** key-presence activates a provider (no enable flags); idempotent re-runnable config; unified local token, upstream keys never leave the box.

## 3. Providers for 2c (privacy-tier verdicts — CORRECTS earlier assumptions)
We have Cerebras/Groq/Cloudflare (Tier A, verified no-train).
| Provider | base_url | Card | **Tier + reason** | Add first? |
|---|---|---|---|---|
| **GitHub Models** | `models.github.ai/inference` | No (GH token) | **A** — documented "not used to train"; GPT-class | **YES (first — Tier-A win)** |
| NVIDIA NIM | `integrate.api.nvidia.com/v1` | No | **B** — catalog says no-train BUT privacy policy says records/trains (conflicting) → default B | yes as **B** |
| SambaNova | `api.sambanova.ai/v1` | No | **B** — free-tier data use undocumented / under legal review → default B | yes as **B** |
| Mistral | `api.mistral.ai/v1` | No | **B** — free tier trains by default (opt-out exists) | yes (B) |
| Gemini (free) | native | No | **B** — trains/retains free tier | yes (B) |
| Cohere trial | native | No | **B** — trial undocumented | low |
| OpenRouter `:free` | `openrouter.ai/api/v1` | No | **B default** (per-route ZDR varies) | optional |
| GLM/DeepSeek/Ollama-Cloud | various | No | **B** (CN train/retain) | public-only |
| Keyless (Pollinations/OVH/Kilo) | various | No key | **B (hard)** — zero-signup = zero ToS | optional public breadth |

Verified Tier-A (ours): Cerebras (no retain/train, 1M tok/day), Groq (no-train, self-serve ZDR toggle — enable it).
**First to add:** GitHub Models (Tier A). Then Mistral+SambaNova+NIM as Tier-B breadth (public prompts only).

## 4. Distribution / `consilium init` ideas
- Key-presence activation (PAL); idempotent re-runnable init (FreeLLMAPI); wizard prompts per Tier-A key → **live 1-token ping** → green/red readiness table; one-line path-agnostic installer (venv+deps+`.env` chmod600+`claude mcp add`+start LiteLLM); config schema `keys[]{platform,key,label,enabled}` + our `privacy_tier`; README leads with privacy hook; unified local token as a security feature.

## 5. Top-5 highest-leverage borrows
1. ai-council anonymized synthesis prompt + code-names (MIT — copy, NOTICE Akuti).
2. FreeLLMAPI Fusion judge prompt + `diversifyChain` (MIT — copy).
3. PAL stance-steering + honesty guardrail (Apache — copy w/ header).
4. karpathy peer-rank → mean-ordinal (NO LICENSE — reimplement, add self-vote exclusion).
5. DUH Jaccard convergence + rigor-confidence (AGPL — reimplement; math is standard).
Free win: configure LiteLLM native `rpm/tpm/allowed_fails/cooldown_time/retry_policy/fallbacks`.

## 6. Confidence + gaps
Licenses verified (ai-council MIT, FreeLLMAPI MIT, PAL Apache-2.0, DUH AGPL-3.0, karpathy **no LICENSE**). NIM & SambaNova privacy genuinely ambiguous → **default Tier B**, confirm endpoint ToS before ever promoting to A. Provider free model IDs/limits drift — re-verify at implementation.
