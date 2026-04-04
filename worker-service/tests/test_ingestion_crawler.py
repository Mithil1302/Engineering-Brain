"""
Tests for GitHubRepoCrawler (Task 1.1)
"""
import pytest
import asyncio
import base64
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from worker_service.app.ingestion.crawler import GitHubRepoCrawler, FileContent, RepoCrawlResult


@pytest.fixture
def mock_private_key():
    """Mock RSA private key for testing"""
    return """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF0K3j8N8K8TlJF3dVzJvKq3cXHqL
-----END RSA PRIVATE KEY-----"""


@pytest.fixture
def crawler(mock_private_key):
    """Create a GitHubRepoCrawler instance for testing"""
    return GitHubRepoCrawler(
        app_id="12345",
        private_key=mock_private_key,
        installation_id="67890",
        max_concurrent=5,
        max_file_size_kb=100,
    )


class TestGitHubRepoCrawler:
    """Test suite for GitHubRepoCrawler"""

    def test_extension_whitelist(self, crawler):
        """Test that EXTENSION_WHITELIST contains all required extensions"""
        expected = {".py", ".ts", ".js", ".go", ".java", ".yaml", ".yml", 
                   ".json", ".md", ".proto", ".tf", ".sql"}
        assert crawler.EXTENSION_WHITELIST == expected

    def test_path_blacklist(self, crawler):
        """Test that PATH_BLACKLIST contains all required patterns"""
        expected = {"node_modules/", ".git/", "dist/", "build/", 
                   "__pycache__/", "vendor/", "coverage/", ".next/", ".nuxt/"}
        assert crawler.PATH_BLACKLIST == expected

    def test_should_include_file_valid(self, crawler):
        """Test file inclusion for valid files"""
        assert crawler._should_include_file("src/main.py", 1000) is True
        assert crawler._should_include_file("api/routes.ts", 5000) is True
        assert crawler._should_include_file("README.md", 2000) is True

    def test_should_include_file_invalid_extension(self, crawler):
        """Test file exclusion for invalid extensions"""
        assert crawler._should_include_file("image.png", 1000) is False
        assert crawler._should_include_file("binary.exe", 1000) is False

    def test_should_include_file_blacklisted_path(self, crawler):
        """Test file exclusion for blacklisted paths"""
        assert crawler._should_include_file("node_modules/package.json", 1000) is False
        assert crawler._should_include_file(".git/config", 1000) is False
        assert crawler._should_include_file("dist/bundle.js", 1000) is False
        assert crawler._should_include_file(".next/cache/data.json", 1000) is False

    def test_should_include_file_size_exceeded(self, crawler):
        """Test file exclusion when size exceeds limit"""
        # max_file_size_kb=100 means 102400 bytes
        assert crawler._should_include_file("large.py", 102401) is False
        assert crawler._should_include_file("ok.py", 102400) is True

    def test_create_jwt(self, crawler):
        """Test JWT creation with correct payload structure"""
        with patch('time.time', return_value=1000000):
            jwt_token = crawler._create_jwt()
            assert isinstance(jwt_token, str)
            assert len(jwt_token) > 0
            # JWT should have 3 parts separated by dots
            parts = jwt_token.split('.')
            assert len(parts) == 3

    @pytest.mark.asyncio
    async def test_get_installation_token_caching(self, crawler):
        """Test that installation token is cached and reused"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "ghs_test_token",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            # First call should fetch token
            token1 = await crawler._get_installation_token()
            assert token1 == "ghs_test_token"
            
            # Second call should use cached token
            token2 = await crawler._get_installation_token()
            assert token2 == "ghs_test_token"
            
            # Should only call API once due to caching
            assert mock_client.return_value.__aenter__.return_value.post.call_count == 1

    @pytest.mark.asyncio
    async def test_handle_rate_limit_below_threshold(self, crawler):
        """Test rate limit handling when remaining is below 100"""
        mock_response = MagicMock()
        mock_response.headers = {
            "X-RateLimit-Remaining": "50",
            "X-RateLimit-Reset": str(int(time.time()) + 10)
        }

        with patch('asyncio.sleep') as mock_sleep:
            await crawler._handle_rate_limit(mock_response)
            # Should sleep when remaining < 100
            assert mock_sleep.called
            # Sleep time should be reset_time - now + 5 seconds buffer
            call_args = mock_sleep.call_args[0][0]
            assert call_args >= 10  # At least 10 seconds (plus 5 second buffer)

    @pytest.mark.asyncio
    async def test_handle_rate_limit_above_threshold(self, crawler):
        """Test rate limit handling when remaining is above 100"""
        mock_response = MagicMock()
        mock_response.headers = {
            "X-RateLimit-Remaining": "500",
            "X-RateLimit-Reset": str(int(time.time()) + 3600)
        }

        with patch('asyncio.sleep') as mock_sleep:
            await crawler._handle_rate_limit(mock_response)
            # Should not sleep when remaining >= 100
            assert not mock_sleep.called

    @pytest.mark.asyncio
    async def test_fetch_file_content_success(self, crawler):
        """Test successful file content fetch"""
        content = "print('hello world')"
        encoded_content = base64.b64encode(content.encode()).decode()
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": encoded_content,
            "size": len(content),
            "sha": "abc123"
        }
        mock_response.headers = {
            "X-RateLimit-Remaining": "5000",
            "X-RateLimit-Reset": str(int(time.time()) + 3600)
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await crawler._fetch_file_content("owner/repo", "test.py", "token")
            
            assert result is not None
            assert result.path == "test.py"
            assert result.content == content
            assert result.extension == ".py"
            assert result.sha == "abc123"

    @pytest.mark.asyncio
    async def test_fetch_file_content_404(self, crawler):
        """Test file content fetch returns None on 404"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {
            "X-RateLimit-Remaining": "5000",
            "X-RateLimit-Reset": str(int(time.time()) + 3600)
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await crawler._fetch_file_content("owner/repo", "missing.py", "token")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_file_content_size_exceeded(self, crawler):
        """Test file content fetch returns None when size exceeds limit"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": base64.b64encode(b"x" * 200000).decode(),
            "size": 200000,  # Exceeds 100KB limit
            "sha": "abc123"
        }
        mock_response.headers = {
            "X-RateLimit-Remaining": "5000",
            "X-RateLimit-Reset": str(int(time.time()) + 3600)
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            result = await crawler._fetch_file_content("owner/repo", "large.py", "token")
            
            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_file_content_exponential_backoff(self, crawler):
        """Test exponential backoff on 429 responses"""
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 60)
        }

        with patch('httpx.AsyncClient') as mock_client, \
             patch('asyncio.sleep') as mock_sleep:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response_429)
            
            result = await crawler._fetch_file_content("owner/repo", "test.py", "token")
            
            # Should return None after max retries
            assert result is None
            # Should have called sleep with exponential backoff
            assert mock_sleep.call_count == 5  # 5 retry attempts

    @pytest.mark.asyncio
    async def test_crawl_repo_full_mode(self, crawler):
        """Test full repository crawl (changed_files=None)"""
        mock_token = "ghs_test_token"
        
        # Mock token fetch
        with patch.object(crawler, '_get_installation_token', return_value=mock_token), \
             patch.object(crawler, '_get_default_branch', return_value='main'), \
             patch.object(crawler, '_get_branch_sha', return_value='sha123'), \
             patch.object(crawler, '_fetch_tree', return_value=[
                 {"path": "src/main.py", "type": "blob"},
                 {"path": "README.md", "type": "blob"}
             ]), \
             patch.object(crawler, '_fetch_file_content', side_effect=[
                 FileContent("src/main.py", "code", ".py", 100, "sha1", None),
                 FileContent("README.md", "docs", ".md", 50, "sha2", None)
             ]):
            
            result = await crawler.crawl_repo("owner/repo", changed_files=None)
            
            assert isinstance(result, RepoCrawlResult)
            assert result.repo == "owner/repo"
            assert result.default_branch == "main"
            assert result.total_files == 2
            assert len(result.files) == 2

    @pytest.mark.asyncio
    async def test_crawl_repo_incremental_mode(self, crawler):
        """Test incremental repository crawl (changed_files provided)"""
        mock_token = "ghs_test_token"
        changed_files = ["src/updated.py", "docs/new.md"]
        
        with patch.object(crawler, '_get_installation_token', return_value=mock_token), \
             patch.object(crawler, '_get_default_branch', return_value='main'), \
             patch.object(crawler, '_get_branch_sha', return_value='sha123'), \
             patch.object(crawler, '_fetch_file_content', side_effect=[
                 FileContent("src/updated.py", "code", ".py", 100, "sha1", None),
                 FileContent("docs/new.md", "docs", ".md", 50, "sha2", None)
             ]):
            
            result = await crawler.crawl_repo("owner/repo", changed_files=changed_files)
            
            assert isinstance(result, RepoCrawlResult)
            assert result.total_files == 2
            # Should not call _fetch_tree in incremental mode
            assert len(result.files) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
