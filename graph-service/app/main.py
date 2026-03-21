from fastapi import FastAPI
import threading
from .health_server import serve as start_health, graph_store
from .otel_setup import setup_otel

app = FastAPI(title="graph-service")

# Init OTel
setup_otel(app)

@app.get("/healthz")
def healthz():
    ready = graph_store.is_ready()
    return {
        "status": "ok" if ready else "degraded",
        "service": "graph-service",
        "neo4j_ready": ready,
    }


# Start gRPC health server in background thread
def _start_grpc_health():
    server = start_health()
    server.wait_for_termination()


threading.Thread(target=_start_grpc_health, daemon=True).start()
