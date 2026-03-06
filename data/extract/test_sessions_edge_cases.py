"""Edge case tests for session extraction pipeline."""

import json
from pathlib import Path
import pytest
from data.extract.sessions import (
    extract_session, discover_sessions, _load_records,
    _extract_user_turn, _extract_assistant_turn, _format_tool_call,
    _detect_runtime_type, _classify_tool_call
)


class TestDetectRuntimeType:
    def test_no_mcp_servers(self):
        records = [{"type": "user"}, {"type": "assistant"}]
        runtime_type, servers = _detect_runtime_type(records)
        assert runtime_type == "claudecode"
        assert servers == []

    def test_prism_nvim_server(self):
        records = [
            {"type": "progress", "data": {"type": "mcp_progress", "serverName": "prism-nvim"}},
            {"type": "user"}
        ]
        runtime_type, servers = _detect_runtime_type(records)
        assert runtime_type == "claudecode-nvim"
        assert servers == ["prism-nvim"]

    def test_other_mcp_server(self):
        records = [
            {"type": "progress", "data": {"type": "mcp_progress", "serverName": "other-server"}},
            {"type": "user"}
        ]
        runtime_type, servers = _detect_runtime_type(records)
        assert runtime_type == "claudecode-mcp"
        assert servers == ["other-server"]

    def test_multiple_mcp_servers_including_prism_nvim(self):
        records = [
            {"type": "progress", "data": {"type": "mcp_progress", "serverName": "other-server"}},
            {"type": "progress", "data": {"type": "mcp_progress", "serverName": "prism-nvim"}},
            {"type": "user"}
        ]
        runtime_type, servers = _detect_runtime_type(records)
        assert runtime_type == "claudecode-nvim"
        assert servers == ["other-server", "prism-nvim"]


class TestClassifyToolCall:
    def test_mcp_tool_call(self):
        block = {"id": "t1", "name": "mcp__prism-nvim__edit_buffer", "input": {"path": "test.py"}}
        result = _classify_tool_call(block)
        assert result["source"] == "mcp"
        assert result["mcp_server"] == "prism-nvim"
        assert result["name"] == "mcp__prism-nvim__edit_buffer"

    def test_standard_tool_call(self):
        block = {"id": "t1", "name": "bash", "input": {"command": "ls"}}
        result = _classify_tool_call(block)
        assert result["source"] == "standard"
        assert result["mcp_server"] == ""
        assert result["name"] == "bash"

    def test_mcp_tool_call_with_insufficient_parts(self):
        block = {"id": "t1", "name": "mcp__", "input": {}}
        result = _classify_tool_call(block)
        assert result["source"] == "mcp"
        assert result["mcp_server"] == ""


class TestExtractUserTurn:
    def test_user_with_text_and_tool_results(self):
        record = {
            "type": "user",
            "uuid": "u1",
            "message": {
                "content": [
                    {"type": "text", "text": "Here's the result"},
                    {"type": "tool_result", "tool_use_id": "t1", "content": "output", "is_error": False}
                ]
            }
        }
        turn = _extract_user_turn(record)
        assert turn is not None
        assert "Here's the result" in turn.content
        assert len(turn.tool_results) == 1
        assert '<tool_result tool_use_id="t1">' in turn.content

    def test_user_with_only_tool_results(self):
        record = {
            "type": "user",
            "uuid": "u1",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "output", "is_error": False}
                ]
            }
        }
        turn = _extract_user_turn(record)
        assert turn is not None
        assert len(turn.tool_results) == 1
        assert '<tool_result tool_use_id="t1">' in turn.content

    def test_user_with_non_dict_content_blocks(self):
        record = {
            "type": "user",
            "uuid": "u1",
            "message": {
                "content": [
                    "invalid_block",
                    {"type": "text", "text": "valid text"}
                ]
            }
        }
        turn = _extract_user_turn(record)
        assert turn is not None
        assert turn.content == "valid text"


class TestExtractAssistantTurn:
    def test_assistant_with_thinking_and_text(self):
        records = [{
            "type": "assistant",
            "requestId": "r1",
            "message": {
                "content": [
                    {"type": "thinking", "text": "Internal reasoning"},
                    {"type": "text", "text": "Final response"}
                ]
            }
        }]
        turn = _extract_assistant_turn(records)
        assert turn is not None
        assert "Internal reasoning" not in turn.content
        assert "Final response" in turn.content

    def test_assistant_with_tool_use_and_text(self):
        records = [{
            "type": "assistant",
            "requestId": "r1",
            "message": {
                "content": [
                    {"type": "text", "text": "I'll run a command"},
                    {"type": "tool_use", "id": "t1", "name": "bash", "input": {"command": "ls"}}
                ]
            }
        }]
        turn = _extract_assistant_turn(records)
        assert turn is not None
        assert "I'll run a command" in turn.content
        assert len(turn.tool_calls) == 1
        assert '<tool_call name="bash"' in turn.content

    def test_assistant_with_invalid_content_blocks(self):
        records = [{
            "type": "assistant",
            "requestId": "r1",
            "message": {
                "content": [
                    "invalid_block",
                    {"type": "text", "text": "valid text"}
                ]
            }
        }]
        turn = _extract_assistant_turn(records)
        assert turn is not None
        assert turn.content == "valid text"

    def test_assistant_with_empty_tool_use_input(self):
        records = [{
            "type": "assistant",
            "requestId": "r1",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "bash", "input": {}}
                ]
            }
        }]
        turn = _extract_assistant_turn(records)
        assert turn is not None
        assert len(turn.tool_calls) == 1


