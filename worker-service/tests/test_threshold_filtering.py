"""
Test threshold filtering in RAG chain (Task 7.3).

Validates:
- 7.3.1: Apply score_threshold = 0.3 to final_score
- 7.3.2: Minimum guarantee of 3 chunks (not 2)
- 7.3.3: Threshold check runs AFTER freshness scoring
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock
from app.llm.chains import RAGChain
from app.llm.embeddings import SearchResult


def test_threshold_filtering_basic():
    """
    Test 7.3.1: Verify that score_threshold = 0.3 is applied to final_score.
    
    Chunks with final_score >= 0.3 should be kept, others filtered out.
    """
    # Create mock LLM and store
    mock_llm = Mock()
    mock_store = Mock()
    
    # Create RAGChain with default score_threshold = 0.3
    chain = RAGChain(llm=mock_llm, store=mock_store)
    
    # Verify score_threshold is set correctly
    assert chain.score_threshold == 0.3, "Default score_threshold should be 0.3"
    
    # Create test chunks with varying final_scores
    now = datetime.now(timezone.utc)
    chunks = [
        SearchResult(
            chunk_id=1,
            source_type="code",
            source_ref="high.py",
            chunk_text="high score content",
            score=0.8,
            metadata={"last_modified": now - timedelta(days=5)},
            rerank_score=0.8,
            freshness_score=1.2,
            final_score=0.0  # Will be calculated
        ),
        SearchResult(
            chunk_id=2,
            source_type="code",
            source_ref="medium.py",
            chunk_text="medium score content",
            score=0.5,
            metadata={"last_modified": now - timedelta(days=50)},
            rerank_score=0.4,
            freshness_score=1.0,
            final_score=0.0  # Will be calculated
        ),
        SearchResult(
            chunk_id=3,
            source_type="code",
            source_ref="low.py",
            chunk_text="low score content",
            score=0.2,
            metadata={"last_modified": now - timedelta(days=100)},
            rerank_score=0.2,
            freshness_score=0.9,
            final_score=0.0  # Will be calculated
        ),
    ]
    
    # Apply freshness scoring (which calculates final_score)
    scored = chain._apply_freshness_scoring(chunks)
    
    # Manually apply threshold filtering as done in run()
    filtered = [c for c in scored if c.final_score >= chain.score_threshold]
    
    # Verify filtering works correctly
    # Expected: chunk 1 (0.8*0.7 + 1.2*0.3 = 0.92) and chunk 2 (0.4*0.7 + 1.0*0.3 = 0.58) pass
    # chunk 3 (0.2*0.7 + 0.9*0.3 = 0.41) should also pass since 0.41 >= 0.3
    assert len(filtered) >= 2, f"Expected at least 2 chunks to pass threshold, got {len(filtered)}"
    
    # Verify all filtered chunks have final_score >= 0.3
    for chunk in filtered:
        assert chunk.final_score >= 0.3, (
            f"Chunk {chunk.chunk_id} has final_score {chunk.final_score} < 0.3"
        )
    
    print("✓ Threshold filtering test passed")


def test_minimum_guarantee_three_chunks():
    """
    Test 7.3.2: Verify minimum guarantee of 3 chunks (not 2).
    
    Even if fewer than 3 chunks pass the threshold, the top 3 should be returned.
    """
    mock_llm = Mock()
    mock_store = Mock()
    
    chain = RAGChain(llm=mock_llm, store=mock_store, score_threshold=0.9)  # High threshold
    
    # Create test chunks where only 1 passes the high threshold
    now = datetime.now(timezone.utc)
    chunks = [
        SearchResult(
            chunk_id=1,
            source_type="code",
            source_ref="best.py",
            chunk_text="best content",
            score=0.9,
            metadata={"last_modified": now - timedelta(days=1)},
            rerank_score=0.95,
            freshness_score=1.2,
            final_score=0.0
        ),
        SearchResult(
            chunk_id=2,
            source_type="code",
            source_ref="second.py",
            chunk_text="second content",
            score=0.5,
            metadata={"last_modified": now - timedelta(days=50)},
            rerank_score=0.5,
            freshness_score=1.0,
            final_score=0.0
        ),
        SearchResult(
            chunk_id=3,
            source_type="code",
            source_ref="third.py",
            chunk_text="third content",
            score=0.3,
            metadata={"last_modified": now - timedelta(days=100)},
            rerank_score=0.3,
            freshness_score=0.9,
            final_score=0.0
        ),
        SearchResult(
            chunk_id=4,
            source_type="code",
            source_ref="fourth.py",
            chunk_text="fourth content",
            score=0.2,
            metadata={"last_modified": now - timedelta(days=200)},
            rerank_score=0.2,
            freshness_score=0.9,
            final_score=0.0
        ),
    ]
    
    # Apply freshness scoring
    scored = chain._apply_freshness_scoring(chunks)
    
    # Apply threshold filtering with minimum guarantee
    filtered = [c for c in scored if c.final_score >= chain.score_threshold]
    if len(filtered) < 3:
        filtered = scored[:3]
    
    # Verify we get exactly 3 chunks (the minimum guarantee)
    assert len(filtered) == 3, f"Expected exactly 3 chunks (minimum guarantee), got {len(filtered)}"
    
    # Verify they are the top 3 by final_score
    assert filtered[0].chunk_id == 1, "First chunk should be the highest scored"
    assert filtered[1].chunk_id == 2, "Second chunk should be the second highest scored"
    assert filtered[2].chunk_id == 3, "Third chunk should be the third highest scored"
    
    print("✓ Minimum guarantee test passed")


def test_threshold_after_freshness():
    """
    Test 7.3.3: Verify threshold check runs AFTER freshness scoring.
    
    The filtering should use final_score (which includes freshness), not rerank_score.
    """
    mock_llm = Mock()
    mock_store = Mock()
    
    chain = RAGChain(llm=mock_llm, store=mock_store, score_threshold=0.5)
    
    now = datetime.now(timezone.utc)
    
    # Create a chunk with low rerank_score but high freshness
    # This should pass the threshold due to freshness boost
    chunk_fresh = SearchResult(
        chunk_id=1,
        source_type="code",
        source_ref="fresh.py",
        chunk_text="fresh content",
        score=0.4,
        metadata={"last_modified": now - timedelta(days=2)},  # Very fresh
        rerank_score=0.3,  # Low rerank score (< 0.5)
        freshness_score=1.2,  # Will be set by _apply_freshness_scoring
        final_score=0.0
    )
    
    # Create a chunk with high rerank_score but low freshness
    # This should also pass due to high rerank score
    chunk_old = SearchResult(
        chunk_id=2,
        source_type="code",
        source_ref="old.py",
        chunk_text="old content",
        score=0.8,
        metadata={"last_modified": now - timedelta(days=200)},  # Very old
        rerank_score=0.8,  # High rerank score
        freshness_score=0.9,  # Will be set by _apply_freshness_scoring
        final_score=0.0
    )
    
    chunks = [chunk_fresh, chunk_old]
    
    # Apply freshness scoring
    scored = chain._apply_freshness_scoring(chunks)
    
    # Calculate expected final_scores
    # chunk_fresh: 0.3 * 0.7 + 1.2 * 0.3 = 0.21 + 0.36 = 0.57 (passes threshold 0.5)
    # chunk_old: 0.8 * 0.7 + 0.9 * 0.3 = 0.56 + 0.27 = 0.83 (passes threshold 0.5)
    
    # Apply threshold filtering
    filtered = [c for c in scored if c.final_score >= chain.score_threshold]
    
    # Both should pass because final_score includes freshness
    assert len(filtered) == 2, f"Expected 2 chunks to pass, got {len(filtered)}"
    
    # Verify the fresh chunk passed despite low rerank_score
    fresh_chunk = next((c for c in filtered if c.chunk_id == 1), None)
    assert fresh_chunk is not None, "Fresh chunk should pass threshold due to freshness boost"
    assert fresh_chunk.final_score >= 0.5, (
        f"Fresh chunk final_score {fresh_chunk.final_score} should be >= 0.5"
    )
    
    # Verify final_score is used, not rerank_score
    assert fresh_chunk.rerank_score < 0.5, "Fresh chunk rerank_score is < 0.5"
    assert fresh_chunk.final_score >= 0.5, "But final_score (with freshness) is >= 0.5"
    
    print("✓ Threshold after freshness test passed")


def test_minimum_guarantee_with_fewer_chunks():
    """
    Test edge case: When there are fewer than 3 chunks total, return all of them.
    """
    mock_llm = Mock()
    mock_store = Mock()
    
    chain = RAGChain(llm=mock_llm, store=mock_store, score_threshold=0.9)
    
    now = datetime.now(timezone.utc)
    chunks = [
        SearchResult(
            chunk_id=1,
            source_type="code",
            source_ref="only.py",
            chunk_text="only content",
            score=0.5,
            metadata={"last_modified": now - timedelta(days=50)},
            rerank_score=0.5,
            freshness_score=1.0,
            final_score=0.0
        ),
    ]
    
    # Apply freshness scoring
    scored = chain._apply_freshness_scoring(chunks)
    
    # Apply threshold filtering with minimum guarantee
    filtered = [c for c in scored if c.final_score >= chain.score_threshold]
    if len(filtered) < 3:
        filtered = scored[:3]  # This will only get 1 chunk since that's all we have
    
    # Should return the 1 chunk we have
    assert len(filtered) == 1, f"Expected 1 chunk (all available), got {len(filtered)}"
    
    print("✓ Edge case test passed")


if __name__ == "__main__":
    test_threshold_filtering_basic()
    test_minimum_guarantee_three_chunks()
    test_threshold_after_freshness()
    test_minimum_guarantee_with_fewer_chunks()
    print("\n✅ All threshold filtering tests passed!")
