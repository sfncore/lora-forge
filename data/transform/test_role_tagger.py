"""Unit tests for role_tagger.py covering path-based and content-based role detection."""

import pytest
from pathlib import Path
from data.transform.role_tagger import tag_role, role_from_path, role_from_content


class TestRoleTagger:
    def test_mayor_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-mayor/session.jsonl")
        assert tag_role(path) == "mayor"
        assert role_from_path(path) == "mayor"

    def test_deacon_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-deacon/session.jsonl")
        assert tag_role(path) == "deacon"
        assert role_from_path(path) == "deacon"

    def test_boot_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-deacon-dogs-boot/session.jsonl")
        assert tag_role(path) == "boot"
        assert role_from_path(path) == "boot"

    def test_witness_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-rig-witness/session.jsonl")
        assert tag_role(path) == "witness"
        assert role_from_path(path) == "witness"

    def test_refinery_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-rig-refinery-rig/session.jsonl")
        assert tag_role(path) == "refinery"
        assert role_from_path(path) == "refinery"

    def test_polecat_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-rig-polecats-furiosa-rig/session.jsonl")
        assert tag_role(path) == "polecat"
        assert role_from_path(path) == "polecat"

    def test_crew_path(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-rig-crew-dev-rig/session.jsonl")
        assert tag_role(path) == "crew"
        assert role_from_path(path) == "crew"

    def test_unknown_path(self):
        path = Path("/home/ubuntu/gt/-unknown/session.jsonl")
        assert tag_role(path) == "unknown"
        assert role_from_path(path) is None

    def test_content_based_detection(self):
        content = "[GAS TOWN] mayor <- human"
        assert role_from_content(content) == "mayor"

    def test_content_based_detection_case_insensitive(self):
        content = "[GAS TOWN] MAYOR <- human"
        assert role_from_content(content) == "mayor"

    def test_content_based_detection_invalid_role(self):
        content = "[GAS TOWN] invalid_role <- human"
        assert role_from_content(content) is None

    def test_content_based_detection_no_match(self):
        content = "This is just regular content without role info"
        assert role_from_content(content) is None

    def test_fallback_to_content_when_path_unknown(self):
        path = Path("/home/ubuntu/gt/-unknown/session.jsonl")
        content = "[GAS TOWN] polecat <- human"
        assert tag_role(path, content) == "polecat"

    def test_path_takes_precedence_over_content(self):
        path = Path("/home/ubuntu/gt/-home-ubuntu-gt-mayor/session.jsonl")
        content = "[GAS TOWN] polecat <- human"
        assert tag_role(path, content) == "mayor"