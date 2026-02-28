"""
Session linker that maps session_id to bead_id and OTel signals.
"""
import json
import logging
import os
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
                            # Extract session info if available
                            if 'session_id' in record:
                                self._cmd_usage_cache[record['session_id']] = record
        except (IOError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load {CMD_USAGE_PATH}: {e}")
        
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
            logger.warning(f"Failed to load {COSTS_PATH}: {e}")
        
        return self._costs_cache
    
    def link_session(self, session_id: str) -> Dict[str, Any]:
        """
        Link a session ID to bead ID and OTel signals.
        
        Args:
            session_id: The session ID to link
            
        Returns:
            Dictionary with bead_id and otel_signals
        """
        result = {
            "bead_id": None,
            "otel_signals": {}
        }
        
        # Try to get bead_id from OTel logs first
        try:
            # Query VictoriaLogs for session resource attribute
            logs_query = f'{{gt.session="{session_id}"}}'
            logs_result = self.otel_client.query_victoria_logs(logs_query)
            
            if logs_result and 'data' in logs_result:
                # Extract bead_id from resource attributes
                for entry in logs_result['data'].get('result', []):
                    if 'values' in entry:
                        for value_pair in entry['values']:
                            if len(value_pair) >= 2:
                                log_line = value_pair[1]
                                if isinstance(log_line, str):
                                    # Try to parse as JSON first
                                    try:
                                        log_data = json.loads(log_line)
                                        if 'resource' in log_data and 'attributes' in log_data['resource']:
                                            attrs = log_data['resource']['attributes']
                                            if 'gt.issue' in attrs:
                                                result["bead_id"] = attrs['gt.issue']
                                                break
                                    except (json.JSONDecodeError, KeyError, TypeError):
                                        # If JSON parsing fails, check if it's a string containing gt.issue
                                        if 'gt.issue' in log_line:
                                            # Extract bead_id from string format
                                            try:
                                                # Look for pattern like "gt.issue":"bead-id"
                                                start_idx = log_line.find('"gt.issue"')
                                                if start_idx != -1:
                                                    colon_idx = log_line.find(':', start_idx)
                                                    if colon_idx != -1:
                                                        # Find the next quote after colon
                                                        quote_idx = log_line.find('"', colon_idx + 1)
                                                        if quote_idx != -1:
                                                            end_quote_idx = log_line.find('"', quote_idx + 1)
                                                            if end_quote_idx != -1:
                                                                bead_id = log_line[quote_idx + 1:end_quote_idx]
                                                                result["bead_id"] = bead_id
                                                                break
                                            except Exception:
                                                continue
                
                # If we found logs, extract additional signals
                if logs_result:
                    result["otel_signals"]["logs_available"] = True
                    result["otel_signals"]["log_count"] = len(logs_result['data'].get('result', []))
        except Exception as e:
            logger.warning(f"Failed to query OTel logs for {session_id}: {e}")
        
        # Try to get metrics data
        try:
            metrics_query = f'gt_session_duration{{session_id="{session_id}"}}'
            metrics_result = self.otel_client.query_victoria_metrics(metrics_query)
            
            if metrics_result:
                result["otel_signals"]["metrics_available"] = True
                # Extract relevant metrics
                if 'data' in metrics_result and 'result' in metrics_result['data']:
                    result["otel_signals"]["metrics"] = metrics_result['data']['result']
        except Exception as e:
            logger.warning(f"Failed to query OTel metrics for {session_id}: {e}")
        
        # Fallback to local files if no bead_id found
        if result["bead_id"] is None:
            cmd_usage = self._load_cmd_usage()
            costs = self._load_costs()
            
            # Check costs file for session_id
            if session_id in costs:
                cost_record = costs[session_id]
                if 'role' in cost_record:
                    result["otel_signals"]["fallback_source"] = "costs.jsonl"
                    # We don't have bead_id in costs, but we can note the role
                    result["otel_signals"]["role"] = cost_record.get('role')
            
            # Check cmd-usage for session_id
            if session_id in cmd_usage:
                cmd_record = cmd_usage[session_id]
                if 'actor' in cmd_record:
                    result["otel_signals"]["fallback_source"] = "cmd-usage.jsonl"
                    result["otel_signals"]["actor"] = cmd_record.get('actor')
        
        return result