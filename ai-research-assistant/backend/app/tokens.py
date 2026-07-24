CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens(text: str) -> int:
    """Return a lightweight token estimate for prompt budgeting.

    The estimate intentionally avoids provider-specific tokenizers so local tests
    stay fast and offline. For English/Spanish text, four characters per token is
    a practical approximation for budgeting RAG context.
    """
    normalized_text = text.strip()
    if not normalized_text:
        return 0
    return max(1, len(normalized_text) // CHARS_PER_TOKEN_ESTIMATE)


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Trim text to an approximate token budget without cutting empty budgets."""
    if max_tokens <= 0:
        return ""

    max_characters = max_tokens * CHARS_PER_TOKEN_ESTIMATE
    normalized_text = text.strip()
    if len(normalized_text) <= max_characters:
        return normalized_text

    return normalized_text[:max_characters].rstrip() + "..."
