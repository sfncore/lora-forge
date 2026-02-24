"""Scrub secrets and tokens from training data.

Session transcripts often contain real tokens (GitHub OAuth, Google OAuth,
API keys, etc.) that must be removed before training or pushing to repos.
"""

from __future__ import annotations

import re

# Patterns that match common secret formats.
# Each tuple: (pattern, replacement, description)
_SECRET_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # GitHub tokens
    (re.compile(r"gho_[A-Za-z0-9]{36,}"), "[GITHUB_OAUTH_REDACTED]", "GitHub OAuth"),
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "[GITHUB_PAT_REDACTED]", "GitHub PAT"),
    (re.compile(r"ghs_[A-Za-z0-9]{36,}"), "[GITHUB_SECRET_REDACTED]", "GitHub App Secret"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{40,}"), "[GITHUB_PAT_REDACTED]", "GitHub Fine-grained PAT"),

    # Google tokens
    (re.compile(r"ya29\.[A-Za-z0-9_-]{50,}"), "[GOOGLE_ACCESS_TOKEN_REDACTED]", "Google Access Token"),
    (re.compile(r"1//[A-Za-z0-9_-]{40,}"), "[GOOGLE_REFRESH_TOKEN_REDACTED]", "Google Refresh Token"),

    # Generic API keys (long hex or base64 strings in key-value context)
    (re.compile(r'(?:api[_-]?key|apikey|secret|token|password|credential)[\s:=]+[\'\"]?([A-Za-z0-9+/=_-]{32,})[\'\"]?', re.IGNORECASE),
     lambda m: m.group(0).replace(m.group(1), "[API_KEY_REDACTED]"), "Generic API key"),

    # AWS keys
    (re.compile(r"AKIA[A-Z0-9]{16}"), "[AWS_KEY_REDACTED]", "AWS Access Key"),
    (re.compile(r'(?:aws_secret_access_key|secret_key)[\s:=]+[\'\"]?([A-Za-z0-9+/=]{40})[\'\"]?', re.IGNORECASE),
     lambda m: m.group(0).replace(m.group(1), "[AWS_SECRET_REDACTED]"), "AWS Secret Key"),

    # Anthropic keys
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{40,}"), "[ANTHROPIC_KEY_REDACTED]", "Anthropic API Key"),

    # OpenAI keys
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "[OPENAI_KEY_REDACTED]", "OpenAI API Key"),

    # SSH private keys
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", re.DOTALL),
     "[PRIVATE_KEY_REDACTED]", "Private Key"),

    # Bearer tokens in headers
    (re.compile(r'(?:Bearer|Authorization)[\s:]+[\'\"]?([A-Za-z0-9._+/=-]{30,})[\'\"]?', re.IGNORECASE),
     lambda m: m.group(0).replace(m.group(1), "[BEARER_TOKEN_REDACTED]"), "Bearer Token"),

    # Kimi API keys
    (re.compile(r'(?:KIMI_API_KEY|kimi_api_key)[\s:=]+[\'\"]?([A-Za-z0-9_-]{20,})[\'\"]?', re.IGNORECASE),
     lambda m: m.group(0).replace(m.group(1), "[KIMI_KEY_REDACTED]"), "Kimi API Key"),

    # GH_TOKEN env var values
    (re.compile(r'GH_TOKEN[=\s]+([A-Za-z0-9_]{30,})'),
     lambda m: m.group(0).replace(m.group(1), "[GH_TOKEN_REDACTED]"), "GH_TOKEN value"),
]


def scrub_secrets(text: str) -> tuple[str, int]:
    """Scrub all detected secrets from text.

    Returns (scrubbed_text, count_of_secrets_found).
    """
    total_found = 0

    for pattern, replacement, _desc in _SECRET_PATTERNS:
        if callable(replacement):
            text, count = pattern.subn(replacement, text)
        else:
            text, count = pattern.subn(replacement, text)
        total_found += count

    return text, total_found


def scrub_sample(sample: dict) -> tuple[dict, int]:
    """Scrub secrets from all conversation messages in a training sample.

    Returns (scrubbed_sample, total_secrets_found).
    """
    total = 0
    conversations = sample.get("conversations", [])

    for msg in conversations:
        value = msg.get("value", "")
        scrubbed, count = scrub_secrets(value)
        if count > 0:
            msg["value"] = scrubbed
            total += count

    return sample, total
