import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { Resource } from '@opentelemetry/resources';
import { SemanticResourceAttributes } from '@opentelemetry/semantic-conventions';

const exporter = new OTLPTraceExporter({});

const sdk = new NodeSDK({
  traceExporter: exporter,
  resource: new Resource({
    [SemanticResourceAttributes.SERVICE_NAME]: 'ingestion-service',
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

export const startOtel = async () => {
  await sdk.start();
};

process.on('SIGTERM', () => {
  sdk.shutdown();
});
