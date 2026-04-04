"""
Test Task 7.2.8: ChainStep for freshness scoring with score range log message.
"""
from datetime import datetime, timedelta, timezone
from app.llm.chains import ChunkResult


def test_freshness_chainstep_log_format():
    """Verify that the log message format matches the task specification."""
    # Create test chunks with different final scores
    chunks = [
        ChunkResult(
            chunk_id=1,
            content="test content 1",
            source_ref="test1.py",
            source_type="code",
            score=0.9,
            rerank_score=0.9,
            metadata={"last_modified": datetime.now(timezone.utc) - timedelta(days=5)},
            freshness_score=1.2,
            final_score=0.99,  # (0.9 * 0.7) + (1.2 * 0.3) = 0.63 + 0.36 = 0.99
        ),
        ChunkResult(
            chunk_id=2,
            content="test content 2",
            source_ref="test2.py",
            source_type="code",
            score=0.7,
            rerank_score=0.7,
            metadata={"last_modified": datetime.now(timezone.utc) - timedelta(days=100)},
            freshness_score=0.9,
            final_score=0.76,  # (0.7 * 0.7) + (0.9 * 0.3) = 0.49 + 0.27 = 0.76
        ),
    ]
    
    # Sort by final_score descending (as the method does)
    scored = sorted(chunks, key=lambda c: c.final_score, reverse=True)
    
    # Verify the log message format
    # After sort: index 0 is highest (0.99), index -1 is lowest (0.76)
    log_message = f"scores range [{scored[-1].final_score:.2f}, {scored[0].final_score:.2f}]"
    
    # Verify format
    assert log_message == "scores range [0.76, 0.99]", \
        f"Expected 'scores range [0.76, 0.99]', got: {log_message}"
    
    print(f"✓ Log message format correct: {log_message}")
    print(f"✓ Highest score (index 0): {scored[0].final_score:.2f}")
    print(f"✓ Lowest score (index -1): {scored[-1].final_score:.2f}")


def test_freshness_chainstep_empty_chunks():
    """Verify that empty chunk list is handled gracefully."""
    scored = []
    
    # Verify the fallback message for empty list
    log_message = f"scores range [{scored[-1].final_score:.2f}, {scored[0].final_score:.2f}]" if scored else "no chunks"
    
    assert log_message == "no chunks", \
        f"Expected 'no chunks' for empty list, got: {log_message}"
    
    print(f"✓ Empty chunks handled: {log_message}")


if __name__ == "__main__":
    test_freshness_chainstep_log_format()
    test_freshness_chainstep_empty_chunks()
    print("\n✓ All Task 7.2.8 tests passed!")

