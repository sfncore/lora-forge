"""
Session linker that maps session_id to bead_id and OTel signals.

Queries VictoriaLogs for done events (exit_type, status, topic) and session
lifecycle (duration_ms). Falls back to local files (~/.gt/cmd-usage.jsonl,
~/.gt/costs.jsonl) when OTel data is unavailable.
"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from data.transform.otel_client import OTelClient

# Configure logging
logger = logging.getLogger(__name__)

# Constants for fallback files
CMD_USAGE_PATH = os.path.expanduser("~/.gt/cmd-usage.jsonl")
COSTS_PATH = os.path.expanduser("~/.gt/costs.jsonl")


class SessionLinker:
    """Links session IDs to bead IDs and OTel signals."""

    def __init__(self):
        self.otel_client = OTelClient()
        self._cmd_usage_cache = None
        self._costs_cache = None

    def _load_cmd_usage(self) -> Dict[str, Any]:
        """Load and cache cmd-usage.jsonl data."""
        if self._cmd_usage_cache is not None:
            return self._cmd_usage_cache

        self._cmd_usage_cache = {}
        try:
            if os.path.exists(CMD_USAGE_PATH):
                with open(CMD_USAGE_PATH, 'r') as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            if 'session_id' in record:
                                self._cmd_usage_cache[record['session_id']] = record
        except (IOError, json.JSONDecodeError) as e:
            logger.warning("Failed to load %s: %s", CMD_USAGE_PATH, e)

        return self._cmd_usage_cache

    def _load_costs(self) -> Dict[str, Any]:
        """Load and cache costs.jsonl data."""
        if self._costs_cache is not None:
            return self._costs_cache

        self._costs_cache = {}
        try:
            if os.path.exists(COSTS_PATH):
                with open(COSTS_PATH, 'r') as f:
                    for line in f:
                        if line.strip():
                            record = json.loads(line)
                            if 'session_id' in record:
                                self._costs_cache[record['session_id']] = record
        except (IOError, json.JSONDecodeError) as e:
            logger.warning("Failed to load %s: %s", COSTS_PATH, e)

        return self._costs_cache

    def _extract_exit_type(self, session_id: str) -> Optional[str]:
        """Extract exit_type from done events for this session."""
        done_events = self.otel_client.get_done_events(session_id)
        if not done_events:
            return None
        # Use the most recent done event
        for event in done_events:
            exit_type = event.get("exit_type")
            if exit_type:
                return exit_type
        return None

    def _extract_duration_ms(self, session_id: str) -> Optional[int]:
        """Compute duration_ms from session.start and session.stop events."""
        lifecycle = self.otel_client.get_session_lifecycle(session_id)
        if not lifecycle:
            return None

        start_time = None
        stop_time = None
        for event in lifecycle:
            msg = event.get("_msg", "")
            timestamp = event.get("_time")
            if not timestamp:
                continue
            try:
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if "session.start" in msg:
                if start_time is None or ts < start_time:
                    start_time = ts
            elif "session.stop" in msg:
                if stop_time is None or ts > stop_time:
                    stop_time = ts

        if start_time and stop_time:
            delta = stop_time - start_time
            return int(delta.total_seconds() * 1000)
        return None

    def _extract_bead_id(self, done_events) -> Optional[str]:
        """Extract bead_id (gt.issue) from done event fields."""
        for event in done_events:
            bead_id = event.get("gt.issue")
            if bead_id:
                return bead_id
            # Also check _stream field which may contain gt.issue as a label
            stream = event.get("_stream", "")
            if "gt.issue" in stream:
                # _stream format: {gt.issue="lf-xxxx",...}
                for part in stream.strip("{}").split(","):
                    if part.strip().startswith("gt.issue="):
                        val = part.split("=", 1)[1].strip('"')
                        if val:
                            return val
        return None

    def link_session(self, session_id: str) -> Dict[str, Any]:
        """
        Link a session ID to bead ID and OTel signals.

        Queries VictoriaLogs for done events (exit_type, status, topic) and
        session lifecycle (duration_ms). Returns dict with bead_id and
        otel_signals containing exit_type, status, topic, duration_ms.
        """
        result: Dict[str, Any] = {
            "bead_id": None,
            "otel_signals": {},
        }
        signals = result["otel_signals"]

        # 1. Query done events for exit_type, status, topic, and bead_id
        try:
            done_events = self.otel_client.get_done_events(session_id)
            if done_events:
                # Extract fields from most recent done event
                for event in done_events:
                    exit_type = event.get("exit_type")
                    if exit_type:
                        signals["exit_type"] = exit_type
                        status = event.get("status")
                        if status:
                            signals["status"] = status
                        topic = event.get("gt.topic")
                        if topic:
                            signals["topic"] = topic
                        break

                # Extract bead_id from done events
                result["bead_id"] = self._extract_bead_id(done_events)
        except Exception as e:
            logger.warning("Failed to query done events for %s: %s", session_id, e)

        # 2. Query session lifecycle for duration_ms
        try:
            duration_ms = self._extract_duration_ms(session_id)
            if duration_ms is not None:
                signals["duration_ms"] = duration_ms
        except Exception as e:
            logger.warning("Failed to query lifecycle for %s: %s", session_id, e)

        # 4. Fallback to local files if no bead_id found
        if result["bead_id"] is None:
            cmd_usage = self._load_cmd_usage()
            costs = self._load_costs()

            if session_id in costs:
                cost_record = costs[session_id]
                if 'role' in cost_record:
                    signals.setdefault("fallback_source", "costs.jsonl")
                    signals.setdefault("role", cost_record.get('role'))

            if session_id in cmd_usage:
                cmd_record = cmd_usage[session_id]
                if 'actor' in cmd_record:
                    signals.setdefault("fallback_source", "cmd-usage.jsonl")
                    signals.setdefault("actor", cmd_record.get('actor'))

        return result
