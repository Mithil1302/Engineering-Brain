import os
import logging

log = logging.getLogger("worker-service.otel")


def setup_otel(app, service_name: str = "worker-service"):
    """
    Set up OpenTelemetry tracing.

    OTEL is only activated when OTEL_EXPORTER_OTLP_ENDPOINT is explicitly
    set (e.g. pointing at a Jaeger or Tempo collector).  Without the env var
    the service falls back to a no-op tracer so every endpoint still works
    even without a collector running.
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()

    if not endpoint:
        log.info(
            "OTEL_EXPORTER_OTLP_ENDPOINT not set — OpenTelemetry tracing disabled. "
            "Set this variable to enable distributed tracing."
        )
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        RequestsInstrumentor().instrument()
        GrpcInstrumentorClient().instrument()
        GrpcInstrumentorServer().instrument()
        log.info("OpenTelemetry tracing enabled — exporting to %s", endpoint)
    except Exception as exc:
        log.warning("OpenTelemetry setup failed (non-fatal): %s", exc)
