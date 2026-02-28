"""
OTel client for querying VictoriaMetrics and VictoriaLogs.
"""
import json
import logging
from typing import Dict, Any, Optional
import requests
from functools import lru_cache

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
    
    def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make a request to the given URL with parameters."""
    def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make a request to the given URL with parameters."""
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, ValueError, Exception) as e:
            logger.warning(f"Failed to query {url}: {e}")
            return None
    @lru_cache(maxsize=128)
    def query_victoria_metrics(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Query VictoriaMetrics via PromQL HTTP API.
        
        Args:
            query: PromQL query string
            
        Returns:
            Structured results or None if query fails
        """
        params = {"query": query}
        url = f"{VICTORIA_METRICS_URL}/api/v1/query"
        return self._make_request(url, params)
    
    @lru_cache(maxsize=128)
    def query_victoria_logs(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Query VictoriaLogs via LogsQL HTTP API.
        
        Args:
            query: LogsQL query string
            
        Returns:
            Structured results or None if query fails
        """
        params = {"query": query}
        url = f"{VICTORIA_LOGS_URL}/select/logsql/query"
        return self._make_request(url, params)