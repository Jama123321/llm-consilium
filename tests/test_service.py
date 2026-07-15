from consilium import env_file, paths, service


def test_proxy_command_shape():
    cmd = service.proxy_command()
    assert cmd[0].endswith("litellm") or cmd[0].endswith("litellm.exe")
    assert "--config" in cmd and str(paths.CONFIG_PATH) in cmd
    assert "--port" in cmd and "4000" in cmd


def test_proxy_env_merges_dotenv(tmp_path, monkeypatch):
    envf = tmp_path / ".env"
    env_file.write(envf, {"CEREBRAS_API_KEY": "csk-x", "LITELLM_MASTER_KEY": "sk-1"})
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    merged = service.proxy_env(envf)
    assert merged["CEREBRAS_API_KEY"] == "csk-x" and "PATH" in merged  # dotenv over os.environ


def test_start_background_writes_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PID_PATH", tmp_path / "proxy.pid")
    monkeypatch.setattr(paths, "LOG_PATH", tmp_path / "proxy.log")

    class FakeProc:
        pid = 4242

    calls = {}

    def spawn(cmd, **kw):
        calls["cmd"] = cmd
        return FakeProc()

    rc = service.start(spawn=spawn, is_alive=lambda _p: False,
                       env_path=tmp_path / "missing.env", echo=lambda _m: None)
    assert rc == 0
    assert (tmp_path / "proxy.pid").read_text().strip() == "4242"
    assert calls["cmd"][0].endswith("litellm") or calls["cmd"][0].endswith("litellm.exe")


def test_start_background_noop_when_already_running(tmp_path, monkeypatch):
    pid_file = tmp_path / "proxy.pid"
    pid_file.write_text("999")
    monkeypatch.setattr(paths, "PID_PATH", pid_file)
    spawned = []
    service.start(spawn=lambda *a, **k: spawned.append(1), is_alive=lambda _p: True,
                  env_path=tmp_path / "x.env", echo=lambda _m: None)
    assert spawned == []  # did not spawn a second proxy


def test_start_foreground_uses_exec_fn():
    captured = {}
    service.start(foreground=True, exec_fn=lambda cmd, env: captured.update(cmd=cmd) or 0,
                  env_path="nope.env", echo=lambda _m: None)
    assert "--config" in captured["cmd"]


def test_stop_terminates_and_clears_pid(tmp_path, monkeypatch):
    pid_file = tmp_path / "proxy.pid"
    pid_file.write_text("321")
    monkeypatch.setattr(paths, "PID_PATH", pid_file)
    killed = []
    rc = service.stop(terminate=killed.append, echo=lambda _m: None)
    assert rc == 0 and killed == [321] and not pid_file.exists()


def test_stop_when_not_running(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PID_PATH", tmp_path / "none.pid")
    assert service.stop(terminate=lambda _p: None, echo=lambda _m: None) == 0


def test_status_reports_injected(tmp_path, monkeypatch):
    pid_file = tmp_path / "proxy.pid"
    pid_file.write_text("55")
    monkeypatch.setattr(paths, "PID_PATH", pid_file)
    out = []
    service.status(is_alive=lambda _p: True, port_open=lambda _h, _p: True, echo=out.append)
    joined = "\n".join(out)
    assert "running" in joined and "listening" in joined
