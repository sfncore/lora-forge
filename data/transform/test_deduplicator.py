"""Unit tests for deduplicator.py covering content hashing and duplicate removal."""

import hashlib
import pytest
from data.transform.deduplicator import deduplicate, content_hash


class TestDeduplicator:
    def test_content_hash_same_gpt_responses(self):
        conv1 = [
            {"from": "human", "value": "Hello"},
            {"from": "gpt", "value": "Hi there! How can I help?"},
            {"from": "human", "value": "What's the weather?"},
            {"from": "gpt", "value": "I don't have access to weather data."}
        ]
        conv2 = [
            {"from": "human", "value": "Greetings"},
            {"from": "gpt", "value": "Hi there! How can I help?"},
            {"from": "human", "value": "Tell me about weather"},
            {"from": "gpt", "value": "I don't have access to weather data."}
        ]
        assert content_hash(conv1) == content_hash(conv2)

    def test_content_hash_different_gpt_responses(self):
        conv1 = [
            {"from": "gpt", "value": "Response A"}
        ]
        conv2 = [
            {"from": "gpt", "value": "Response B"}
        ]
        assert content_hash(conv1) != content_hash(conv2)

    def test_content_hash_only_gpt_messages_considered(self):
        conv1 = [
            {"from": "human", "value": "Different user message 1"},
            {"from": "gpt", "value": "Same assistant response"},
            {"from": "human", "value": "Another different user message"}
        ]
        conv2 = [
            {"from": "human", "value": "Completely different user input"},
            {"from": "gpt", "value": "Same assistant response"},
            {"from": "human", "value": "Yet another user message"}
        ]
        assert content_hash(conv1) == content_hash(conv2)

    def test_content_hash_no_gpt_messages(self):
        conv = [
            {"from": "human", "value": "User only conversation"}
        ]
        hash_val = content_hash(conv)
        assert hash_val == hashlib.sha256("".encode("utf-8")).hexdigest()[:16]

    def test_content_hash_empty_conversation(self):
        conv = []
        hash_val = content_hash(conv)
        assert hash_val == hashlib.sha256("".encode("utf-8")).hexdigest()[:16]

    def test_deduplicate_identical_samples(self):
        samples = [
            {"conversations": [{"from": "gpt", "value": "Same response"}]},
            {"conversations": [{"from": "gpt", "value": "Same response"}]},
            {"conversations": [{"from": "gpt", "value": "Same response"}]}
        ]
        deduped = deduplicate(samples)
        assert len(deduped) == 1
        assert deduped[0] == samples[0]

    def test_deduplicate_different_samples(self):
        samples = [
            {"conversations": [{"from": "gpt", "value": "Response A"}]},
            {"conversations": [{"from": "gpt", "value": "Response B"}]},
            {"conversations": [{"from": "gpt", "value": "Response C"}]}
        ]
        deduped = deduplicate(samples)
        assert len(deduped) == 3

    def test_deduplicate_mixed_samples(self):
        samples = [
            {"conversations": [{"from": "gpt", "value": "Response A"}]},
            {"conversations": [{"from": "gpt", "value": "Response B"}]},
            {"conversations": [{"from": "gpt", "value": "Response A"}]},  # Duplicate of first
            {"conversations": [{"from": "gpt", "value": "Response C"}]},
            {"conversations": [{"from": "gpt", "value": "Response B"}]}   # Duplicate of second
        ]
        deduped = deduplicate(samples)
        assert len(deduped) == 3
        # Should keep first occurrence of each unique hash
        assert deduped[0]["conversations"][0]["value"] == "Response A"
        assert deduped[1]["conversations"][0]["value"] == "Response B"  
        assert deduped[2]["conversations"][0]["value"] == "Response C"

    def test_deduplicate_preserves_non_conversation_data(self):
        samples = [
            {
                "conversations": [{"from": "gpt", "value": "Same response"}],
                "metadata": {"source": "dataset1", "quality": 0.9}
            },
            {
                "conversations": [{"from": "gpt", "value": "Same response"}],
                "metadata": {"source": "dataset2", "quality": 0.7}  # Different metadata
            },
            {
                "conversations": [{"from": "gpt", "value": "Different response"}],
                "metadata": {"source": "dataset3", "quality": 0.8}
            }
        ]
        deduped = deduplicate(samples)
        assert len(deduped) == 2
        # Should keep the first sample with "Same response" including its metadata
        assert deduped[0]["metadata"]["source"] == "dataset1"
        assert deduped[1]["conversations"][0]["value"] == "Different response"

    def test_deduplicate_empty_input(self):
        samples = []
        deduped = deduplicate(samples)
        assert len(deduped) == 0

    def test_deduplicate_single_sample(self):
        samples = [{"conversations": [{"from": "gpt", "value": "Only one"}]}]
        deduped = deduplicate(samples)
        assert len(deduped) == 1
        assert deduped[0] == samples[0]

    def test_hash_consistency(self):
        conv = [
            {"from": "human", "value": "Test"},
            {"from": "gpt", "value": "Response"},
            {"from": "human", "value": "Follow up"},
            {"from": "gpt", "value": "Final response"}
        ]
        hash1 = content_hash(conv)
        hash2 = content_hash(conv)
        assert hash1 == hash2

    def test_hash_order_dependent(self):
        conv1 = [
            {"from": "gpt", "value": "First"},
            {"from": "gpt", "value": "Second"}
        ]
        conv2 = [
            {"from": "gpt", "value": "Second"},
            {"from": "gpt", "value": "First"}
        ]
        assert content_hash(conv1) != content_hash(conv2)