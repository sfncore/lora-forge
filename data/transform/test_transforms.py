"""Unit tests for data transformation pipeline."""

import json
from pathlib import Path
import pytest
from data.extract.sessions import Turn
from data.transform.role_tagger import tag_role, role_from_path
from data.transform.tool_normalizer import truncate_tool_result, clean_tool_result, normalize_turn_content
from data.transform.chunker import chunk_turns
from data.transform.quality_filter import assess_turns
from data.transform.deduplicator import deduplicate, content_hash


class TestRoleTagger:
    def test_mayor_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-mayor/session.jsonl")
        assert tag_role(path) == "mayor"

    def test_deacon_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-deacon/session.jsonl")
        assert tag_role(path) == "deacon"

    def test_boot_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-deacon-dogs-boot/session.jsonl")
        assert tag_role(path) == "boot"

    def test_witness_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-rig-witness/session.jsonl")
        assert tag_role(path) == "witness"

    def test_refinery_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-rig-refinery-rig/session.jsonl")
        assert tag_role(path) == "refinery"

    def test_polecat_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-rig-polecats-furiosa-rig/session.jsonl")
        assert tag_role(path) == "polecat"

    def test_crew_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-home-ubuntu-gt-rig-crew-dev-rig/session.jsonl")
        assert tag_role(path) == "crew"

    def test_unknown_path(self):
        path = Path("/home/ubuntu/gt/.claude/projects/-unknown/session.jsonl")
        assert tag_role(path) == "unknown"


class TestToolNormalizer:
    def test_truncate_short(self):
        content = "Short result"
        assert truncate_tool_result(content, max_chars=100) == content

    def test_truncate_long(self):
        content = "A" * 3000
        result = truncate_tool_result(content, max_chars=1000)
        assert len(result) <= 1020
        assert "... [truncated] ..." in result

    def test_clean_noise(self):
        content = "Shell cwd was reset to /home\nActual output"
        cleaned = clean_tool_result(content)
        assert "Shell cwd" not in cleaned
        assert "Actual output" in cleaned

    def test_normalize_turn(self):
        content = "Text\n<tool_result tool_use_id=\"t1\">\n" + "X" * 3000 + "\n</tool_result>"
        normalized = normalize_turn_content(content, max_result_chars=1000)
        assert "... [truncated] ..." in normalized


class TestChunker:
    def test_short_session(self):
        turns = [Turn(role="user", content="Hi"), Turn(role="assistant", content="Hello")]
        chunks = chunk_turns(turns, window_size=16)
        assert len(chunks) == 1

    def test_long_session(self):
        turns = [Turn(role="user" if i % 2 == 0 else "assistant", content=f"Turn {i}") for i in range(20)]
        chunks = chunk_turns(turns, window_size=8, stride=4)
        assert len(chunks) > 1

    def test_chunk_metadata(self):
        turns = [Turn(role="user", content="Hi"), Turn(role="assistant", content="Hello")]
        chunks = chunk_turns(turns)
        assert chunks[0].chunk_index == 0
        assert chunks[0].total_chunks == 1


class TestQualityFilter:
    def test_too_few_turns(self):
        turns = [Turn(role="user", content="Hi")]
        result = assess_turns(turns)
        assert result.keep is False

    def test_substantive(self):
        turns = [
            Turn(role="user", content="Review this code change and tell me if there are any issues with the implementation"),
            Turn(role="assistant", content="Let me analyze the changes carefully.\n\nThe code looks mostly good but I noticed a potential issue with error handling..."),
        ]
        result = assess_turns(turns)
        assert result.keep is True


class TestDeduplicator:
    def test_content_hash(self):
        conv1 = [{"from": "gpt", "value": "Hello"}]
        conv2 = [{"from": "gpt", "value": "Hello"}]
        conv3 = [{"from": "gpt", "value": "Hi"}]
        assert content_hash(conv1) == content_hash(conv2)
        assert content_hash(conv1) != content_hash(conv3)

    def test_deduplicate(self):
        samples = [
            {"conversations": [{"from": "gpt", "value": "Same"}]},
            {"conversations": [{"from": "gpt", "value": "Same"}]},
            {"conversations": [{"from": "gpt", "value": "Different"}]},
        ]
        deduped = deduplicate(samples)
        assert len(deduped) == 2
