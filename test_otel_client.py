"""
Unit tests for OTel client.
"""
import unittest
from unittest.mock import patch, MagicMock
from data.transform.otel_client import OTelClient


class TestOTelClient(unittest.TestCase):
    """Test cases for OTelClient."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = OTelClient()
    
    @patch('data.transform.otel_client.requests.Session')
    def test_query_victoria_metrics_success(self, mock_session_class):
        """Test successful VictoriaMetrics query."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [],
                "resultType": "vector"
            },
            "stats": {
                "seriesFetched": "0",
                "executionTimeMsec": 3
            }
        }
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        result = self.client.query_victoria_metrics("test_query")
        
        self.assertEqual(result["status"], "success")
        self.assertIn("result", result["data"])
        self.assertEqual(result["data"]["result"], [])
    
    def test_query_victoria_metrics_failure(self):
        """Test failed VictoriaMetrics query."""
        # Create a mock session that raises an exception
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection error")
        
        # Replace the client's session with our mock
        original_session = self.client.session
        self.client.session = mock_session
        try:
            result = self.client.query_victoria_metrics("test_query")
            self.assertIsNone(result)
        finally:
            self.client.session = original_session
    
    def test_query_victoria_logs_success(self):
        """Test successful VictoriaLogs query."""
        # Create a mock session with successful response
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": []
            }
        }
        mock_session.get.return_value = mock_response
        
        # Replace the client's session with our mock
        original_session = self.client.session
        self.client.session = mock_session
        try:
            result = self.client.query_victoria_logs("test_query")
            self.assertIsNotNone(result)
            self.assertEqual(result["status"], "success")
            self.assertIn("result", result["data"])
            self.assertEqual(result["data"]["result"], [])
        finally:
            self.client.session = original_session
    
    def test_query_victoria_logs_failure(self):
        """Test failed VictoriaLogs query."""
        # Create a mock session that raises an exception
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection error")
        
        # Replace the client's session with our mock
        original_session = self.client.session
        self.client.session = mock_session
        try:
            result = self.client.query_victoria_logs("test_query")
            self.assertIsNone(result)
        finally:
            self.client.session = original_session
    
    def test_caching(self):
        """Test that queries are cached."""
        with patch.object(self.client, '_make_request') as mock_make_request:
            mock_make_request.return_value = {"cached": True}
            
            # First call
            result1 = self.client.query_victoria_metrics("test_query")
            # Second call with same query
            result2 = self.client.query_victoria_metrics("test_query")
            
            # Should only call _make_request once due to caching
            mock_make_request.assert_called_once()
            self.assertEqual(result1, result2)


if __name__ == '__main__':
    unittest.main()