class TestExtractSession:
    def test_session_with_request_id_fallback_to_message_id(self, tmp_path: Path):
        jsonl_file = tmp_path / "session.jsonl"
        records = [
            {"type": "user", "sessionId": "s1", "uuid": "u1", "message": {"content": "Hi"}},
            {"type": "assistant", "sessionId": "s1", "uuid": "a1", "message": {"id": "msg1", "content": [{"type": "text", "text": "Hello"}]}},
        ]
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records))
        session = extract_session(jsonl_file)
        assert session is not None and len(session.turns) == 2

    def test_session_with_duplicate_request_ids(self, tmp_path: Path):
        jsonl_file = tmp_path / "session.jsonl"
        records = [
            {"type": "user", "sessionId": "s1", "uuid": "u1", "message": {"content": "Hi"}},
            {"type": "assistant", "sessionId": "s1", "uuid": "a1", "requestId": "r1", "message": {"content": [{"type": "text", "text": "Part 1"}]}},
            {"type": "assistant", "sessionId": "s1", "uuid": "a2", "requestId": "r1", "message": {"content": [{"type": "text", "text": "Part 2"}]}},
        ]
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records))
        session = extract_session(jsonl_file)
        assert session is not None and len(session.turns) == 2
        assert "Part 1" in session.turns[1].content
        assert "Part 2" in session.turns[1].content

    def test_session_with_malformed_json_records(self, tmp_path: Path):
        jsonl_file = tmp_path / "session.jsonl"
        content = '{"type": "user", "message": {"content": "Hi"}}\n' + \
                  'invalid json line\n' + \
                  '{"type": "assistant", "requestId": "r1", "message": {"content": [{"type": "text", "text": "Hello"}]}}'
        jsonl_file.write_text(content)
        session = extract_session(jsonl_file)
        assert session is not None and len(session.turns) == 2

    def test_session_with_non_conversation_records(self, tmp_path: Path):
        jsonl_file = tmp_path / "session.jsonl"
        records = [
            {"type": "file-history-snapshot", "data": "snapshot"},
            {"type": "user", "sessionId": "s1", "uuid": "u1", "message": {"content": "Hi"}},
            {"type": "progress", "data": {"type": "mcp_progress", "serverName": "prism-nvim"}},
            {"type": "summary", "data": "summary"},
            {"type": "assistant", "sessionId": "s1", "uuid": "a1", "requestId": "r1", "message": {"content": [{"type": "text", "text": "Hello"}]}},
        ]
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records))
        session = extract_session(jsonl_file)
        assert session is not None and len(session.turns) == 2
        assert session.runtime_type == "claudecode-nvim"
        assert "prism-nvim" in session.mcp_servers

    def test_session_without_session_id_or_cwd(self, tmp_path: Path):
        jsonl_file = tmp_path / "session.jsonl"
        records = [
            {"type": "user", "uuid": "u1", "message": {"content": "Hi"}},
            {"type": "assistant", "uuid": "a1", "requestId": "r1", "message": {"content": [{"type": "text", "text": "Hello"}]}},
        ]
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records))
        session = extract_session(jsonl_file)
        assert session is not None
        assert session.session_id == ""
        assert session.cwd == ""


class TestFormatToolCall:
    def test_mcp_tool_call_formatting(self):
        tool_call = {
            "name": "mcp__prism-nvim__edit_buffer",
            "input": {"path": "test.py", "content": "print('hello')"},
            "source": "mcp",
            "mcp_server": "prism-nvim"
        }
        formatted = _format_tool_call(tool_call)
        assert '<tool_call name="mcp__prism-nvim__edit_buffer" source="mcp" mcp_server="prism-nvim">' in formatted
        assert '"path":"test.py","content":"print(\'hello\')"' in formatted

    def test_standard_tool_call_formatting(self):
        tool_call = {
            "name": "bash",
            "input": {"command": "ls -la"},
            "source": "standard",
            "mcp_server": ""
        }
        formatted = _format_tool_call(tool_call)
        assert '<tool_call name="bash" source="standard">' in formatted
        assert '"command":"ls -la"' in formatted

    def test_tool_call_with_special_characters_in_input(self):
        tool_call = {
            "name": "bash",
            "input": {"command": 'echo "hello world" && ls'},
            "source": "standard",
            "mcp_server": ""
        }
        formatted = _format_tool_call(tool_call)
        assert '"command":"echo \\"hello world\\" && ls"' in formatted