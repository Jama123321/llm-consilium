from __future__ import annotations

from consilium import env_file
from council import orchestrator, registry


class CouncilService:
    def __init__(self, orch) -> None:
        self._orch = orch

    @classmethod
    def build(cls) -> CouncilService:
        key = env_file.load().get("LITELLM_MASTER_KEY", "")
        return cls(orchestrator.build(api_key=key))

    async def ask(self, prompt, *, model=None, capability=None, sensitivity="sensitive"):
        return await self._orch.ask(prompt, model=model, capability=capability,
                                    sensitivity=sensitivity)

    async def council(self, prompt, *, members=None, size=None, mode=None,
                      sensitivity="sensitive", on_progress=None):
        return await self._orch.council(prompt, members=members, size=size, mode=mode,
                                        sensitivity=sensitivity, on_progress=on_progress)

    def list_models(self) -> list[dict]:
        members = registry.load_members(
            orchestrator.DEFAULT_CONFIG_PATH, available_keys=registry.available_env_keys())
        return [{"alias": m.alias, "tier": m.privacy_tier,
                 "provider_family": m.provider_family, "capabilities": list(m.capabilities)}
                for m in members]
