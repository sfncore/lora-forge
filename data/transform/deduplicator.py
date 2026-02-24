"""Deduplicate training samples based on content hashing.

Strategy: hash the assistant responses (not user prompts, which are often
templated) and remove near-duplicates. Many sessions start identically
(hook check, mail check) — these should be deduplicated.
"""

from __future__ import annotations

import hashlib


def content_hash(conversations: list[dict]) -> str:
    """Generate a hash of the assistant (gpt) responses in a conversation.

    Only hashes gpt messages to avoid deduplicating based on identical
    user prompts (which are often templated in Gas Town).
    """
    gpt_parts = []
    for msg in conversations:
        if msg.get("from") == "gpt":
            gpt_parts.append(msg.get("value", ""))

    content = "\n---\n".join(gpt_parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def deduplicate(samples: list[dict]) -> list[dict]:
    """Remove duplicate samples based on assistant content hash.

    Keeps the first occurrence of each unique hash.
    Returns the deduplicated list and count of removed duplicates.
    """
    seen: set[str] = set()
    unique: list[dict] = []

    for sample in samples:
        conversations = sample.get("conversations", [])
        h = content_hash(conversations)

        if h not in seen:
            seen.add(h)
            unique.append(sample)

    return unique
