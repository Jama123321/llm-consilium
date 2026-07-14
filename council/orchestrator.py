from __future__ import annotations

from council import aggregate as agg
from council import client, fanout, privacy, registry, router, usage
from council.errors import AllMembersFailed, MemberCallError, NoEligibleMember, PrivacyRefusal
from council.types import AskResult, AsyncCaller, CouncilResult, Member

DEFAULT_BASE_URL = "http://127.0.0.1:4000/v1"
CLASSIFIER_ALIAS = "council/groq-llama-70b"  # must be Tier-A; used only if within the allowed set
# must be Tier-A; used as judge only if within the chosen set
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
        store: usage.UsageStore | None = None,
    ) -> None:
        self._members = members
        self._caller = caller
        self._classifier_alias = classifier_alias
        self._chair_alias = chair_alias
        self._default_member_aliases = default_member_aliases
        self._store = store

    def _by_alias(self, alias: str) -> Member | None:
        return next((m for m in self._members if m.alias == alias), None)

    def _counts(self) -> dict[str, tuple[int, int]]:
        return self._store.counts() if self._store is not None else {}

    def usage_summary(self) -> list[dict]:
        return usage.summary(self._members, self._counts())

    def _classifier_for(self, allowed: list[Member]) -> str:
        # The classifier receives the prompt, so it must satisfy the privacy gate too:
        # use the configured classifier only if it survived the tier filter, else the
        # fastest allowed member.
        if not allowed:
            raise NoEligibleMember("no members available for the requested sensitivity")
        if any(m.alias == self._classifier_alias for m in allowed):
            return self._classifier_alias
        return max(allowed, key=lambda m: m.rpm).alias

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
        pool = usage.available(allowed, self._counts()) or allowed
        auto = capability is None
        if auto:
            capability = await router.classify(
                prompt, caller=self._caller, classifier_alias=self._classifier_for(allowed)
            )
        errors: list[str] = []
        for member in router.rank(pool, capability):
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
        pool = usage.available(allowed, self._counts()) or allowed
        wanted = members or self._default_member_aliases
        chosen = [m for m in pool if m.alias in wanted] or [
            m for m in allowed if m.alias in wanted
        ]
        if not chosen:
            raise NoEligibleMember("no eligible council members for this sensitivity")
        answers = await fanout.fan_out(prompt, chosen, self._caller)
        merged, mode, disagreements, judge_used = await agg.aggregate(
            prompt, answers, caller=self._caller, judge_aliases=self._judge_order(chosen)
        )
        return CouncilResult(
            answer=merged, per_member=answers, disagreements=disagreements,
            judge_used=judge_used, mode=mode,
        )

    def _judge_order(self, chosen: list[Member]) -> list[str]:
        # Judges come only from the already-tier-filtered chosen members, so the chair
        # is used only when it survived the gate and is part of this council.
        ordered = [m.alias for m in sorted(chosen, key=lambda m: m.strength, reverse=True)]
        if self._chair_alias in ordered:
            ordered.remove(self._chair_alias)
            ordered.insert(0, self._chair_alias)
        return ordered


def build(
    config_path: str = "proxy/config.yaml", *, base_url: str = DEFAULT_BASE_URL, api_key: str
) -> Orchestrator:
    members = registry.load_members(config_path)
    store = usage.UsageStore()
    caller = client.make_caller(base_url, api_key, recorder=store.record)
    return Orchestrator(members, caller, store=store)
