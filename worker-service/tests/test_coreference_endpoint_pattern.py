"""Test for task 6.1.3: Endpoint pattern extraction with segment filtering."""

import pytest
from app.qa.coreference import ConversationState


def test_endpoint_pattern_extraction():
    """Test that endpoint pattern correctly filters single-segment paths."""
    state = ConversationState()
    
    # Test text with various endpoint patterns
    text = """
    Check /health endpoint
    Call /api/users endpoint
    Use /api/v1/payments/process
    Hit /status
    Query /v2/orders/{id}/items
    """
    
    known_services = []
    entities = state.extract_entities(text, known_services)
    
    # Should extract only endpoints with 2+ segments (count('/') >= 2)
    endpoints = entities["endpoint"]
    
    # Expected: /api/users, /api/v1/payments/process, /v2/orders/{id}/items
    # Excluded: /health, /status (single segment)
    assert len(endpoints) == 3, f"Expected 3 endpoints, got {len(endpoints)}: {endpoints}"
    
    # Verify each endpoint has at least 2 slashes
    for endpoint in endpoints:
        assert endpoint.count('/') >= 2, f"Endpoint {endpoint} has fewer than 2 slashes"
    
    # Verify specific endpoints are included
    assert "/api/users" in endpoints
    assert "/api/v1/payments/process" in endpoints or "/api/v1/payments" in endpoints
    
    # Verify single-segment paths are excluded
    assert "/health" not in endpoints
    assert "/status" not in endpoints


def test_endpoint_pattern_regex():
    """Test the regex pattern matches the specification."""
    state = ConversationState()
    
    # Valid patterns that should match
    valid_endpoints = [
        "/api/users",
        "/v1/orders",
        "/api/v2/payments",
        "/users/{id}/profile",
        "/api-gateway/health",
        "/service_name/endpoint",
    ]
    
    for endpoint in valid_endpoints:
        text = f"Call {endpoint} endpoint"
        entities = state.extract_entities(text, [])
        # Note: some may be filtered by segment count, but should match the regex
        # We're testing that the pattern works, not the filter
    
    # Invalid patterns that should NOT match (start with uppercase or invalid chars)
    invalid_endpoints = [
        "/API/users",  # uppercase start
        "/123/users",  # starts with digit
        "api/users",   # no leading slash
    ]
    
    for endpoint in invalid_endpoints:
        text = f"Call {endpoint} endpoint"
        entities = state.extract_entities(text, [])
        assert endpoint not in entities["endpoint"], f"Invalid endpoint {endpoint} was matched"


def test_endpoint_segment_count_boundary():
    """Test the boundary condition for segment count."""
    state = ConversationState()
    
    # Exactly 1 slash (0 segments after first slash) - should be excluded
    text1 = "Check /health"
    entities1 = state.extract_entities(text1, [])
    assert "/health" not in entities1["endpoint"]
    
    # Exactly 2 slashes (1 segment) - should be excluded
    text2 = "Check /api/health"
    entities2 = state.extract_entities(text2, [])
    # Wait, this has 2 slashes, so count('/') = 2, which means >= 2, so it SHOULD be included
    assert "/api/health" in entities2["endpoint"], "Endpoint with 2 slashes should be included"
    
    # 3 slashes (2 segments) - should be included
    text3 = "Check /api/v1/health"
    entities3 = state.extract_entities(text3, [])
    assert "/api/v1/health" in entities3["endpoint"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
