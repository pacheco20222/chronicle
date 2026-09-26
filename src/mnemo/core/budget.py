def estimate_tokens(text: str) -> int:
    # Approximate local token count; avoids adding a tokenizer dependency.
    return max(1, len(text) // 4)
