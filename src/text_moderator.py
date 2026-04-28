"""Fast local text moderation rules for demo and fallback scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple


Rule = Tuple[str, Sequence[str], float]

RULES: Sequence[Rule] = (
    (
        "spam",
        (
            "free nitro",
            "airdrop",
            "giveaway winner",
            "click this link",
            "limited time offer",
        ),
        0.5,
    ),
    (
        "scam",
        (
            "verify your wallet",
            "seed phrase",
            "account recovery form",
            "password reset prize",
        ),
        0.65,
    ),
    (
        "harassment",
        (
            "go harm yourself",
            "targeted harassment",
            "dox this user",
        ),
        0.72,
    ),
    (
        "adult_content",
        (
            "nsfw",
            "explicit image",
            "adult server",
        ),
        0.6,
    ),
)

URL_RE = re.compile(r"https?://|discord\.gg/|bit\.ly/|tinyurl\.com/", re.I)
MENTION_RE = re.compile(r"(@everyone|@here|<@!?\d+>)", re.I)


@dataclass(frozen=True)
class TextAnalysis:
    score: float
    category: str
    reason: str


def analyze_text(content: str) -> TextAnalysis:
    """Score a message using deterministic, low-latency rules."""

    normalized = " ".join((content or "").lower().split())
    if not normalized:
        return TextAnalysis(0.0, "clean", "empty or whitespace-only message")

    matched: List[Tuple[str, str, float]] = []
    for category, phrases, weight in RULES:
        for phrase in phrases:
            if phrase in normalized:
                matched.append((category, phrase, weight))

    score = sum(weight for _, _, weight in matched)
    if URL_RE.search(content):
        score += 0.18
        matched.append(("link", "external invite or shortened URL", 0.18))
    if MENTION_RE.search(content) and len(content) > 80:
        score += 0.12
        matched.append(("mass_mention", "mention-heavy long message", 0.12))
    if _has_repeated_char_spam(content):
        score += 0.1
        matched.append(("spam", "repeated character spam", 0.1))

    if not matched:
        return TextAnalysis(0.05, "clean", "no moderation rules matched")

    dominant = max(matched, key=lambda item: item[2])[0]
    phrases = _format_matches(match[1] for match in matched)
    return TextAnalysis(min(score, 0.99), dominant, f"matched {phrases}")


def _has_repeated_char_spam(content: str) -> bool:
    if len(content) < 24:
        return False
    return bool(re.search(r"(.)\1{7,}", content.lower()))


def _format_matches(matches: Iterable[str]) -> str:
    unique = []
    for match in matches:
        if match not in unique:
            unique.append(match)
    return ", ".join(unique[:4])

