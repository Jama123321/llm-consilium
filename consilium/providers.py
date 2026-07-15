from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    tier: str
    env_vars: tuple[str, ...]
    signup: str
    ping_base_url: str  # for cloudflare, the base comes from CLOUDFLARE_API_BASE at ping time
    ping_model: str


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "cerebras", "Cerebras", "A", ("CEREBRAS_API_KEY",),
        "cloud.cerebras.ai -> API Keys (free, 1M tokens/day)",
        "https://api.cerebras.ai/v1", "zai-glm-4.7",
    ),
    Provider(
        "groq", "Groq", "A", ("GROQ_API_KEY",),
        "console.groq.com -> API Keys (free)",
        "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile",
    ),
    Provider(
        "cloudflare", "Cloudflare Workers AI", "A",
        ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_BASE"),
        "dash.cloudflare.com -> My Profile -> API Tokens -> 'Workers AI' template; "
        "API base https://api.cloudflare.com/client/v4/accounts/<id>/ai/v1",
        "", "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    ),
    Provider(
        "github", "GitHub Models", "A", ("GITHUB_API_KEY",),
        "github.com -> Settings -> Developer settings -> fine-grained token, Models: Read",
        "https://models.github.ai/inference", "openai/gpt-4.1-mini",
    ),
    Provider(
        "mistral", "Mistral", "B", ("MISTRAL_API_KEY",),
        "console.mistral.ai -> API Keys (free; trains on prompts -> Tier B)",
        "https://api.mistral.ai/v1", "mistral-small-latest",
    ),
    Provider(
        "sambanova", "SambaNova", "B", ("SAMBANOVA_API_KEY",),
        "cloud.sambanova.ai -> API Keys (free)",
        "https://api.sambanova.ai/v1", "Meta-Llama-3.3-70B-Instruct",
    ),
    Provider(
        "nvidia", "NVIDIA NIM", "B", ("NVIDIA_NIM_API_KEY",),
        "build.nvidia.com -> API Key (free credits)",
        "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct",
    ),
)
