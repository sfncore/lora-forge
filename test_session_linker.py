"""
Unit tests for Session linker.
"""
import unittest
import os
import json
from unittest.mock import patch, MagicMock
from data.transform.session_linker import SessionLinker


class TestSessionLinker(unittest.TestCase):
    """Test cases for SessionLinker."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.linker = SessionLinker()
    
    def test_link_session_with_otel_success(self):
        """Test successful session linking with OTel data."""
        # Create a mock OTel client
        mock_otel_client = MagicMock()
        mock_otel_client.query_victoria_logs.return_value = {
            "data": {
                "result": [
                    {
                        "values": [
                            [1234567890, '{"resource": {"attributes": {"gt.issue": "test-bead-id"}}}']
                        ]
                    }
                ]
            }
        }
        mock_otel_client.query_victoria_metrics.return_value = {
            "data": {
                "result": [{"metric": {"session_id": "test-session"}, "value": [1234567890, "100"]}]
            }
        }
        
        # Replace the linker's otel_client with our mock
        original_client = self.linker.otel_client
        self.linker.otel_client = mock_otel_client
        try:
            result = self.linker.link_session("test-session")
            
            self.assertEqual(result["bead_id"], "test-bead-id")
            self.assertTrue(result["otel_signals"]["logs_available"])
            self.assertTrue(result["otel_signals"]["metrics_available"])
        finally:
            self.linker.otel_client = original_client
    
    @patch('data.transform.session_linker.OTelClient')
    def test_link_session_with_otel_failure(self, mock_otel_client_class):
        """Test session linking when OTel queries fail."""
        mock_otel_client = MagicMock()
        mock_otel_client.query_victoria_logs.return_value = None
        mock_otel_client.query_victoria_metrics.return_value = None
        mock_otel_client_class.return_value = mock_otel_client
        
        # Create temporary fallback files
        cmd_usage_path = os.path.expanduser("~/.gt/cmd-usage.jsonl")
        costs_path = os.path.expanduser("~/.gt/costs.jsonl")
        
        # Ensure .gt directory exists
        gt_dir = os.path.dirname(cmd_usage_path)
        os.makedirs(gt_dir, exist_ok=True)
        
        # Write test data to costs file
        test_costs = {"session_id": "test-session", "role": "polecat"}
        with open(costs_path, 'w') as f:
            f.write(json.dumps(test_costs) + '\n')
        
        try:
            result = self.linker.link_session("test-session")
            
            self.assertIsNone(result["bead_id"])
            self.assertEqual(result["otel_signals"]["fallback_source"], "costs.jsonl")
            self.assertEqual(result["otel_signals"]["role"], "polecat")
        finally:
            # Clean up test files
            if os.path.exists(costs_path):
                os.remove(costs_path)
    
    @patch('data.transform.session_linker.OTelClient')
    def test_link_session_fallback_to_cmd_usage(self, mock_otel_client_class):
        """Test session linking fallback to cmd-usage.jsonl."""
        mock_otel_client = MagicMock()
        mock_otel_client.query_victoria_logs.return_value = None
        mock_otel_client.query_victoria_metrics.return_value = None
        mock_otel_client_class.return_value = mock_otel_client
        
        # Create temporary fallback files
        cmd_usage_path = os.path.expanduser("~/.gt/cmd-usage.jsonl")
        costs_path = os.path.expanduser("~/.gt/costs.jsonl")
        
        # Ensure .gt directory exists
        gt_dir = os.path.dirname(cmd_usage_path)
        os.makedirs(gt_dir, exist_ok=True)
        
        # Write test data to cmd-usage file
        test_cmd = {"session_id": "test-session", "actor": "polecat/furiosa"}
        with open(cmd_usage_path, 'w') as f:
            f.write(json.dumps(test_cmd) + '\n')
        
        try:
            result = self.linker.link_session("test-session")
            
            self.assertIsNone(result["bead_id"])
            self.assertEqual(result["otel_signals"]["fallback_source"], "cmd-usage.jsonl")
            self.assertEqual(result["otel_signals"]["actor"], "polecat/furiosa")
        finally:
            # Clean up test files
            if os.path.exists(cmd_usage_path):
                os.remove(cmd_usage_path)


if __name__ == '__main__':
    unittest.main()