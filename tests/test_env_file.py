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


def test_write_replaces_symlink_instead_of_following(tmp_path):
    if os.name != "posix":
        import pytest
        pytest.skip("symlink creation needs privilege on Windows")
    target = tmp_path / "target.txt"
    target.write_text("PREEXISTING")
    link = tmp_path / ".env"
    os.symlink(target, link)
    env_file.write(link, {"LITELLM_MASTER_KEY": "sk-secret"})
    assert not link.is_symlink()  # symlink replaced by a real file
    assert env_file.load(link)["LITELLM_MASTER_KEY"] == "sk-secret"
    assert target.read_text() == "PREEXISTING"  # attacker target NOT written through


def test_write_tightens_perms_on_preexisting_loose_file(tmp_path):
    if os.name != "posix":
        import pytest
        pytest.skip("posix permissions")
    p = tmp_path / ".env"
    p.write_text("OLD=1")
    p.chmod(0o644)
    env_file.write(p, {"LITELLM_MASTER_KEY": "sk-1"})
    assert (p.stat().st_mode & 0o777) == 0o600  # loose perms fixed atomically, no race
