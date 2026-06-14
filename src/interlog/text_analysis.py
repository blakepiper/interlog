"""Reconstruct typed text from the keystroke log and run light lexical analysis.

This is opt-in and privacy-gated: it turns raw keystrokes into readable text, so
it must only run on request, and never on a session recorded in privacy mode
(where key identities were deliberately not logged).

Reconstruction is approximate by nature: keystrokes are captured globally (every
app/field concatenated, with no document boundaries), and caret moves via arrow
keys or mouse clicks are not tracked, so edits may not land where the typist saw
them. Treat the transcript as a reviewable artifact, not ground truth.
"""

import re
from collections import Counter

# Small built-in stopword list, kept dependency-free.
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else", "of", "to", "in",
    "on", "for", "with", "as", "at", "by", "from", "is", "are", "was", "were",
    "be", "been", "being", "it", "this", "that", "these", "those", "i", "you",
    "he", "she", "we", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "its", "our", "their", "not", "no", "yes", "do", "does", "did", "so",
    "up", "out", "about", "into", "over", "again", "just", "than", "too", "very",
    "can", "will", "would", "should", "could", "have", "has", "had", "what",
    "which", "who", "when", "where", "why", "how", "all", "any", "both", "each",
    "more", "most", "some", "such",
}

# Special keys that map to characters when reconstructing text.
_SPECIAL = {
    "Key.space": " ",
    "Key.enter": "\n",
    "Key.return": "\n",
    "Key.tab": "\t",
}


def is_redacted(events):
    """True if key identities were redacted (i.e. the session used privacy mode)."""
    return any(
        e.get("key") == "[REDACTED]"
        for e in events
        if e.get("event_type") == "key_press"
    )


def reconstruct_text(events):
    """Approximate the typed text from key_press events.

    Backspace removes the previous character; space/enter/tab map to whitespace;
    other special keys (shift, ctrl, arrows, ...) are ignored. See the module
    docstring for the inherent limitations.
    """
    out = []
    for e in events:
        if e.get("event_type") != "key_press":
            continue
        key = e.get("key") or ""
        if len(key) == 1:
            out.append(key)
        elif key in _SPECIAL:
            out.append(_SPECIAL[key])
        elif key == "Key.backspace":
            if out:
                out.pop()
    return "".join(out)


def lexical_stats(text, top_n=15):
    """Dependency-free lexical summary of reconstructed text."""
    words = re.findall(r"[a-z']+", text.lower())
    keywords = Counter(w for w in words if len(w) > 2 and w not in STOPWORDS)
    return {
        "char_count": len(text),
        "word_count": len(words),
        "unique_words": len(set(words)),
        "avg_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0,
        "top_keywords": keywords.most_common(top_n),
    }
