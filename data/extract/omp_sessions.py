"""Extract training-relevant turns from omp (oh-my-pi) session JSONL files.

omp session format differs from Claude Code:
  - All conversation records use type: "message" with message.role
  - Roles: "user", "assistant", "toolResult"
  - Assistant tool calls use type: "toolCall" (not "tool_use")
  - Tool results are separate messages with role: "toolResult"
  - Extra record types: "session", "model_change", "thinking_level_change", "custom_message"
  - Messages carry api/provider/model/usage metadata
  - parentId chain instead of requestId grouping

Session directory layout:
  ~/.omp/agent/sessions/{project-dir}/{timestamp}_{session-id}.jsonl
  e.g. -gt-sfgastown-polecats-jade-sfgastown/2026-03-02T06-15-47-386Z_14829964eeafeed9.jsonl
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from data.extract.sessions import ExtractedSession, Turn

logger = logging.getLogger(__name__)

# omp default sessions directory.
OMP_SESSIONS_DIR = Path.home() / ".omp" / "agent" / "sessions"

# Record types that carry conversation data.
_MESSAGE_TYPE = "message"
_CONVERSATION_ROLES = {"user", "assistant", "toolResult"}


def extract_omp_session(session_path: Path) -> ExtractedSession | None:
    """Extract training-relevant turns from an omp session JSONL file.

    Returns None if the session contains no usable conversation data.
    """
    records = _load_records(session_path)
    if not records:
        return None

    session_id = ""
    cwd = ""
    model = ""
    provider = ""
    api = ""
    mcp_servers: set[str] = set()

    # Collect conversation messages in order.
    messages: list[dict] = []

    for rec in records:
        rec_type = rec.get("type", "")

        # Session header — extract metadata.
        if rec_type == "session":
            if not session_id:
                session_id = rec.get("id", "")
            if not cwd:
                cwd = rec.get("cwd", "")
            continue

        # Model changes — track current model.
        if rec_type == "model_change":
            model = rec.get("model", model)
            continue

        # Conversation messages.
        if rec_type == _MESSAGE_TYPE:
            msg = rec.get("message", {})
            role = msg.get("role", "")
            if role in _CONVERSATION_ROLES:
                messages.append(rec)
                # Extract model/provider/api from assistant messages.
                if role == "assistant":
                    msg_api = msg.get("api", "")
                    msg_provider = msg.get("provider", "")
                    msg_model = msg.get("model", "")
                    if msg_api:
                        api = msg_api
                    if msg_provider:
                        provider = msg_provider
                    if msg_model:
                        model = msg_model
                # Track MCP tools used.
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "toolCall":
                            name = block.get("name", "")
                            if name.startswith("mcp_"):
                                parts = name.split("_", 2)
                                if len(parts) >= 2:
                                    mcp_servers.add(parts[1])
            continue

    if not messages:
        return None

    # Build turns by grouping toolResult messages with preceding assistant turns.
    turns = _build_turns(messages)

    if not turns:
        return None

    servers_list = sorted(mcp_servers)
    runtime_type = _classify_runtime(api, provider, model)

    return ExtractedSession(
        session_id=session_id,
        source_path=str(session_path),
        cwd=cwd,
        turns=turns,
        runtime_type=runtime_type,
        mcp_servers=servers_list,
        metadata={
            "total_records": len(records),
            "conversation_records": len(messages),
            "runtime_type": runtime_type,
            "mcp_servers": servers_list,
            "omp_model": model,
            "omp_provider": provider,
            "omp_api": api,
        },
    )


def _build_turns(messages: list[dict]) -> list[Turn]:
    """Build Turn objects from omp message records.

    omp has three message roles:
      - user: human input (content is list of text blocks)
      - assistant: model response (content has text + toolCall blocks)
      - toolResult: tool execution result (separate message, not embedded in user)

    We merge consecutive toolResult messages into a single user turn
    to match the Turn format expected by the downstream pipeline.
    """
    turns: list[Turn] = []
    pending_tool_results: list[dict] = []

    for rec in messages:
        msg = rec.get("message", {})
        role = msg.get("role", "")
        ts = rec.get("timestamp", "")
        rec_id = rec.get("id", "")

        if role == "toolResult":
            # Accumulate tool results — they'll be flushed as a user turn.
            pending_tool_results.append(rec)
            continue

        # Before processing user/assistant, flush any pending tool results.
        if pending_tool_results:
            turn = _flush_tool_results(pending_tool_results)
            if turn:
                turns.append(turn)
            pending_tool_results = []

        if role == "user":
            turn = _extract_user_turn(rec)
            if turn:
                turns.append(turn)

        elif role == "assistant":
            turn = _extract_assistant_turn(rec)
            if turn:
                turns.append(turn)

    # Flush any trailing tool results.
    if pending_tool_results:
        turn = _flush_tool_results(pending_tool_results)
        if turn:
            turns.append(turn)

    return turns


def _extract_user_turn(rec: dict) -> Turn | None:
    """Extract a user turn from an omp user message record."""
    msg = rec.get("message", {})
    content = msg.get("content", [])
    ts = rec.get("timestamp", "")
    rec_id = rec.get("id", "")

    if isinstance(content, str):
        if not content.strip():
            return None
        return Turn(role="user", content=content, timestamp=ts, uuid=rec_id)

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "").strip()
                    if text:
                        text_parts.append(text)
            elif isinstance(block, str):
                text_parts.append(block)

        if not text_parts:
            return None

        return Turn(role="user", content="\n".join(text_parts), timestamp=ts, uuid=rec_id)

    return None


def _extract_assistant_turn(rec: dict) -> Turn | None:
    """Extract an assistant turn from an omp assistant message record.

    omp uses "toolCall" blocks (not "tool_use") with slightly different structure:
      - type: "toolCall"
      - id: "call_..."
      - name: tool name
      - arguments: dict (not "input")
    """
    msg = rec.get("message", {})
    content = msg.get("content", [])
    ts = rec.get("timestamp", "")
    rec_id = rec.get("id", "")

    if not isinstance(content, list):
        return None

    text_parts: list[str] = []
    tool_calls: list[dict] = []

    for block in content:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")

        if block_type == "text":
            text = block.get("text", "").strip()
            if text:
                text_parts.append(text)

        elif block_type == "toolCall":
            tool_call = _classify_tool_call(block)
            tool_calls.append(tool_call)
            text_parts.append(_format_tool_call(tool_call))

        elif block_type == "thinking":
            # Skip thinking blocks — same as Claude Code extractor.
            pass

    if not text_parts:
        return None

    return Turn(
        role="assistant",
        content="\n".join(text_parts),
        tool_calls=tool_calls,
        timestamp=ts,
        uuid=rec_id,
    )


def _flush_tool_results(tool_result_recs: list[dict]) -> Turn | None:
    """Convert accumulated toolResult messages into a user turn.

    This matches the Claude Code extractor's convention where tool results
    are represented as user turns with tool_results populated.
    """
    tool_results = []
    text_parts = []

    for rec in tool_result_recs:
        msg = rec.get("message", {})
        tool_call_id = msg.get("toolCallId", "")
        tool_name = msg.get("toolName", "")
        content = msg.get("content", [])
        ts = rec.get("timestamp", "")

        # Extract text from content blocks.
        result_text = ""
        if isinstance(content, str):
            result_text = content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            result_text = "\n".join(parts)

        is_error = msg.get("isError", False)

        tool_results.append({
            "tool_use_id": tool_call_id,
            "content": result_text,
            "is_error": is_error,
            "tool_name": tool_name,
        })

        text_parts.append(
            f'<tool_result tool_use_id="{tool_call_id}">\n{result_text}\n</tool_result>'
        )

    if not tool_results and not text_parts:
        return None

    first_ts = tool_result_recs[0].get("timestamp", "") if tool_result_recs else ""

    return Turn(
        role="user",
        content="\n".join(text_parts),
        tool_results=tool_results,
        timestamp=first_ts,
        uuid="",
    )


def _classify_tool_call(block: dict) -> dict:
    """Extract and classify an omp toolCall block.

    omp uses "arguments" instead of "input", and tool IDs are "call_..." prefixed.
    MCP tool names use underscore separators: mcp_<server>_<tool>.
    """
    name = block.get("name", "")
    # omp uses "arguments" for tool inputs
    tool_input = block.get("arguments", block.get("input", {}))

    result = {
        "id": block.get("id", ""),
        "name": name,
        "input": tool_input,
    }

    if name.startswith("mcp_"):
        parts = name.split("_", 2)
        result["source"] = "mcp"
        result["mcp_server"] = parts[1] if len(parts) >= 2 else "unknown"
    else:
        result["source"] = "standard"
        result["mcp_server"] = ""

    return result


def _format_tool_call(tool_call: dict) -> str:
    """Format a tool call as an XML-tagged string for training data.

    Uses the same format as the Claude Code extractor for downstream compatibility.
    """
    args_json = json.dumps(
        tool_call.get("input", {}), ensure_ascii=False, separators=(",", ":")
    )
    name = tool_call.get("name", "unknown")
    source = tool_call.get("source", "standard")
    attrs = f'name="{name}" source="{source}"'
    mcp_server = tool_call.get("mcp_server", "")
    if mcp_server:
        attrs += f' mcp_server="{mcp_server}"'
    return f"<tool_call {attrs}>\n{args_json}\n</tool_call>"


def _classify_runtime(api: str, provider: str, model: str) -> str:
    """Classify the omp runtime type from API/provider/model metadata."""
    if not api:
        return "omp"

    # Include provider info for richer runtime classification.
    if provider:
        return f"omp-{provider.lower()}"

    return f"omp-{api}"


def discover_omp_sessions(
    base_dir: Path | None = None, pattern: str = "-gt-*"
) -> list[Path]:
    """Discover all omp session JSONL files.

    Args:
        base_dir: The .omp/agent/sessions/ directory. Defaults to OMP_SESSIONS_DIR.
        pattern: Glob pattern for project subdirectories. Default matches
                 all Gas Town project directories.

    Returns:
        List of paths to session JSONL files, sorted by modification time (newest first).
    """
    if base_dir is None:
        base_dir = OMP_SESSIONS_DIR

    if not base_dir.exists():
        logger.warning("omp sessions directory not found: %s", base_dir)
        return []

    sessions = []
    for project_dir in base_dir.glob(pattern):
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            sessions.append(jsonl_file)

    return sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)


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


def is_omp_session(path: Path) -> bool:
    """Check if a JSONL file is an omp session (vs Claude Code session).

    Reads the first record and checks for omp-specific markers:
      - type: "session" with version field
      - type: "model_change"
      - type: "message" with message.role
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    rec_type = rec.get("type", "")
                    # omp sessions start with a "session" record with version field
                    if rec_type == "session" and "version" in rec:
                        return True
                    # Or a model_change (omp-specific)
                    if rec_type == "model_change":
                        return True
                    # Claude Code uses type: "user" / "assistant" directly
                    if rec_type in ("user", "assistant"):
                        return False
                    # omp uses type: "message" with role inside
                    if rec_type == "message":
                        return True
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return False


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.is_file():
            session = extract_omp_session(path)
            if session:
                print(f"Session: {session.session_id}")
                print(f"Runtime: {session.runtime_type}")
                print(f"Model: {session.metadata.get('omp_model', 'unknown')}")
                print(f"Provider: {session.metadata.get('omp_provider', 'unknown')}")
                if session.mcp_servers:
                    print(f"MCP servers: {', '.join(session.mcp_servers)}")
                print(f"Turns: {len(session.turns)}")
                tool_call_count = sum(len(t.tool_calls) for t in session.turns)
                tool_result_count = sum(len(t.tool_results) for t in session.turns)
                print(f"Tool calls: {tool_call_count}, Tool results: {tool_result_count}")
                for i, turn in enumerate(session.turns[:5]):
                    preview = turn.content[:100].replace("\n", " ")
                    tools = f" [{len(turn.tool_calls)} tools]" if turn.tool_calls else ""
                    results = f" [{len(turn.tool_results)} results]" if turn.tool_results else ""
                    print(f"  {i}: [{turn.role}]{tools}{results} {preview}...")
            else:
                print("No usable data in session")
        elif path.is_dir():
            sessions = discover_omp_sessions(path)
            print(f"Found {len(sessions)} omp session files")
            for s in sessions[:10]:
                size_kb = s.stat().st_size // 1024
                print(f"  {s.parent.name}/{s.name} ({size_kb}KB)")
    else:
        sessions = discover_omp_sessions()
        print(f"Found {len(sessions)} omp session files in {OMP_SESSIONS_DIR}")
        for s in sessions[:10]:
            size_kb = s.stat().st_size // 1024
            print(f"  {s.parent.name}/{s.name} ({size_kb}KB)")
