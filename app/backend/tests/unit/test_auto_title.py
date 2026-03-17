"""Auto-title generation — first-message title truncation.

Tests the behavior currently implemented inline in routers/chat.py L99-104.
These tests lock down the contract BEFORE Phase 5 extracts it into
ConversationMetadata.generate_title().

The auto-title algorithm:
    1. If this is the first user message (session.messages is empty)
    2. Take first 50 chars of the message content, stripped
    3. If message is >50 chars, append "…" (unicode ellipsis, not "...")
    4. Set as session.title
    5. On second+ messages, do nothing
"""

import pytest


def _generate_title(content: str) -> str:
    """Replicate routers/chat.py L99-104 auto-title logic as a pure function."""
    title = content[:50].strip()
    if len(content) > 50:
        title += "\u2026"  # Unicode ellipsis "…"
    return title


class TestAutoTitle:
    """Verify auto-title generation matches routers/chat.py behavior."""

    def test_short_message_no_truncation(self):
        """Messages ≤50 chars become the title verbatim."""
        assert _generate_title("Hello world") == "Hello world"

    def test_exactly_50_chars_no_ellipsis(self):
        """Message exactly 50 chars does NOT get ellipsis."""
        msg = "a" * 50
        title = _generate_title(msg)
        assert title == msg
        assert "\u2026" not in title

    def test_51_chars_gets_ellipsis(self):
        """Message at 51 chars gets truncated + ellipsis."""
        msg = "a" * 51
        title = _generate_title(msg)
        assert len(title) == 51  # 50 chars + 1 ellipsis char
        assert title.endswith("\u2026")

    def test_long_message_truncated(self):
        """Long messages are cut at 50 chars + ellipsis."""
        msg = "This is a very long message that definitely exceeds the fifty character limit for auto-titling"
        title = _generate_title(msg)
        assert len(title) == 51  # 50 + ellipsis
        assert title.endswith("\u2026")
        assert title.startswith("This is a very long message that definitely excee")

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped from the title."""
        title = _generate_title("  hello  ")
        assert title == "hello"

    def test_empty_message(self):
        """Empty string produces empty title."""
        assert _generate_title("") == ""

    def test_whitespace_only_message(self):
        """Whitespace-only message produces empty title after strip."""
        assert _generate_title("   ") == ""

    def test_unicode_content(self):
        """Unicode characters in message are preserved."""
        msg = "调查路由器 R-045 的状态"
        title = _generate_title(msg)
        assert title == msg  # Under 50 chars

    def test_newline_in_message(self):
        """Newlines in the first 50 chars are preserved (strip only affects edges)."""
        msg = "Line 1\nLine 2"
        title = _generate_title(msg)
        assert title == "Line 1\nLine 2"

    def test_ellipsis_is_unicode_not_ascii(self):
        """The ellipsis character is U+2026 (…), not three periods (...)."""
        msg = "x" * 100
        title = _generate_title(msg)
        assert "..." not in title
        assert "\u2026" in title
