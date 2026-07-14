import os

from consilium import env_file


def test_load_parses_keys_and_skips_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nA=1\n\nB = two \n# x\nUNKNOWN_X=zzz\n")
    assert env_file.load(p) == {"A": "1", "B": "two", "UNKNOWN_X": "zzz"}


def test_load_missing_file_returns_empty(tmp_path):
    assert env_file.load(tmp_path / "nope.env") == {}


def test_write_roundtrips_and_preserves_unknown(tmp_path):
    p = tmp_path / ".env"
    values = {
        "CEREBRAS_API_KEY": "csk-x",
        "MISTRAL_API_KEY": "m",
        "LITELLM_MASTER_KEY": "sk-1",
        "WEIRD": "w",
    }
    env_file.write(p, values)
    assert env_file.load(p) == values  # every key round-trips, incl. unknown "WEIRD"


def test_write_sets_posix_permissions(tmp_path):
    p = tmp_path / ".env"
    env_file.write(p, {"LITELLM_MASTER_KEY": "sk-1"})
    if os.name == "posix":
        assert (p.stat().st_mode & 0o777) == 0o600
