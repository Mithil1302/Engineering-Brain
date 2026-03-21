import express from 'express';
import pino from 'pino';
import net from 'net';
import { healthClient, makeHealthRequest } from './grpc-client.js';
import { startOtel } from './otel.js';

const app = express();
const log = pino();
const port = process.env.PORT || 3000;

// Start OTel SDK
startOtel().catch((err) => {
  console.error('OTel start failed', err);
});

app.get('/healthz', (req, res) => {
  res.json({ status: 'ok', service: 'api-gateway' });
});

// Simple TCP reachability check
const checkPort = (host, port, timeout = 1000) =>
  new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    const onDone = (ok, error) => {
      socket.destroy();
      resolve({ ok, error });
    };
    socket.setTimeout(timeout);
    socket.on('connect', () => onDone(true));
    socket.on('timeout', () => onDone(false, 'timeout'));
    socket.on('error', (err) => onDone(false, err.message));
  });

// HTTP health check helper
const checkHttp = async (url) => {
  try {
    const res = await fetch(url, { method: 'GET' });
    return { ok: res.ok, status: res.status };
  } catch (err) {
    return { ok: false, error: err.message };
  }
};

app.get('/mesh', async (_req, res) => {
  const checks = {
    kafka: await checkPort('kafka', 9092),
    neo4j: await checkPort('neo4j', 7687),
    qdrant: await checkPort('qdrant', 6333),
    postgres: await checkPort('postgres', 5432),
    ingestion: await checkHttp('http://ingestion-service:3001/healthz'),
    graph: await checkHttp('http://graph-service:8001/healthz'),
    agent: await checkHttp('http://agent-service:8002/healthz'),
    worker: await checkHttp('http://worker-service:8003/healthz'),
  };

  // gRPC health check to graph-service
  const grpcHealth = await new Promise((resolve) => {
    healthClient.check(makeHealthRequest('graph-service'), (err, resp) => {
      if (err) return resolve({ ok: false, error: err.message });
      const status = resp?.getStatus ? resp.getStatus() : 'UNKNOWN';
      return resolve({ ok: status === 'SERVING', status });
    });
  });
  checks.graph_grpc = grpcHealth;

  const ok = Object.values(checks).every((c) => c.ok);
  res.status(ok ? 200 : 503).json({ ok, checks });
});

app.listen(port, () => {
  log.info({ port }, 'api-gateway listening');
});
