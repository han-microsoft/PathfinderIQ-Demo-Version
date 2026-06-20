"""agentkit.tokens — tiktoken token counter (domain-blind).

Public surface: ``from agentkit.tokens import count_tokens``.

Requires the ``tokens`` extra (``pip install agentkit[tokens]``) for
``tiktoken``. The encoder is lazily initialised on first ``count_tokens``
call, so importing this module never pays encoder-setup cost and (if the
extra is installed) never imports tiktoken at module load.

Encoder selection reads the active model from the registered settings
(``agentkit.config.get_settings().llm_model``); unknown models fall back to
``cl100k_base``.
"""

from __future__ import annotations

from typing import Any

_encoder: Any | None = None


def _get_encoder() -> Any:
    """Return the shared tokenizer, creating it on first use.

    Avoids import-time tiktoken initialisation so lightweight imports and
    tests do not pay encoder setup cost unless token counting is needed.
    """
    global _encoder
    if _encoder is not None:
        return _encoder

    import tiktoken

    from agentkit.config import get_settings

    model = get_settings().llm_model
    try:
        _encoder = tiktoken.encoding_for_model(model)
    except KeyError:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """Count tokens in a string using tiktoken.

    Args:
        text: The input string to tokenize.

    Returns:
        Number of tokens (non-negative integer). Empty string returns 0.
    """
    return len(_get_encoder().encode(text))


__all__ = ["count_tokens"]
