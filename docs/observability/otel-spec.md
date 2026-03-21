# Observability Spec

## Logging
- Structured JSON: trace_id, span_id, correlation_id, event_type, repo, service, request_id, rule_id, severity, message, timestamp.

## Metrics (Prometheus)
- ingestion_lag_seconds
- drift_findings_total (by severity)
- impact_job_latency_seconds (histogram)
- pr_checks_total (by status)
- kafka_consumer_lag

## Tracing (OpenTelemetry)
- Propagate trace context across API → ingestion → graph → agent.
- Export to Jaeger; sampling defaults TBD.

## Dashboards
- See dashboards.md for panel definitions.
