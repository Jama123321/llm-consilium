import httpx

from consilium import env_file, init
from consilium.providers import PROVIDERS


def test_mask_hides_secret():
    assert init.mask("") == "not set"
    assert "1234" in init.mask("csk-abcd1234")  # last-4 surfaced for recognition
    assert "abcd1234" not in init.mask("csk-abcd1234")  # full value never shown


def test_live_ping_ok_and_error():
    def handler(request):
        return httpx.Response(200 if "good" in request.headers["authorization"] else 401)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    groq = next(p for p in PROVIDERS if p.key == "groq")
    assert init.live_ping(groq, {"GROQ_API_KEY": "good"}, client=client).ok is True
    assert init.live_ping(groq, {"GROQ_API_KEY": "bad"}, client=client).ok is False


def test_run_writes_keys_and_reports_readiness(tmp_path, capsys):
    p = tmp_path / ".env"
    # scripted answers: one per env_var across all providers, in order.
    # cerebras, groq, cloudflare(token, base), github, mistral, sambanova, nvidia
    answers = iter(["csk-cere", "gsk-groq", "", "", "", "", "", ""])
    lines: list[str] = []

    def prompt(_msg):
        return next(answers)

    def ping(provider, env):
        return init.PingResult(ok=True, detail="ok")

    rc = init.run(env_path=p, prompt=prompt, echo=lines.append, ping=ping)
    assert rc == 0
    saved = env_file.load(p)
    assert saved["CEREBRAS_API_KEY"] == "csk-cere" and saved["GROQ_API_KEY"] == "gsk-groq"
    assert saved["LITELLM_MASTER_KEY"].startswith("sk-")  # generated
    # only providers with all keys are pinged; cloudflare (token+base skipped) is dormant
    joined = "\n".join(lines)
    assert "Cerebras" in joined and "dormant" in joined
    assert "csk-cere" not in joined and "gsk-groq" not in joined  # secrets never echoed


def test_run_keeps_existing_master_and_unknown(tmp_path):
    p = tmp_path / ".env"
    env_file.write(p, {"LITELLM_MASTER_KEY": "sk-keepme", "WEIRD": "w"})
    rc = init.run(env_path=p, prompt=lambda _m: "", echo=lambda _l: None,
                  ping=lambda _p, _e: init.PingResult(True, "ok"))
    assert rc == 0
    saved = env_file.load(p)
    assert saved["LITELLM_MASTER_KEY"] == "sk-keepme"  # preserved, not regenerated
    assert saved["WEIRD"] == "w"  # unknown key preserved
