# Pi-Rust Session Format (JSONL v3)

Reference for building the pir session extractor (`data/extract/pir_sessions.py`).

## Storage Location

```
~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl
```

- Sessions organized by working directory context
- Encoded CWD replaces `/` with `-` and wraps with `--`: `--home-ubuntu-gt-deacon--`
- SQLite index at `~/.pi/agent/sessions/session-index.sqlite`
- Currently 726+ sessions across all rigs

## SQLite Index Schema

```sql
CREATE TABLE sessions (
    path TEXT PRIMARY KEY,
    id TEXT NOT NULL,
    cwd TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    message_count INTEGER NOT NULL,
    last_modified_ms INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    name TEXT
);
```

Use the index for fast session discovery instead of globbing the filesystem.

## JSONL v3 Event Types

### Session Header (first line)
```json
{
  "type": "session",
  "version": 3,
  "id": "dd46c0ee-3ee4-4c5a-962e-2ccbbd69e7e2",
  "timestamp": "2026-02-25T08:30:46.710Z",
  "cwd": "/home/ubuntu/gt/deacon",
  "provider": "Alibaba",
  "modelId": "qwen3-coder-plus",
  "thinkingLevel": "off"
}
```

### User Message
```json
{
  "type": "message",
  "id": "57f9d64c",
  "parentId": "f51247f9",
  "timestamp": "2026-02-25T08:30:46.757Z",
  "message": {
    "role": "user",
    "content": "[GAS TOWN] deacon <- daemon ...",
    "timestamp": 1772008246757
  }
}
```

### Assistant Message (with tool calls)
```json
{
  "type": "message",
  "id": "da68c815",
  "parentId": "57f9d64c",
  "timestamp": "2026-02-25T08:32:33.237Z",
  "message": {
    "role": "assistant",
    "content": [
      { "type": "text", "text": "I'll start...\n\n" },
      {
        "type": "toolCall",
        "id": "",
        "name": "bash",
        "arguments": { "command": "gt deacon heartbeat" }
      }
    ],
    "api": "openai-completions",
    "provider": "Alibaba",
    "model": "qwen3-coder-plus",
    "usage": {
      "input": 3341,
      "output": 41,
      "cacheRead": 0,
      "cacheWrite": 0,
      "totalTokens": 3382,
      "cost": { "input": 0.0, "output": 0.0 }
    },
    "stopReason": "toolUse",
    "timestamp": 1772008247946
  }
}
```

### Tool Result
```json
{
  "type": "message",
  "id": "b811789f",
  "parentId": "da68c815",
  "timestamp": "2026-02-25T08:32:33.237Z",
  "message": {
    "role": "toolResult",
    "toolCallId": "",
    "toolName": "bash",
    "content": [
      { "type": "text", "text": "✓ Heartbeat updated\n" }
    ],
    "isError": false,
    "timestamp": 1772008248841
  }
}
```

### Model Change
```json
{
  "type": "model_change",
  "id": "87517077",
  "timestamp": "...",
  "provider": "Alibaba",
  "modelId": "qwen3-coder-plus"
}
```

### Thinking Level Change
```json
{
  "type": "thinking_level_change",
  "id": "f51247f9",
  "parentId": "87517077",
  "timestamp": "...",
  "thinkingLevel": "off"
}
```

## Mapping to lora_forge ExtractedSession

| pir field | lora_forge field | Notes |
|-----------|-----------------|-------|
| `session.id` | `session_id` | Direct |
| `session.cwd` | metadata + role detection | Parse CWD for rig/role |
| `message.role=user` | `Turn(role="user")` | Content is string |
| `message.role=assistant` | `Turn(role="assistant")` | Content is array of blocks |
| `content[].type=text` | `Turn.content` | Concatenate text blocks |
| `content[].type=toolCall` | `Turn.tool_calls` | Map name + arguments |
| `message.role=toolResult` | `Turn.tool_results` | Map toolName + content + isError |
| `message.usage` | metadata | Token counts per turn |
| `session.provider` | metadata | Model/provider for cost tracking |

## Key Differences from Claude Code Format

1. **Content structure**: pir assistant content is an array of typed blocks;
   Claude uses a different content block format
2. **Tool calls**: pir uses `toolCall` type in content array;
   Claude uses separate `tool_use` records
3. **Tool results**: pir uses `role: "toolResult"`;
   Claude uses `type: "tool_result"` records
4. **Thinking**: pir tracks `thinkingLevel` per session and can change mid-session
5. **Parent chain**: pir uses `parentId` to build a tree; Claude uses `requestId` grouping
6. **Token usage**: pir embeds `usage` in each assistant message; Claude uses separate records

## Role Detection from CWD

```python
CWD_ROLE_PATTERNS = {
    r"/deacon$": "deacon",
    r"/deacon/dogs/boot$": "boot",
    r"/witness$": "witness",
    r"/refinery/rig$": "refinery",
    r"/mayor/rig$": "mayor",
    r"/crew/\w+$": "crew",
    r"/polecats/\w+": "polecat",
}
```

Also check first user message for `[GAS TOWN] <role>` pattern as fallback.
