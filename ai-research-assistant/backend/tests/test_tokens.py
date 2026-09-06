import pytest

from app.tokens import estimate_tokens, truncate_to_token_budget


@pytest.mark.parametrize(("text", "expected"), [("", 0), ("abc", 1), ("abcdefgh", 2)])
def test_estimate_tokens_uses_lightweight_character_budget(text, expected):
    assert estimate_tokens(text) == expected


def test_truncate_to_token_budget_handles_limits():
    assert truncate_to_token_budget("content", 0) == ""
    assert truncate_to_token_budget("short", 10) == "short"
    assert truncate_to_token_budget("abcdefghij", 2) == "abcdefgh..."
