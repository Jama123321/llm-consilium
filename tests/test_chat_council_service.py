import asyncio

from consilium_chat.council_service import CouncilService


class FakeOrch:
    def __init__(self):
        self.calls = []

    async def ask(self, prompt, *, model=None, capability=None, sensitivity="sensitive"):
        self.calls.append(("ask", prompt, model, capability, sensitivity))
        return "ASK_RESULT"

    async def council(self, prompt, *, members=None, size=None, mode=None,
                      sensitivity="sensitive", on_progress=None):
        self.calls.append(("council", prompt, mode, sensitivity))
        return "COUNCIL_RESULT"


def test_ask_delegates():
    svc = CouncilService(FakeOrch())
    r = asyncio.run(svc.ask("q", model="m", capability=None, sensitivity="public"))
    assert r == "ASK_RESULT"
    assert svc._orch.calls[0] == ("ask", "q", "m", None, "public")


def test_council_delegates():
    svc = CouncilService(FakeOrch())
    r = asyncio.run(svc.council("q", members=None, size=3, mode="debate", sensitivity="sensitive"))
    assert r == "COUNCIL_RESULT"
    assert svc._orch.calls[0][0] == "council" and svc._orch.calls[0][2] == "debate"
