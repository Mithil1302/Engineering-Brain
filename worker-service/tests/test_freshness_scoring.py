"""
Test freshness scoring thresholds in RAG chain.
"""
from datetime import datetime, timedelta, timezone
from app.llm.chains import RAGChain
from app.llm.embeddings import SearchResult


def test_freshness_thresholds():
    """
    Verify freshness scoring thresholds are applied correctly:
    - age_days <= 7 → 1.2
    - age_days <= 30 → 1.1
    - age_days <= 90 → 1.0
    - age_days > 90 → 0.9
    
    Thresholds are inclusive on the lower bound.
    """
    now = datetime.now(timezone.utc)
    
    # Create test chunks with different ages
    test_cases = [
        # (age_days, expected_freshness_score, description)
        (0, 1.2, "today"),
        (7, 1.2, "exactly 7 days (inclusive)"),
        (8, 1.1, "8 days"),
        (30, 1.1, "exactly 30 days (inclusive)"),
        (31, 1.0, "31 days"),
        (90, 1.0, "exactly 90 days (inclusive)"),
        (91, 0.9, "91 days"),
        (365, 0.9, "1 year old"),
    ]
    
    for age_days, expected_score, description in test_cases:
        last_modified = now - timedelta(days=age_days)
        
        chunk = SearchResult(
            chunk_id=1,
            source_type="code",
            source_ref="test.py",
            chunk_text="test content",
            score=0.8,
            metadata={"last_modified": last_modified},
            rerank_score=0.9,
            freshness_score=1.0,
            final_score=0.0
        )
        
        # Create a minimal RAGChain instance (we only need the method)
        chain = RAGChain(llm=None, store=None)
        
        # Apply freshness scoring
        scored = chain._apply_freshness_scoring([chunk])
        
        # Verify the freshness score
        assert scored[0].freshness_score == expected_score, (
            f"Failed for {description}: expected {expected_score}, "
            f"got {scored[0].freshness_score}"
        )
        
        # Verify final_score calculation
        expected_final = (chunk.rerank_score * 0.7) + (expected_score * 0.3)
        assert abs(scored[0].final_score - expected_final) < 0.001, (
            f"Failed final_score for {description}: expected {expected_final}, "
            f"got {scored[0].final_score}"
        )
    
    print("✓ All freshness threshold tests passed")


def test_freshness_missing_timestamp():
    """Verify that missing last_modified defaults to neutral score 1.0"""
    chunk = SearchResult(
        chunk_id=1,
        source_type="code",
        source_ref="test.py",
        chunk_text="test content",
        score=0.8,
        metadata={},  # No last_modified
        rerank_score=0.9,
        freshness_score=1.0,
        final_score=0.0
    )
    
    chain = RAGChain(llm=None, store=None)
    scored = chain._apply_freshness_scoring([chunk])
    
    assert scored[0].freshness_score == 1.0, (
        f"Missing timestamp should default to 1.0, got {scored[0].freshness_score}"
    )
    
    print("✓ Missing timestamp test passed")


def test_freshness_sorting():
    """Verify chunks are sorted by final_score descending"""
    now = datetime.now(timezone.utc)
    
    chunks = [
        SearchResult(
            chunk_id=1,
            source_type="code",
            source_ref="old.py",
            chunk_text="old content",
            score=0.8,
            metadata={"last_modified": now - timedelta(days=100)},  # Old: 0.9
            rerank_score=0.5,  # Low rerank
            freshness_score=1.0,
            final_score=0.0
        ),
        SearchResult(
            chunk_id=2,
            source_type="code",
            source_ref="fresh.py",
            chunk_text="fresh content",
            score=0.8,
            metadata={"last_modified": now - timedelta(days=5)},  # Fresh: 1.2
            rerank_score=0.7,  # Medium rerank
            freshness_score=1.0,
            final_score=0.0
        ),
        SearchResult(
            chunk_id=3,
            source_type="code",
            source_ref="medium.py",
            chunk_text="medium content",
            score=0.8,
            metadata={"last_modified": now - timedelta(days=50)},  # Medium: 1.0
            rerank_score=0.6,  # Medium rerank
            freshness_score=1.0,
            final_score=0.0
        ),
    ]
    
    chain = RAGChain(llm=None, store=None)
    scored = chain._apply_freshness_scoring(chunks)
    
    # Verify sorting: highest final_score first
    assert scored[0].chunk_id == 2, "Fresh content with good rerank should be first"
    assert scored[0].final_score > scored[1].final_score, "Scores should be descending"
    assert scored[1].final_score > scored[2].final_score, "Scores should be descending"
    
    print("✓ Sorting test passed")


if __name__ == "__main__":
    test_freshness_thresholds()
    test_freshness_missing_timestamp()
    test_freshness_sorting()
    print("\n✅ All freshness scoring tests passed!")
