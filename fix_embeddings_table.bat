@echo off
echo ================================================================================
echo Creating meta.embeddings table manually
echo ================================================================================
echo.

echo [1] Enabling pgvector extension...
docker-compose exec -T postgres psql -U brain -d brain -c "CREATE EXTENSION IF NOT EXISTS vector;"
echo.

echo [2] Creating meta.embeddings table...
docker-compose exec -T postgres psql -U brain -d brain -c "CREATE TABLE IF NOT EXISTS meta.embeddings (id BIGSERIAL PRIMARY KEY, source_type TEXT NOT NULL, source_ref TEXT NOT NULL, chunk_index INT NOT NULL DEFAULT 0, chunk_text TEXT NOT NULL, embedding vector(3072) NOT NULL, metadata JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE (source_type, source_ref, chunk_index));"
echo.

echo [3] Creating indexes...
docker-compose exec -T postgres psql -U brain -d brain -c "CREATE INDEX IF NOT EXISTS idx_embeddings_source ON meta.embeddings (source_type, source_ref);"
echo.

docker-compose exec -T postgres psql -U brain -d brain -c "CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw ON meta.embeddings USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
echo.

echo [4] Verifying table creation...
docker-compose exec -T postgres psql -U brain -d brain -c "\d meta.embeddings"
echo.

echo ================================================================================
echo Done! Now retry your ingestion test.
echo ================================================================================
