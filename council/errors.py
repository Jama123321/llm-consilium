class ConsiliumError(Exception):
    """Base class for all council errors."""


class PrivacyRefusal(ConsiliumError):
    """Prompt contains a secret, or no member satisfies the required tier."""


class NoEligibleMember(ConsiliumError):
    """No member has the requested capability."""


class AllMembersFailed(ConsiliumError):
    """Every fan-out member abstained."""


class MemberCallError(ConsiliumError):
    """A single member call failed (non-200 / timeout)."""

    def __init__(self, alias: str, detail: str) -> None:
        super().__init__(f"{alias}: {detail}")
        self.alias = alias
        self.detail = detail
