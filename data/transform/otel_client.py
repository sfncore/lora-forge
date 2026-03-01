"""
OTel client for querying VictoriaMetrics and VictoriaLogs.
"""
import json
import logging
from typing import Dict, Any, List, Optional
import requests

# Configure logging
logger = logging.getLogger(__name__)

# Constants for endpoints
VICTORIA_METRICS_URL = "http://localhost:8428"
VICTORIA_LOGS_URL = "http://localhost:9428"


class OTelClient:
    """Client for querying VictoriaMetrics and VictoriaLogs."""

    def __init__(self):
        self.session = requests.Session()
        self.session.timeout = 10  # 10 second timeout for requests

    def _query_logs(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Query VictoriaLogs via LogsQL. Returns list of log entries (NDJSON parsed)."""
        url = f"{VICTORIA_LOGS_URL}/select/logsql/query"
        params = {"query": query, "limit": str(limit)}
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            # VictoriaLogs returns NDJSON (one JSON object per line)
            entries = []
            for line in response.text.strip().splitlines():
                if line.strip():
                    entries.append(json.loads(line))
            return entries
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("Failed to query VictoriaLogs: %s", e)
            return []

    def _query_metrics(self, query: str) -> Optional[Dict[str, Any]]:
        """Query VictoriaMetrics via PromQL HTTP API."""
        url = f"{VICTORIA_METRICS_URL}/api/v1/query"
        params = {"query": query}
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("Failed to query VictoriaMetrics: %s", e)
            return None

    # -- Structured query methods ------------------------------------------

    def get_done_events(self, session_id: str) -> List[Dict[str, Any]]:
        """Get 'done' events for a session. Returns list of log entries with exit_type."""
        query = f'_msg:"done" AND gt.session:"{session_id}"'
        return self._query_logs(query, limit=10)

    def get_session_lifecycle(self, session_id: str) -> List[Dict[str, Any]]:
        """Get session.start and session.stop events for duration calculation."""
        query = f'(_msg:"session.start" OR _msg:"session.stop") AND session_id:"{session_id}"'
        return self._query_logs(query, limit=10)

    # -- Legacy methods (kept for backwards compat) ------------------------

    def query_victoria_metrics(self, query: str) -> Optional[Dict[str, Any]]:
        """Query VictoriaMetrics via PromQL HTTP API (legacy wrapper)."""
        return self._query_metrics(query)

    def query_victoria_logs(self, query: str) -> List[Dict[str, Any]]:
        """Query VictoriaLogs via LogsQL HTTP API (legacy wrapper, now returns list)."""
        return self._query_logs(query)
