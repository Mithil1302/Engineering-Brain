"""
Tests for CodeChunker (Task 1.2)
"""
import pytest
from worker_service.app.ingestion.chunker import CodeChunker, Chunk
from worker_service.app.ingestion.crawler import FileContent


@pytest.fixture
def chunker():
    """Create a CodeChunker instance for testing"""
    return CodeChunker(max_chunk_chars=2000)


class TestCodeChunker:
    """Test suite for CodeChunker"""

    def test_compute_chunk_id_consistency(self, chunker):
        """Test that chunk_id is computed consistently"""
        chunk_id1 = chunker._compute_chunk_id("owner/repo", "src/main.py", "def hello(): pass")
        chunk_id2 = chunker._compute_chunk_id("owner/repo", "src/main.py", "def hello(): pass")
        chunk_id3 = chunker._compute_chunk_id("owner/repo", "src/main.py", "def world(): pass")
        
        # Same inputs should produce same hash
        assert chunk_id1 == chunk_id2
        # Different content should produce different hash
        assert chunk_id1 != chunk_id3
        # Should be SHA-256 (64 hex characters)
        assert len(chunk_id1) == 64

    def test_extract_python_functions(self, chunker):
        """Test Python function extraction using AST"""
        file = FileContent(
            path="test.py",
            content='''def hello():
    """Say hello"""
    print("hello")

def world():
    """Say world"""
    print("world")
''',
            extension=".py",
            size_bytes=100,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_python(file)
        
        assert len(chunks) == 2
        assert chunks[0].metadata["name"] == "hello"
        assert chunks[0].metadata["type"] == "function"
        assert "Say hello" in chunks[0].metadata["docstring"]
        assert chunks[1].metadata["name"] == "world"

    def test_extract_python_classes(self, chunker):
        """Test Python class extraction using AST"""
        file = FileContent(
            path="test.py",
            content='''class MyClass:
    """A test class"""
    def method(self):
        pass
''',
            extension=".py",
            size_bytes=100,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_python(file)
        
        assert len(chunks) == 1
        assert chunks[0].metadata["name"] == "MyClass"
        assert chunks[0].metadata["type"] == "class"
        assert "test class" in chunks[0].metadata["docstring"]

    def test_extract_python_syntax_error_fallback(self, chunker):
        """Test that syntax errors fall back to sliding window"""
        file = FileContent(
            path="test.py",
            content="def broken(\n    incomplete syntax",
            extension=".py",
            size_bytes=50,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_python(file)
        
        # Should fall back to sliding window
        assert len(chunks) >= 1
        assert chunks[0].source_type == "code"

    def test_extract_typescript_declarations(self, chunker):
        """Test TypeScript/JavaScript declaration extraction"""
        file = FileContent(
            path="test.ts",
            content='''export function hello() {
    console.log("hello");
}

export class MyClass {
    constructor() {}
}

interface MyInterface {
    name: string;
}
''',
            extension=".ts",
            size_bytes=200,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_typescript(file)
        
        assert len(chunks) >= 3
        names = [c.metadata["name"] for c in chunks]
        assert "hello" in names
        assert "MyClass" in names
        assert "MyInterface" in names

    def test_extract_go_functions(self, chunker):
        """Test Go function extraction"""
        file = FileContent(
            path="test.go",
            content='''func Hello() {
    fmt.Println("hello")
}

func (r *Receiver) Method() {
    fmt.Println("method")
}

type MyStruct struct {
    Name string
}
''',
            extension=".go",
            size_bytes=200,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_go(file)
        
        assert len(chunks) >= 3
        # Check for function with receiver
        method_chunk = [c for c in chunks if c.metadata.get("name") == "Method"]
        assert len(method_chunk) > 0
        assert method_chunk[0].metadata.get("receiver_type") is not None

    def test_extract_markdown_sections(self, chunker):
        """Test Markdown section extraction"""
        file = FileContent(
            path="README.md",
            content='''# Main Title

Some intro text.

## Section One

Content for section one.

### Subsection

More content.

## Section Two

Content for section two.
''',
            extension=".md",
            size_bytes=200,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_markdown(file)
        
        assert len(chunks) >= 3
        titles = [c.metadata["section_title"] for c in chunks]
        assert "Section One" in titles
        assert "Section Two" in titles

    def test_extract_yaml_openapi(self, chunker):
        """Test OpenAPI spec extraction from YAML"""
        file = FileContent(
            path="openapi.yaml",
            content='''openapi: 3.0.0
info:
  title: Test API
paths:
  /users:
    get:
      operationId: getUsers
      tags: [users]
    post:
      operationId: createUser
      tags: [users]
      deprecated: true
''',
            extension=".yaml",
            size_bytes=300,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_yaml(file)
        
        assert len(chunks) == 2
        # Check GET endpoint
        get_chunk = [c for c in chunks if c.metadata.get("http_method") == "GET"]
        assert len(get_chunk) == 1
        assert get_chunk[0].metadata["path"] == "/users"
        assert get_chunk[0].source_type == "spec"
        
        # Check POST endpoint
        post_chunk = [c for c in chunks if c.metadata.get("http_method") == "POST"]
        assert len(post_chunk) == 1
        assert post_chunk[0].metadata["deprecated"] is True

    def test_extract_yaml_kubernetes(self, chunker):
        """Test Kubernetes manifest extraction"""
        file = FileContent(
            path="deployment.yaml",
            content='''apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 3
''',
            extension=".yaml",
            size_bytes=100,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_yaml(file)
        
        assert len(chunks) == 1
        assert chunks[0].source_type == "config"
        assert chunks[0].metadata["kind"] == "Deployment"
        assert chunks[0].metadata["name"] == "my-app"

    def test_extract_proto_services(self, chunker):
        """Test Protocol Buffer service extraction"""
        file = FileContent(
            path="service.proto",
            content='''syntax = "proto3";

service UserService {
  rpc GetUser(GetUserRequest) returns (User);
  rpc CreateUser(CreateUserRequest) returns (User);
}

message User {
  string id = 1;
  string name = 2;
}
''',
            extension=".proto",
            size_bytes=200,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_proto(file)
        
        assert len(chunks) >= 2
        service_chunks = [c for c in chunks if c.metadata.get("proto_type") == "service"]
        message_chunks = [c for c in chunks if c.metadata.get("proto_type") == "message"]
        assert len(service_chunks) >= 1
        assert len(message_chunks) >= 1

    def test_extract_sql_statements(self, chunker):
        """Test SQL statement extraction"""
        file = FileContent(
            path="schema.sql",
            content='''CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100)
);

CREATE INDEX idx_users_name ON users(name);

CREATE FUNCTION get_user_count() RETURNS INTEGER AS $$
BEGIN
    RETURN (SELECT COUNT(*) FROM users);
END;
$$ LANGUAGE plpgsql;
''',
            extension=".sql",
            size_bytes=300,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_sql(file)
        
        assert len(chunks) >= 3
        # Should extract CREATE TABLE, CREATE INDEX, CREATE FUNCTION
        statement_types = [c.metadata.get("statement_type") for c in chunks]
        assert "TABLE" in statement_types or "CREATE TABLE" in str(chunks)

    def test_extract_terraform_resources(self, chunker):
        """Test Terraform resource extraction"""
        file = FileContent(
            path="main.tf",
            content='''resource "aws_instance" "web" {
  ami           = "ami-12345"
  instance_type = "t2.micro"
}

resource "aws_s3_bucket" "data" {
  bucket = "my-bucket"
}
''',
            extension=".tf",
            size_bytes=200,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._extract_terraform(file)
        
        assert len(chunks) == 2
        assert chunks[0].source_type == "infra"
        resource_types = [c.metadata.get("resource_type") for c in chunks]
        assert "aws_instance" in resource_types
        assert "aws_s3_bucket" in resource_types

    def test_sliding_window_chunking(self, chunker):
        """Test sliding window fallback for unknown file types"""
        # Create a file with 100 lines
        lines = [f"line {i}" for i in range(100)]
        content = "\n".join(lines)
        
        file = FileContent(
            path="test.txt",
            extension=".txt",
            content=content,
            size_bytes=len(content),
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker._sliding_window(file)
        
        # With 50-line windows and 10-line overlap, should have multiple chunks
        assert len(chunks) > 1
        # Each chunk should have reasonable line counts
        for chunk in chunks:
            assert chunk.end_line - chunk.start_line <= 50

    def test_subdivide_large_chunk(self, chunker):
        """Test subdivision of chunks exceeding max_chunk_chars"""
        # Create a chunk larger than 2000 chars
        large_content = "x" * 5000
        large_chunk = Chunk(
            chunk_id="",
            repo="test/repo",
            file_path="large.py",
            extension=".py",
            content=large_content,
            source_type="code",
            metadata={},
            start_line=1,
            end_line=100,
            char_count=5000
        )
        
        sub_chunks = chunker._subdivide_large_chunk(large_chunk)
        
        # Should create multiple sub-chunks
        assert len(sub_chunks) > 1
        # Each sub-chunk should be <= max_chunk_chars
        for chunk in sub_chunks:
            assert chunk.char_count <= chunker.max_chunk_chars
        # All content should be preserved (with overlap)
        total_chars = sum(len(c.content) for c in sub_chunks)
        assert total_chars >= len(large_content)

    def test_chunk_files_assigns_repo_and_chunk_id(self, chunker):
        """Test that chunk_files assigns repo and chunk_id to all chunks"""
        file = FileContent(
            path="test.py",
            content="def hello(): pass",
            extension=".py",
            size_bytes=20,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker.chunk_files("owner/repo", [file])
        
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.repo == "owner/repo"
            assert chunk.chunk_id != ""
            assert len(chunk.chunk_id) == 64  # SHA-256

    def test_chunk_files_handles_extractor_failure(self, chunker):
        """Test that chunk_files falls back to sliding window on extractor failure"""
        # Create a Python file that will cause AST to fail
        file = FileContent(
            path="broken.py",
            content="def broken(\n    incomplete",
            extension=".py",
            size_bytes=30,
            sha="abc",
            last_modified=None
        )
        
        chunks = chunker.chunk_files("owner/repo", [file])
        
        # Should still produce chunks via sliding window fallback
        assert len(chunks) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
