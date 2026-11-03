"""Unique hub title helper — chapter summarization.

New titles at first creation must remain unique. When the draft title
collides with an existing hub title, a distinctive phrase from the
chapter labels (skipping generic words) becomes the suffix; fallback
is the lesson date, then an incrementing number.
"""

import re

# Generic chapter words that don't distinguish lessons: every lesson
# has an intro/overview/summary, so they can't disambiguate.
STOPWORDS = {
    "introduction", "intro", "overview", "welcome", "summary",
    "conclusion", "closing", "next", "steps", "questions",
    "answered", "discussion", "explained", "general", "and",
    "the", "a", "an", "of", "for", "in", "on", "to", "with",
}

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_TITLE_WORD_RE = re.compile(r"[A-Za-z0-9]+")

def _words(text):
    return [w.lower() for w in _WORD_RE.findall(text or "")]

def distinctive_phrase(chapters, base_title):
    """Pick a distinctive 2-3 word phrase from chapter labels.

    Skips labels whose words are all stopwords or already in the
    base title. Returns the first distinctive label's words (up to 3),
    title-cased, or "" when nothing distinctive exists.
    """
    base_words = set(_TITLE_WORD_RE.findall((base_title or "").lower()))
    for ch in chapters or []:
        label = (ch.get("label") if isinstance(ch, dict) else "") or ""
        ws = _words(label)
        # distinctive words are those not in stopwords and not already in title
        keep = [w for w in ws if w not in STOPWORDS and w not in base_words]
        if keep:
            # use up to 3 words of original label's kept words, title-cased
            phrase = " ".join(w.capitalize() for w in keep[:3])
            return phrase
        # fallback: if label has any non-stopword at all (even if in title), use it
    for ch in chapters or []:
        label = (ch.get("label") if isinstance(ch, dict) else "") or ""
        ws = _words(label)
        keep = [w for w in ws if w not in STOPWORDS]
        if keep:
            phrase = " ".join(w.capitalize() for w in keep[:3])
            # ensure it's not identical to base title
            if phrase.lower() != (base_title or "").lower():
                return phrase
    return ""


def unique_title(proposed, chapters=None, lesson_date="", existing=None):
    """Return a unique title derived from proposed.

    proposed: the draft title (string).
    chapters: list of {start, label} dicts (may be empty).
    lesson_date: human date like "Oct 29, 2026" (may be empty).
    existing: iterable of titles already in the hub (case-sensitive).
    """
    existing = set(existing or [])
    title = (proposed or "").strip() or "Untitled"
    if title not in existing:
        return title
    phrase = distinctive_phrase(chapters or [], title)
    if phrase:
        cand = f"{title} — {phrase}"
        if cand not in existing:
            return cand
    if lesson_date:
        cand = f"{title} — {lesson_date}"
        if cand not in existing:
            return cand
    i = 2
    while True:
        cand = f"{title} ({i})"
        if cand not in existing:
            return cand
        i += 1
