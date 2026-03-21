# Proto Tooling

## Node stub generation
```
npm install
npm run gen:node
```
Outputs to `proto/node/` using `grpc_tools_node_protoc` (adjust import paths per service).

> Note (Windows + spaces in path): grpc-tools/protoc can fail when the repository path contains spaces. If that happens, run from WSL or a path without spaces, or invoke protoc with fully quoted paths. Python stubs are generated and checked in; regenerate Node stubs in a space-free path if needed.

## Python stub generation
```
pip install -e .
python -m grpc_tools.protoc \
  -I. \
  --python_out=python \
  --grpc_python_out=python \
  services.proto
```
Outputs to `proto/python/`.
