from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer

def setup_otel(app, service_name: str = "worker-service"):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter()
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    GrpcInstrumentorClient().instrument()
    GrpcInstrumentorServer().instrument()
