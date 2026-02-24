"""Map session directory paths to canonical Gas Town roles.

Directory naming convention:
  -home-ubuntu-gt-mayor/             → mayor
  -home-ubuntu-gt-deacon/            → deacon
  -home-ubuntu-gt-deacon-dogs-boot/  → boot (deacon sub-role)
  -home-ubuntu-gt-deacon-dogs-alpha/ → deacon (dog)
  -home-ubuntu-gt-{rig}-witness/     → witness
  -home-ubuntu-gt-{rig}-refinery-rig/ → refinery
  -home-ubuntu-gt-{rig}-crew-{name}-{rig}/ → crew
  -home-ubuntu-gt-{rig}-polecats-{name}-{rig}/ → polecat

Content-based fallback: first user message often contains [GAS TOWN] role <- source.
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical roles in Gas Town.
CANONICAL_ROLES = {"mayor", "deacon", "boot", "witness", "refinery", "polecat", "crew"}

# Patterns to match directory names to roles, ordered by specificity.
_DIR_PATTERNS = [
    (re.compile(r"-deacon-dogs-boot$"), "boot"),
    (re.compile(r"-deacon-dogs-"), "deacon"),
    (re.compile(r"-deacon$"), "deacon"),
    (re.compile(r"-mayor$"), "mayor"),
    (re.compile(r"-witness$"), "witness"),
    (re.compile(r"-refinery-"), "refinery"),
    (re.compile(r"-crew-"), "crew"),
    (re.compile(r"-polecats-"), "polecat"),
]

# Content pattern: [GAS TOWN] role <- source
_CONTENT_PATTERN = re.compile(r"\[GAS TOWN\]\s+(\w+)\s+<-")


def role_from_path(session_path: Path) -> str | None:
    """Extract the Gas Town role from a session file's parent directory name.

    Returns the canonical role string, or None if unrecognized.
    """
    dir_name = session_path.parent.name
    for pattern, role in _DIR_PATTERNS:
        if pattern.search(dir_name):
            return role
    return None


def role_from_content(first_user_content: str) -> str | None:
    """Extract the Gas Town role from the first user message content.

    Looks for patterns like '[GAS TOWN] mayor <- human'.
    """
    match = _CONTENT_PATTERN.search(first_user_content)
    if match:
        role = match.group(1).lower()
        if role in CANONICAL_ROLES:
            return role
    return None


def tag_role(session_path: Path, first_user_content: str = "") -> str:
    """Determine the Gas Town role for a session.

    Tries path-based detection first, falls back to content-based.
    Returns "unknown" if neither method works.
    """
    role = role_from_path(session_path)
    if role:
        return role

    if first_user_content:
        role = role_from_content(first_user_content)
        if role:
            return role

    return "unknown"
