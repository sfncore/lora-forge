"""Unit tests for tool_normalizer.py covering truncation, cleaning, and normalization."""

import pytest
from data.transform.tool_normalizer import (
    truncate_tool_result,
    clean_tool_result,
    normalize_turn_content,
    DEFAULT_MAX_RESULT_CHARS
)


class TestToolNormalizer:
    def test_truncate_short_result_unchanged(self):
        content = "Short result"
        assert truncate_tool_result(content, max_chars=100) == content

    def test_truncate_exact_length_unchanged(self):
        content = "A" * 100
        assert truncate_tool_result(content, max_chars=100) == content

    def test_truncate_long_result(self):
        content = "A" * 3000
        result = truncate_tool_result(content, max_chars=1000)
        assert len(result) <= 1020  # Allow some buffer for truncation marker
        assert "... [truncated] ..." in result
        assert result.startswith("A" * 600)  # 60% of 1000 = 600
        assert result.endswith("A" * 380)   # Remaining ~40% minus marker length

    def test_truncate_with_zero_max_chars(self):
        content = "Some content"
        result = truncate_tool_result(content, max_chars=0)
        assert result == "\n... [truncated] ...\n"

    def test_clean_noise_patterns_removed(self):
        content = """Shell cwd was reset to /home
WARNING: This binary was built with
Actual useful output here"""
        cleaned = clean_tool_result(content)
        assert "Shell cwd" not in cleaned
        assert "WARNING: This binary" not in cleaned
        assert "Actual useful output here" in cleaned

    def test_clean_empty_result_after_noise_removal(self):
        content = "Shell cwd was reset to /home\nWARNING: This binary was built with"
        cleaned = clean_tool_result(content)
        assert cleaned == ""

    def test_clean_no_noise_preserved(self):
        content = "This is clean output with no noise patterns"
        assert clean_tool_result(content) == content

    def test_normalize_single_tool_result(self):
        content = """Regular text
<tool_result tool_use_id="t1">
Shell cwd was reset to /home
""" + "X" * 3000 + """
</tool_result>
More text"""
        normalized = normalize_turn_content(content, max_result_chars=1000)
        assert "Shell cwd" not in normalized
        assert "... [truncated] ..." in normalized
        assert "<tool_result tool_use_id=\"t1\">" in normalized
        assert "</tool_result>" in normalized

    def test_normalize_multiple_tool_results(self):
        content = """Start
<tool_result tool_use_id="t1">
""" + "A" * 2500 + """
</tool_result>
Middle
<tool_result tool_use_id="t2">
Shell cwd was reset to /home
""" + "B" * 2500 + """
</tool_result>
End"""
        normalized = normalize_turn_content(content, max_result_chars=1000)
        assert normalized.count("<tool_result") == 2
        assert normalized.count("</tool_result>") == 2
        assert "Shell cwd" not in normalized
        assert normalized.count("... [truncated] ...") == 2

    def test_normalize_no_tool_results_unchanged(self):
        content = "This content has no tool results at all"
        assert normalize_turn_content(content) == content

    def test_normalize_empty_tool_result(self):
        content = "Text\n<tool_result tool_use_id=\"t1\">\n</tool_result>\nMore text"
        normalized = normalize_turn_content(content)
        assert normalized == content  # Should remain unchanged

    def test_default_max_chars_used(self):
        content = "A" * (DEFAULT_MAX_RESULT_CHARS + 100)
        result = truncate_tool_result(content)
        assert len(result) <= DEFAULT_MAX_RESULT_CHARS + 20