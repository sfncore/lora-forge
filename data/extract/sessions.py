"""Extract training-relevant turns from Claude session JSONL files.

Each session JSONL file contains records of types:
  - file-history-snapshot: skip
  - progress: scanned for mcp_progress events (runtime detection), otherwise skip
  - summary: skip
  - user: training data — content is str (human) or list[tool_result]
  - assistant: training data — content is list of {thinking, text, tool_use} blocks

A single assistant response may span MULTIPLE records sharing the same requestId.
We group by requestId to reconstruct complete responses.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Record types that contain training-relevant data.
CONVERSATION_TYPES = {"user", "assistant"}


@dataclass
class Turn:
    """A single conversation turn (user or assistant)."""

    role: str  # "user" or "assistant"
    content: str  # The textual content
    tool_calls: list[dict] = field(default_factory=list)  # Structured tool_use blocks
    tool_results: list[dict] = field(default_factory=list)  # Structured tool_result blocks
    timestamp: str = ""
    uuid: str = ""


@dataclass
class ExtractedSession:
    """A fully extracted session with metadata."""

    session_id: str
    source_path: str
    cwd: str = ""
    turns: list[Turn] = field(default_factory=list)
    runtime_type: str = "unknown"  # claudecode, claudecode-nvim, claudecode-mcp
    mcp_servers: list[str] = field(default_factory=list)  # MCP servers used in session
    metadata: dict = field(default_factory=dict)


def _detect_runtime_type(records: list[dict]) -> tuple[str, list[str]]:
    """Detect runtime type from MCP progress events in session records.

    Scans progress records for mcp_progress events and classifies:
      - "claudecode-nvim": prism-nvim MCP server present (Neovim-embedded)
      - "claudecode-mcp": other MCP servers present but not prism-nvim
      - "claudecode": no MCP servers detected (standard CLI)

    Returns:
        (runtime_type, sorted list of unique MCP server names)
    """
    mcp_servers: set[str] = set()

    for rec in records:
        if rec.get("type") != "progress":
            continue
        data = rec.get("data", {})
        if data.get("type") != "mcp_progress":
            continue
        server_name = data.get("serverName", "")
        if server_name:
            mcp_servers.add(server_name)

    servers_list = sorted(mcp_servers)

    if not mcp_servers:
        return "claudecode", servers_list
    if "prism-nvim" in mcp_servers:
        return "claudecode-nvim", servers_list
    return "claudecode-mcp", servers_list


def extract_session(session_path: Path) -> ExtractedSession | None:
    """Extract training-relevant turns from a Claude session JSONL file.

    Returns None if the session contains no usable conversation data.
    """
    records = _load_records(session_path)
    if not records:
        return None

    # Detect runtime type from MCP progress events.
    runtime_type, mcp_servers = _detect_runtime_type(records)

    session_id = ""
    cwd = ""

    # Group assistant records by requestId to reconstruct full responses.
    assistant_groups: dict[str, list[dict]] = defaultdict(list)
    user_records: list[dict] = []
    record_order: list[tuple[str, str, str]] = []  # (type, key, timestamp)

    for rec in records:
        rec_type = rec.get("type")
        if rec_type not in CONVERSATION_TYPES:
            continue

        if not session_id:
            session_id = rec.get("sessionId", "")
        if not cwd:
            cwd = rec.get("cwd", "")

        ts = rec.get("timestamp", "")
        uuid = rec.get("uuid", "")

        if rec_type == "user":
            key = f"user-{uuid}"
            user_records.append(rec)
            record_order.append(("user", key, ts))

        elif rec_type == "assistant":
            request_id = rec.get("requestId", "")
            if not request_id:
                request_id = rec.get("message", {}).get("id", uuid)
            key = f"assistant-{request_id}"
            assistant_groups[key].append(rec)
            # Only record order for first occurrence of this requestId.
            if len(assistant_groups[key]) == 1:
                record_order.append(("assistant", key, ts))

    if not record_order:
        return None

    # Deduplicate and sort by timestamp.
    seen_keys = set()
    unique_order = []
    for item in record_order:
        if item[1] not in seen_keys:
            seen_keys.add(item[1])
            unique_order.append(item)

    # Build turns in conversation order.
    turns: list[Turn] = []
    user_by_key = {f"user-{r.get('uuid', '')}": r for r in user_records}

    for rec_type, key, ts in unique_order:
        if rec_type == "user":
            rec = user_by_key.get(key)
            if rec:
                turn = _extract_user_turn(rec)
                if turn:
                    turns.append(turn)

        elif rec_type == "assistant":
            group = assistant_groups.get(key, [])
            if group:
                turn = _extract_assistant_turn(group)
                if turn:
                    turns.append(turn)

    if not turns:
        return None

    return ExtractedSession(
        session_id=session_id,
        source_path=str(session_path),
        cwd=cwd,
        turns=turns,
        runtime_type=runtime_type,
        mcp_servers=mcp_servers,
        metadata={
            "total_records": len(records),
            "conversation_records": len(user_records) + sum(len(g) for g in assistant_groups.values()),
            "runtime_type": runtime_type,
            "mcp_servers": mcp_servers,
        },
    )


def _load_records(path: Path) -> list[dict]:
    """Load all JSON records from a JSONL file, skipping malformed lines."""
    records = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug("Skipping malformed JSON at %s:%d", path, line_num)
    return records


def _extract_user_turn(rec: dict) -> Turn | None:
    """Extract a user turn from a user record.

    User content can be:
      - A string (human-typed message)
      - A list of tool_result dicts (responses to tool calls)
    """
    msg = rec.get("message", {})
    content = msg.get("content")
    ts = rec.get("timestamp", "")
    uuid = rec.get("uuid", "")

    if isinstance(content, str):
        if not content.strip():
            return None
        return Turn(role="user", content=content, timestamp=ts, uuid=uuid)

    if isinstance(content, list):
        # Tool results from the user side.
        tool_results = []
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "tool_result":
                    result_content = block.get("content", "")
                    tool_results.append({
                        "tool_use_id": block.get("tool_use_id", ""),
                        "content": result_content if isinstance(result_content, str) else str(result_content),
                        "is_error": block.get("is_error", False),
                    })
                elif block_type == "text":
                    text_parts.append(block.get("text", ""))

        if not tool_results and not text_parts:
            return None

        # Format tool results as content.
        parts = list(text_parts)
        for tr in tool_results:
            parts.append(f'<tool_result tool_use_id="{tr["tool_use_id"]}">\n{tr["content"]}\n</tool_result>')

        return Turn(
            role="user",
            content="\n".join(parts),
            tool_results=tool_results,
            timestamp=ts,
            uuid=uuid,
        )

    return None


def _extract_assistant_turn(records: list[dict]) -> Turn | None:
    """Extract an assistant turn from grouped assistant records.

    Multiple records may share the same requestId, each containing
    different content blocks (thinking, text, tool_use).
    """
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    ts = ""
    uuid = ""

    for rec in records:
        if not ts:
            ts = rec.get("timestamp", "")
        if not uuid:
            uuid = rec.get("uuid", "")

        msg = rec.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type", "")

            if block_type == "text":
                text = block.get("text", "").strip()
                if text:
                    text_parts.append(text)

            elif block_type == "tool_use":
                tool_call = _classify_tool_call(block)
                tool_calls.append(tool_call)
                # Format tool call as part of content.
                text_parts.append(_format_tool_call(tool_call))

            elif block_type == "thinking":
                # Skip thinking blocks for v1 — they contain internal reasoning
                # that we don't want to teach the model to reproduce verbatim.
                pass

    if not text_parts:
        return None

    return Turn(
        role="assistant",
        content="\n".join(text_parts),
        tool_calls=tool_calls,
        timestamp=ts,
        uuid=uuid,
    )


def _classify_tool_call(block: dict) -> dict:
    """Extract and classify a tool_use block by source.

    MCP tool names follow the pattern ``mcp__<server>__<tool>``.
    Returns a dict with id, name, input, plus source and mcp_server fields.
    """
    name = block.get("name", "")
    result = {
        "id": block.get("id", ""),
        "name": name,
        "input": block.get("input", {}),
    }

    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        result["source"] = "mcp"
        result["mcp_server"] = parts[1] if len(parts) >= 2 else "unknown"
    else:
        result["source"] = "standard"
        result["mcp_server"] = ""

    return result


def _format_tool_call(tool_call: dict) -> str:
    """Format a tool call as an XML-tagged string for training data."""
    args_json = json.dumps(tool_call.get("input", {}), ensure_ascii=False, separators=(",", ":"))
    name = tool_call.get("name", "unknown")
    source = tool_call.get("source", "standard")
    attrs = f'name="{name}" source="{source}"'
    mcp_server = tool_call.get("mcp_server", "")
    if mcp_server:
        attrs += f' mcp_server="{mcp_server}"'
    return f"<tool_call {attrs}>\n{args_json}\n</tool_call>"


def discover_sessions(base_dir: Path, pattern: str = "-home-ubuntu-gt-*") -> list[Path]:
    """Discover all Claude session JSONL files under the base directory.

    Args:
        base_dir: The .claude/projects/ directory.
        pattern: Glob pattern for project subdirectories. Default matches
                 all Gas Town project directories.

    Returns:
        List of paths to session JSONL files, sorted by modification time (newest first).
    """
    sessions = []
    for project_dir in base_dir.glob(pattern):
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            # Skip files that are clearly not sessions (e.g., sessions-index).
            if jsonl_file.name.startswith("sessions-"):
                continue
            sessions.append(jsonl_file)

    return sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.is_file():
            session = extract_session(path)
            if session:
                print(f"Session: {session.session_id}")
                print(f"Runtime: {session.runtime_type}")
                if session.mcp_servers:
                    print(f"MCP servers: {', '.join(session.mcp_servers)}")
                print(f"Turns: {len(session.turns)}")
                for i, turn in enumerate(session.turns[:5]):
                    preview = turn.content[:100].replace("\n", " ")
                    tools = f" [{len(turn.tool_calls)} tools]" if turn.tool_calls else ""
                    print(f"  {i}: [{turn.role}]{tools} {preview}...")
            else:
                print("No usable data in session")
        elif path.is_dir():
            sessions = discover_sessions(path)
            print(f"Found {len(sessions)} session files")
            for s in sessions[:10]:
                print(f"  {s.name} ({s.stat().st_size // 1024}KB)")
    else:
        # Default: discover all Gas Town sessions.
        base = Path.home() / ".claude" / "projects"
        sessions = discover_sessions(base)
        print(f"Found {len(sessions)} Gas Town session files")
        for s in sessions[:10]:
            size_kb = s.stat().st_size // 1024
            print(f"  {s.parent.name}/{s.name} ({size_kb}KB)")
