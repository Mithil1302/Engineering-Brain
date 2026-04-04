@echo off
echo ================================================================================
echo Checking Docker Services and Database
echo ================================================================================
echo.

echo [1] Checking running containers...
echo --------------------------------------------------------------------------------
docker-compose ps
echo.

echo [2] Checking PostgreSQL connection...
echo --------------------------------------------------------------------------------
docker-compose exec -T postgres psql -U brain -d brain -c "SELECT version();"
echo.

echo [3] Listing all schemas...
echo --------------------------------------------------------------------------------
docker-compose exec -T postgres psql -U brain -d brain -c "\dn"
echo.

echo [4] Checking if meta schema exists...
echo --------------------------------------------------------------------------------
docker-compose exec -T postgres psql -U brain -d brain -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'meta';"
echo.

echo [5] Listing tables in meta schema...
echo --------------------------------------------------------------------------------
docker-compose exec -T postgres psql -U brain -d brain -c "\dt meta.*"
echo.

echo [6] Checking if meta.embeddings table exists...
echo --------------------------------------------------------------------------------
docker-compose exec -T postgres psql -U brain -d brain -c "\d meta.embeddings"
echo.

echo [7] Checking worker-service logs for migration info...
echo --------------------------------------------------------------------------------
docker-compose logs worker-service | findstr /i "migration schema"
echo.

echo [8] Testing backend endpoints...
echo --------------------------------------------------------------------------------
echo Worker Service (http://localhost:8003):
curl -s http://localhost:8003/healthz
echo.
echo.
echo Agent Service (http://localhost:8002):
curl -s http://localhost:8002/healthz
echo.
echo.
echo Graph Service (http://localhost:8001):
curl -s http://localhost:8001/healthz
echo.
echo.

echo [9] Neo4j Browser Access:
echo --------------------------------------------------------------------------------
echo URL: http://localhost:7474
echo Username: neo4j
echo Password: testtest
echo.

echo ================================================================================
echo Check complete!
echo ================================================================================
