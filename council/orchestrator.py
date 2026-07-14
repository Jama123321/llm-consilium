from __future__ import annotations

from council import aggregate as agg
from council import client, fanout, privacy, registry, router
from council.errors import AllMembersFailed, MemberCallError, NoEligibleMember, PrivacyRefusal
from council.types import AskResult, AsyncCaller, CouncilResult, Member

DEFAULT_BASE_URL = "http://127.0.0.1:4000/v1"
CLASSIFIER_ALIAS = "council/groq-llama-70b"
CHAIR_ALIAS = "council/cerebras-glm-4.7"
DEFAULT_MEMBER_ALIASES = (
    "council/cerebras-glm-4.7",
    "council/groq-gpt-oss-120b",
    "council/cloudflare-llama-70b",
)


class Orchestrator:
    def __init__(
        self,
        members: list[Member],
        caller: AsyncCaller,
        *,
        classifier_alias: str = CLASSIFIER_ALIAS,
        chair_alias: str = CHAIR_ALIAS,
        default_member_aliases: tuple[str, ...] = DEFAULT_MEMBER_ALIASES,
    ) -> None:
        self._members = members
        self._caller = caller
        self._classifier_alias = classifier_alias
        self._chair_alias = chair_alias
        self._default_member_aliases = default_member_aliases

    def _by_alias(self, alias: str) -> Member | None:
        return next((m for m in self._members if m.alias == alias), None)

    async def ask(
        self, prompt: str, *, model: str | None = None, capability: str | None = None,
        sensitivity: str = "sensitive",
    ) -> AskResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        if model is not None:
            member = self._by_alias(model)
            if member is None or member not in allowed:
                raise PrivacyRefusal(
                    f"model {model} is not available for sensitivity={sensitivity}"
                )
            answer = await self._caller(member.alias, prompt)
            return AskResult(answer=answer, model_used=member.alias, capability=None, note="direct")
        auto = capability is None
        if auto:
            capability = await router.classify(
                prompt, caller=self._caller, classifier_alias=self._classifier_alias
            )
        errors: list[str] = []
        for member in router.rank(allowed, capability):
            try:
                answer = await self._caller(member.alias, prompt)
            except MemberCallError as exc:
                errors.append(f"{member.alias}[{exc.detail}]")
                continue
            trail = " -> ".join([*errors, member.alias])
            note = f"{'auto-routed' if auto else 'routed'}: {capability} -> {trail}"
            return AskResult(
                answer=answer, model_used=member.alias, capability=capability, note=note
            )
        raise AllMembersFailed(f"all '{capability}' members failed: {', '.join(errors)}")

    async def council(
        self, prompt: str, *, members: tuple[str, ...] | None = None, sensitivity: str = "sensitive"
    ) -> CouncilResult:
        privacy.scan_secrets(prompt)
        allowed = privacy.allowed_members(self._members, sensitivity)
        wanted = members or self._default_member_aliases
        chosen = [m for m in allowed if m.alias in wanted]
        if not chosen:
            raise NoEligibleMember("no eligible council members for this sensitivity")
        answers = await fanout.fan_out(prompt, chosen, self._caller)
        merged, mode, disagreements = await agg.aggregate(
            prompt, answers, caller=self._caller, judge_alias=self._chair_alias
        )
        judge_used = self._chair_alias if mode == "judge" else None
        return CouncilResult(
            answer=merged, per_member=answers, disagreements=disagreements,
            judge_used=judge_used, mode=mode,
        )


def build(
    config_path: str = "proxy/config.yaml", *, base_url: str = DEFAULT_BASE_URL, api_key: str
) -> Orchestrator:
    members = registry.load_members(config_path)
    caller = client.make_caller(base_url, api_key)
    return Orchestrator(members, caller)
