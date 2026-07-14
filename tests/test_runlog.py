import json

from council.runlog import RunLog


def _read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_disabled_writes_no_file(tmp_path):
    path = tmp_path / "runs.jsonl"
    log = RunLog(path, enabled=False)
    log.record({"tool": "council", "prompt": "hi", "answer": "yo"}, redact=False)
    assert not path.exists()


def test_enabled_writes_one_json_line(tmp_path):
    path = tmp_path / "runs.jsonl"
    log = RunLog(path, enabled=True)
    log.record({"tool": "council", "mode": "judge", "confidence": "high"}, redact=False)
    lines = _read_lines(path)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["tool"] == "council"
    assert entry["mode"] == "judge"
    assert entry["confidence"] == "high"
    assert "ts" in entry


def test_redact_true_nulls_content_and_adds_lengths(tmp_path):
    path = tmp_path / "runs.jsonl"
    log = RunLog(path, enabled=True)
    log.record(
        {
            "tool": "council",
            "prompt": "secret prompt",
            "answer": "secret answer",
            "per_member": [
                {"alias": "council/a", "ok": True, "answer": "member answer"},
            ],
        },
        redact=True,
    )
    entry = _read_lines(path)[0]
    assert entry["redacted"] is True
    assert entry["prompt"] is None
    assert entry["answer"] is None
    assert entry["prompt_len"] == len("secret prompt")
    assert entry["answer_len"] == len("secret answer")
    member = entry["per_member"][0]
    assert member["answer"] is None
    assert member["answer_len"] == len("member answer")
    assert member["alias"] == "council/a"


def test_redact_false_keeps_content(tmp_path):
    path = tmp_path / "runs.jsonl"
    log = RunLog(path, enabled=True)
    log.record(
        {
            "tool": "council",
            "prompt": "keep this",
            "answer": "and this",
            "per_member": [{"alias": "council/a", "ok": True, "answer": "member answer"}],
        },
        redact=False,
    )
    entry = _read_lines(path)[0]
    assert entry["redacted"] is False
    assert entry["prompt"] == "keep this"
    assert entry["answer"] == "and this"
    assert entry["per_member"][0]["answer"] == "member answer"
    assert "prompt_len" not in entry


def test_unwritable_path_does_not_raise(tmp_path):
    # A path whose parent cannot be created (a file used as a directory component).
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    path = blocker / "nested" / "runs.jsonl"
    log = RunLog(path, enabled=True)
    log.record({"tool": "council"}, redact=False)  # must not raise
    assert not path.exists()
