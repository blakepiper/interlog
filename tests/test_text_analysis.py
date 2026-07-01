"""Tests for interlog.text_analysis: text reconstruction and lexical stats."""

from interlog.text_analysis import is_redacted, lexical_stats, reconstruct_text


def test_reconstruct_text_handles_backspace_and_whitespace():
    events = [
        {"event_type": "key_press", "key": "h"},
        {"event_type": "key_press", "key": "e"},
        {"event_type": "key_press", "key": "y"},
        {"event_type": "key_press", "key": "Key.backspace"},
        {"event_type": "key_press", "key": "Key.space"},
        {"event_type": "key_press", "key": "u"},
        {"event_type": "key_press", "key": "Key.shift"},   # ignored
        {"event_type": "mouse_down", "key": ""},            # non-key ignored
    ]
    assert reconstruct_text(events) == "he u"


def test_lexical_stats_keywords_and_counts():
    stats = lexical_stats("The cat sat on the mat. The cat ran.")
    assert stats["word_count"] == 9
    # stopwords ("the", "on") excluded; "cat" is the top keyword
    assert stats["top_keywords"][0] == ("cat", 2)


def test_is_redacted_detects_privacy_mode():
    assert is_redacted([{"event_type": "key_press", "key": "[REDACTED]"}]) is True
    assert is_redacted([{"event_type": "key_press", "key": "a"}]) is False


def test_reconstruct_text_handles_delete():
    events = [
        {"event_type": "key_press", "key": "h"},
        {"event_type": "key_press", "key": "i"},
        {"event_type": "key_press", "key": "Key.delete"},
    ]
    assert reconstruct_text(events) == "h"


def test_lexical_stats_ignores_bare_apostrophe():
    stats = lexical_stats("don't ' '' stop")
    words = {"don't", "stop"}
    assert stats["word_count"] == len(words)
