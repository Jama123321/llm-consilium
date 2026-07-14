from pathlib import Path

UNIT = Path(__file__).resolve().parents[1] / "deploy" / "consilium-proxy.service"


def _text():
    return UNIT.read_text()


def test_execstart_points_at_run_proxy():
    text = _text()
    assert "ExecStart=" in text
    assert "scripts/run-proxy.sh" in text


def test_restart_on_failure():
    assert "Restart=on-failure" in _text()


def test_wanted_by_default_target():
    assert "WantedBy=default.target" in _text()


def test_no_secret_literal():
    text = _text()
    assert "sk-" not in text and "csk-" not in text and "gsk_" not in text
