import pytest

from council import privacy
from council.errors import PrivacyRefusal
from council.types import Member

A = Member("a", "A", ("general",), 3, 5)
B = Member("b", "B", ("general",), 3, 5)


def test_scan_passes_clean_prompt():
    privacy.scan_secrets("please refactor this pure function")  # no raise


@pytest.mark.parametrize(
    "bad",
    [
        "here is my key sk-abcdefghijklmnop12345",
        "CEREBRAS csk-abcdefghijklmnop12345",
        "token gsk_abcdefghijklmnop12345",
        "-----BEGIN RSA PRIVATE KEY-----",
        "OPENAI_API_KEY=supersecretvalue",
    ],
)
def test_scan_refuses_secrets(bad):
    with pytest.raises(PrivacyRefusal):
        privacy.scan_secrets(bad)


def test_sensitive_keeps_only_tier_a():
    assert privacy.allowed_members([A, B], "sensitive") == [A]


def test_public_keeps_all():
    assert privacy.allowed_members([A, B], "public") == [A, B]
