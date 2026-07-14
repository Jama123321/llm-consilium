# Prior-Art Comparison — LLM Consilium (2026-07-14)

> Background-agent research. Question: do similar open-source projects exist, and what is our genuine differentiation?

## Closest matches
- **FreeLLMAPI** — github.com/tashfeenahmed/freellmapi (~16k★, MIT). OpenAI-compatible proxy stacking free tiers of ~18 providers (Google, Groq, Cerebras, Cloudflare, Mistral, NVIDIA, Cohere…) with smart routing, failover, multi-key rotation; a **"Fusion" mode** = parallel fan-out to a panel + judge synthesis; has an MCP endpoint. **Lacks:** privacy/data-policy tiering, secret-scan gate; MCP only advertises usable models (no ask/council/stats tools). *The closest on stack overlap.*
- **PAL / zen-mcp-server** — github.com/BeehiveInnovations/pal-mcp-server (~11.7k★, Apache-2.0). Mature multi-model MCP for Claude Code; `consensus` tool with stance steering + planner/codereview/debug. **Lacks:** free-tier focus, privacy tiering (paid-model orchestrator).
- **Karpathy llm-council** — github.com/karpathy/llm-council (~22.7k★, NO LICENSE). Canonical fan-out → anonymized peer-rank → chairman synthesis. Web app (not MCP), single paid provider (OpenRouter). Spawned an "Awesome-LLM-Council" ecosystem → the category is crowded.
- **ai-council-mcp** — github.com/0xakuti/ai-council-mcp (MIT). Council-as-MCP; anonymized code-names; random-synthesizer. OpenRouter-based, no privacy tiering, no router mode.
- **DUH** — github.com/msitarzewski/duh (AGPL-3.0). Best aggregation logic: adaptive vote/synthesis + PROPOSE→CHALLENGE→REVISE→COMMIT debate with convergence detection. Paid providers, no free/privacy focus.

## Feature comparison (compact)
| Project | Fan-out | Judge/Vote | MCP | Free-tier | Privacy-tier by provider data policy | Local | Setup UX |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Consilium (us)** | ✅ | ✅ adaptive | ✅ ask/council/stats | ✅ | ✅ **A/B train-vs-no-train + secret gate** | ✅ | wizard (planned) |
| FreeLLMAPI | ✅ | ✅ | ~ (info) | ✅ | ❌ | ✅ | dashboard |
| PAL/zen | ~ | ✅ | ✅ | ❌ | ❌ | ✅ | script |
| karpathy | ✅ | ✅ | ❌ web | ❌ | ❌ | ✅ | manual |
| ai-council-mcp | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | manual |
| DUH | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | .env |

## Genuine differentiation (honest)
- Multi-model council + free-tier stacking + MCP are each **commodity** (16k–22k★ incumbents; FreeLLMAPI already does free-stacking+fan-out+MCP).
- **The one unoccupied combination:** privacy tiering by *provider free-tier data policy* (Tier A no-train/no-retain vs Tier B trains-on-free) as a first-class gate in a *free-council MCP*. No OSS project classifies free-tier providers by whether they train on your data. Closest analog = **ZDR-aware routing**, but that is **paid/enterprise** (OpenRouter, Vercel AI Gateway). Our defensible novelty is the *intersection*, not any single feature.

## Recommendation
- **Don't fork** — our intersection isn't served; nothing to fork wholesale. But **stop reinventing commodity layers** (fan-out/aggregation/telemetry exist elsewhere and are better).
- **Borrow** (see borrow-map): DUH aggregation (AGPL → reimplement), ai-council-mcp MCP scaffold (MIT), FreeLLMAPI provider map + key-config UX (MIT).
- **Distribution:** lead README with the privacy hook ("routes your private code only to providers that don't train on it"), not "LLM council"; keep MIT license (avoid AGPL contamination); ship the key wizard (no competitor has one).

## Confidence
High on landscape shape + the differentiation claim. Star counts point-in-time (2026-07-14). Could not exhaustively verify every long-tail council-MCP fork.
