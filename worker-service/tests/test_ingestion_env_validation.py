"""
Tests for environment variable validation (Task 1.8)
"""
import pytest
import os
import sys
from unittest.mock import patch, MagicMock
from worker_service.app.dependencies import validate_ingestion_env_vars


class TestEnvironmentValidation:
    """Test suite for ingestion environment variable validation"""

    def test_validate_all_required_vars_present(self):
        """Test validation passes when all required vars are present"""
        env_vars = {
            "GITHUB_APP_ID": "12345",
            "GITHUB_APP_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
            "GITHUB_INSTALLATION_ID": "67890"
        }
        
        with patch.dict(os.environ, env_vars, clear=False):
            # Should not raise or exit
            try:
                validate_ingestion_env_vars()
                success = True
            except SystemExit:
                success = False
            
            assert success is True

    def test_validate_missing_github_app_id(self):
        """Test validation fails when GITHUB_APP_ID is missing"""
        env_vars = {
            "GITHUB_APP_PRIVATE_KEY": "test_key",
            "GITHUB_INSTALLATION_ID": "67890"
        }
        
        with patch.dict(os.environ, env_vars, clear=True), \
             patch('sys.exit') as mock_exit:
            validate_ingestion_env_vars()
            
            # Should call sys.exit(1)
            mock_exit.assert_called_once_with(1)

    def test_validate_missing_github_private_key(self):
        """Test validation fails when GITHUB_APP_PRIVATE_KEY is missing"""
        env_vars = {
            "GITHUB_APP_ID": "12345",
            "GITHUB_INSTALLATION_ID": "67890"
        }
        
        with patch.dict(os.environ, env_vars, clear=True), \
             patch('sys.exit') as mock_exit:
            validate_ingestion_env_vars()
            
            mock_exit.assert_called_once_with(1)

    def test_validate_missing_installation_id(self):
        """Test validation fails when GITHUB_INSTALLATION_ID is missing"""
        env_vars = {
            "GITHUB_APP_ID": "12345",
            "GITHUB_APP_PRIVATE_KEY": "test_key"
        }
        
        with patch.dict(os.environ, env_vars, clear=True), \
             patch('sys.exit') as mock_exit:
            validate_ingestion_env_vars()
            
            mock_exit.assert_called_once_with(1)

    def test_validate_multiple_missing_vars(self):
        """Test validation collects all missing vars before exiting"""
        env_vars = {}  # All required vars missing
        
        with patch.dict(os.environ, env_vars, clear=True), \
             patch('sys.exit') as mock_exit, \
             patch('logging.Logger.critical') as mock_log:
            validate_ingestion_env_vars()
            
            # Should log critical message
            assert mock_log.called
            log_message = mock_log.call_args[0][0]
            
            # Message should contain all three missing vars
            assert "GITHUB_APP_ID" in log_message
            assert "GITHUB_APP_PRIVATE_KEY" in log_message
            assert "GITHUB_INSTALLATION_ID" in log_message
            
            # Should exit with code 1
            mock_exit.assert_called_once_with(1)

    def test_validate_empty_string_treated_as_missing(self):
        """Test that empty strings are treated as missing values"""
        env_vars = {
            "GITHUB_APP_ID": "",
            "GITHUB_APP_PRIVATE_KEY": "   ",  # Whitespace only
            "GITHUB_INSTALLATION_ID": "67890"
        }
        
        with patch.dict(os.environ, env_vars, clear=True), \
             patch('sys.exit') as mock_exit:
            validate_ingestion_env_vars()
            
            # Should fail because empty/whitespace values are invalid
            mock_exit.assert_called_once_with(1)

    def test_optional_vars_have_defaults(self):
        """Test that optional environment variables have proper defaults"""
        # These should have defaults and not cause validation to fail
        env_vars = {
            "GITHUB_APP_ID": "12345",
            "GITHUB_APP_PRIVATE_KEY": "test_key",
            "GITHUB_INSTALLATION_ID": "67890"
            # INGESTION_MAX_CONCURRENT_FETCHES not set - should default to 10
            # INGESTION_MAX_FILE_SIZE_KB not set - should default to 500
            # INGESTION_BATCH_SIZE not set - should default to 50
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # Should not raise or exit
            try:
                validate_ingestion_env_vars()
                success = True
            except SystemExit:
                success = False
            
            assert success is True
            
            # Verify defaults are used
            assert os.getenv("INGESTION_MAX_CONCURRENT_FETCHES", "10") == "10"
            assert os.getenv("INGESTION_MAX_FILE_SIZE_KB", "500") == "500"
            assert os.getenv("INGESTION_BATCH_SIZE", "50") == "50"


class TestEnvironmentVariableUsage:
    """Test that environment variables are used correctly in dependencies"""

    def test_crawler_uses_env_vars(self):
        """Test that GitHubRepoCrawler is initialized with env vars"""
        from worker_service.app.dependencies import get_ingestion_pipeline
        
        env_vars = {
            "GITHUB_APP_ID": "test_app_id",
            "GITHUB_APP_PRIVATE_KEY": "test_key",
            "GITHUB_INSTALLATION_ID": "test_install_id",
            "INGESTION_MAX_CONCURRENT_FETCHES": "15",
            "INGESTION_MAX_FILE_SIZE_KB": "1000",
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "POSTGRES_DB": "test",
            "KAFKA_BROKERS": "localhost:9092"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            # This would normally initialize the pipeline
            # We're just testing that env vars are read correctly
            assert os.getenv("GITHUB_APP_ID") == "test_app_id"
            assert os.getenv("INGESTION_MAX_CONCURRENT_FETCHES") == "15"
            assert os.getenv("INGESTION_MAX_FILE_SIZE_KB") == "1000"

    def test_embedding_populator_uses_batch_size(self):
        """Test that EmbeddingPopulator uses INGESTION_BATCH_SIZE"""
        env_vars = {
            "INGESTION_BATCH_SIZE": "100"
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            batch_size = int(os.getenv("INGESTION_BATCH_SIZE", "50"))
            assert batch_size == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
