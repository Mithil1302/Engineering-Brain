"""
Test suite for GapDetector._infer_service() implementation.

Verifies that service inference uses the same word-boundary regex as
ConversationState.extract_entities() and returns "general" for no matches.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.qa.gap_detector import GapDetector


class TestServiceInference:
    """Test service inference implementation."""
    
    @pytest.fixture
    def gap_detector(self):
        """Create GapDetector with mocked dependencies."""
        pg_cfg = {
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "user": "test",
            "password": "test"
        }
        llm = Mock()
        return GapDetector(pg_cfg, llm)
    
    def test_word_boundary_regex_exact_match(self, gap_detector):
        """Test that service name matches with word boundaries."""
        with patch.object(gap_detector, '_get_known_services', return_value=['payment-service', 'user-service']):
            result = gap_detector._infer_service("What does payment-service do?", "test/repo")
            assert result == "payment-service"
    
    def test_word_boundary_prevents_partial_match(self, gap_detector):
        """Test that partial matches are rejected (e.g., 'payment' vs 'payment-service')."""
        with patch.object(gap_detector, '_get_known_services', return_value=['payment-service']):
            # "payment" alone should NOT match "payment-service"
            result = gap_detector._infer_service("What does payment do?", "test/repo")
            assert result == "general"
    
    def test_case_insensitive_matching(self, gap_detector):
        """Test that service matching is case-insensitive."""
        with patch.object(gap_detector, '_get_known_services', return_value=['payment-service']):
            result = gap_detector._infer_service("What does PAYMENT-SERVICE do?", "test/repo")
            assert result == "payment-service"
            
            result = gap_detector._infer_service("What does Payment-Service do?", "test/repo")
            assert result == "payment-service"
    
    def test_returns_general_when_no_match(self, gap_detector):
        """Test that 'general' is returned when no service matches."""
        with patch.object(gap_detector, '_get_known_services', return_value=['payment-service', 'user-service']):
            result = gap_detector._infer_service("What is the weather today?", "test/repo")
            assert result == "general"
    
    def test_returns_general_not_none(self, gap_detector):
        """Test that return value is 'general' string, not None."""
        with patch.object(gap_detector, '_get_known_services', return_value=[]):
            result = gap_detector._infer_service("Some question", "test/repo")
            assert result == "general"
            assert result is not None
            assert isinstance(result, str)
    
    def test_first_match_wins(self, gap_detector):
        """Test that first matching service is returned."""
        with patch.object(gap_detector, '_get_known_services', 
                         return_value=['payment-service', 'user-service', 'auth-service']):
            # Question mentions multiple services - first match should win
            result = gap_detector._infer_service(
                "How does payment-service interact with user-service?", 
                "test/repo"
            )
            assert result == "payment-service"
    
    def test_special_characters_escaped(self, gap_detector):
        """Test that service names with special regex characters are properly escaped."""
        with patch.object(gap_detector, '_get_known_services', 
                         return_value=['api.gateway', 'user-service']):
            # The dot in 'api.gateway' should be treated as literal, not regex wildcard
            result = gap_detector._infer_service("What does api.gateway do?", "test/repo")
            assert result == "api.gateway"
            
            # This should NOT match because 'apixgateway' is different from 'api.gateway'
            result = gap_detector._infer_service("What does apixgateway do?", "test/repo")
            assert result == "general"
    
    def test_consistency_with_coreference_resolver(self, gap_detector):
        """
        Test that the regex pattern matches ConversationState.extract_entities().
        
        Both should use: re.search(rf'\b{re.escape(service)}\b', text, re.IGNORECASE)
        """
        import re
        
        # Simulate the exact pattern used in ConversationState.extract_entities()
        service = "payment-service"
        question = "What does payment-service handle?"
        
        # Pattern from ConversationState.extract_entities()
        coreference_pattern = rf'\b{re.escape(service)}\b'
        coreference_match = re.search(coreference_pattern, question, re.IGNORECASE)
        
        # Pattern from GapDetector._infer_service()
        with patch.object(gap_detector, '_get_known_services', return_value=[service]):
            gap_detector_result = gap_detector._infer_service(question, "test/repo")
        
        # Both should agree on the match
        assert coreference_match is not None
        assert gap_detector_result == service


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
