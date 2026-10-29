"""Turn a transcribed narration into a plan location and an item.

Staff say locations in spoken form ("aisle one bay area two"); plan locations are codes like "A1-B2".
Matching is on the numbers in order, so "A1-B2", "aisle 1 bay 2" and "aisle one, bay area two" agree.
"""
import difflib
import re

_NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
)}


def _numbers_in(token: str) -> list[int]:
    if token in _NUMBER_WORDS:
        return [_NUMBER_WORDS[token]]
    return [int(d) for d in re.findall(r"\d+", token)]


def spoken_numbers(text: str, limit: int = 2) -> list[int]:
    """The first `limit` numbers said after the word "aisle" (or from the start if it is absent)."""
    tokens = re.findall(r"[a-z]+\d*|\d+", text.lower())
    if "aisle" in tokens:
        tokens = tokens[tokens.index("aisle") + 1:]
    found: list[int] = []
    for token in tokens:
        found.extend(_numbers_in(token))
        if len(found) >= limit:
            break
    return found[:limit]


def resolve_location(transcript: str, locations: list[str]) -> str | None:
    """The plan location whose numbers match what was said, or None if none or several match."""
    said = spoken_numbers(transcript)
    if not said:
        return None
    matches = [loc for loc in locations if [int(d) for d in re.findall(r"\d+", loc)][: len(said)] == said]
    return matches[0] if len(matches) == 1 else None


def mentioned_items(transcript: str, items: list[str]) -> list[str]:
    """Items whose every word is in the narration (allowing a near-miss spelling), best match first."""
    spoken = re.findall(r"[a-z0-9]+", transcript.lower())

    def hit(word: str) -> bool:
        return word in spoken or bool(difflib.get_close_matches(word, spoken, n=1, cutoff=0.85))

    scored = []
    for item in items:
        words = re.findall(r"[a-z0-9]+", item.lower())
        if words and all(hit(w) for w in words):
            scored.append((len(words), item))
    return [item for _, item in sorted(scored, reverse=True)]


def resolve_item(transcript: str, items: list[str]) -> str | None:
    """The one item named. If the narration names two unrelated items, None (a mixed clip)."""
    found = mentioned_items(transcript, items)
    # "TV unit" and "TV stand" both contain "tv"; a longer exact match wins over a prefix of it.
    found = [i for i in found if not any(i != o and i.lower() in o.lower() for o in found)]
    return found[0] if len(found) == 1 else None
