"""Unit tests for session extraction pipeline."""

import json
from pathlib import Path
import pytest
from data.extract.sessions import (
    extract_session, discover_sessions, _load_records,
    _extract_user_turn, _extract_assistant_turn, _format_tool_call,
)

class TestLoadRecords:
    def test_valid_jsonl(self, tmp_path: Path):
        jsonl_file = tmp_path / "valid.jsonl"
        records = [{"type": "user"}, {"type": "assistant"}]
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records))
        assert len(_load_records(jsonl_file)) == 2

    def test_malformed_skipped(self, tmp_path: Path):
        jsonl_file = tmp_path / "mixed.jsonl"
        lines = ['{"type": "user"}', "not json", '{"type": "assistant"}']
        jsonl_file.write_text("\n".join(lines))
        assert len(_load_records(jsonl_file)) == 2

    def test_empty_file(self, tmp_path: Path):
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("")
        assert len(_load_records(jsonl_file)) == 0

class TestExtractUserTurn:
    def test_string_content(self):
        record = {"type": "user", "uuid": "u1", "message": {"content": "Check hook"}}
        turn = _extract_user_turn(record)
        assert turn is not None and turn.content == "Check hook"

    def test_empty_returns_none(self):
        record = {"type": "user", "message": {"content": "   "}}
        assert _extract_user_turn(record) is None

    def test_tool_result(self):
        record = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "out", "is_error": False}]}}
        turn = _extract_user_turn(record)
        assert turn is not None and len(turn.tool_results) == 1

class TestExtractAssistantTurn:
    def test_text_only(self):
        records = [{"type": "assistant", "requestId": "r1", "message": {"content": [{"type": "text", "text": "OK"}]}}]
        turn = _extract_assistant_turn(records)
        assert turn is not None and turn.content == "OK"

    def test_tool_use(self):
        records = [{"type": "assistant", "requestId": "r1", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}}]}}]
        turn = _extract_assistant_turn(records)
        assert len(turn.tool_calls) == 1 and turn.tool_calls[0]["name"] == "bash"

    def test_thinking_skipped(self):
        records = [{"type": "assistant", "requestId": "r1", "message": {"content": [{"type": "thinking", "text": "hmm"}, {"type": "text", "text": "OK"}]}}]
        turn = _extract_assistant_turn(records)
        assert "hmm" not in turn.content

    def test_multipart(self):
        records = [
            {"type": "assistant", "requestId": "r1", "message": {"content": [{"type": "text", "text": "A "}]}},
            {"type": "assistant", "requestId": "r1", "message": {"content": [{"type": "text", "text": "B"}]}},
        ]
        turn = _extract_assistant_turn(records)
        assert "A" in turn.content and "B" in turn.content

    def test_empty_returns_none(self):
        records = [{"type": "assistant", "requestId": "r1", "message": {"content": []}}]
        assert _extract_assistant_turn(records) is None

class TestFormatToolCall:
    def test_simple(self):
        tool_call = {"name": "bash", "input": {"command": "ls"}}
        formatted = _format_tool_call(tool_call)
        assert '<tool_call name="bash">' in formatted

class TestExtractSession:
    def test_basic(self, tmp_path: Path):
        jsonl_file = tmp_path / "session.jsonl"
        records = [
            {"type": "user", "sessionId": "s1", "uuid": "u1", "message": {"content": "Hi"}},
            {"type": "assistant", "sessionId": "s1", "uuid": "a1", "requestId": "r1", "message": {"content": [{"type": "text", "text": "Hello"}]}},
        ]
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records))
        session = extract_session(jsonl_file)
        assert session is not None and len(session.turns) == 2

    def test_empty_returns_none(self, tmp_path: Path):
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text('{"type": "progress"}\n')
        assert extract_session(jsonl_file) is None

class TestDiscoverSessions:
    def test_discover(self, tmp_path: Path):
        proj = tmp_path / "-home-ubuntu-gt-mayor"
        proj.mkdir()
        session = proj / "session.jsonl"
        session.write_text('{"type": "user"}\n')
        sessions = discover_sessions(tmp_path)
        assert len(sessions) == 1

    def test_skip_index(self, tmp_path: Path):
        proj = tmp_path / "-home-ubuntu-gt-mayor"
        proj.mkdir()
        (proj / "sessions-index.jsonl").write_text("{}\n")
        assert len(discover_sessions(tmp_path)) == 0
