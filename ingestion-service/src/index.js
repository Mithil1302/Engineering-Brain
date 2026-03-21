import express from 'express';
import pino from 'pino';
import crypto from 'crypto';
import path from 'path';
import grpc from '@grpc/grpc-js';
import protoLoader from '@grpc/proto-loader';
import { Kafka } from 'kafkajs';
import pg from 'pg';
import { startOtel } from './otel.js';

const { Pool } = pg;

const app = express();
const log = pino();
const port = process.env.PORT || 3001;

app.use(express.json({ limit: '1mb' }));

const config = {
  kafkaBrokers: (process.env.KAFKA_BROKERS || 'kafka:9092').split(','),
  sourceTopic: process.env.KAFKA_SOURCE_TOPIC || 'repo.events',
  dlqTopic: process.env.KAFKA_DLQ_TOPIC || 'repo.events.dlq',
  graphUpdatesTopic: process.env.GRAPH_UPDATES_TOPIC || 'graph.updates',
  analysisJobsTopic: process.env.ANALYSIS_JOBS_TOPIC || 'analysis.jobs',
  consumerGroup: process.env.KAFKA_CONSUMER_GROUP || 'ingestion-service-v1',
  graphGrpcTarget: process.env.GRAPH_GRPC_TARGET || 'graph-service:50051',
  maxProcessRetries: Number(process.env.MAX_PROCESS_RETRIES || 3),
  retryBaseDelayMs: Number(process.env.RETRY_BASE_DELAY_MS || 500),
  replayDefaultBatchSize: Number(process.env.REPLAY_DEFAULT_BATCH_SIZE || 100),
  postgres: {
    host: process.env.POSTGRES_HOST || 'postgres',
    port: Number(process.env.POSTGRES_PORT || 5432),
    user: process.env.POSTGRES_USER || 'brain',
    password: process.env.POSTGRES_PASSWORD || 'brain',
    database: process.env.POSTGRES_DB || 'brain',
    max: Number(process.env.POSTGRES_POOL_MAX || 10),
  },
  protoPath: path.join(process.cwd(), 'proto', 'services.proto'),
};

const state = {
  ready: false,
  kafkaConnected: false,
  grpcReady: false,
  consumed: 0,
  producedGraphUpdates: 0,
  producedAnalysisJobs: 0,
  producedDlq: 0,
  dedupedMessages: 0,
  quarantinedMessages: 0,
  failedMessages: 0,
  retriedMessages: 0,
  lastError: null,
};

const runtime = {
  pipelineStarted: false,
  startupInProgress: false,
};

const storage = {
  ready: false,
};

const pool = new Pool(config.postgres);

const kafka = new Kafka({
  clientId: 'ingestion-service',
  brokers: config.kafkaBrokers,
});

const consumer = kafka.consumer({
  groupId: config.consumerGroup,
  retry: { retries: 10 },
});

const producer = kafka.producer({
  allowAutoTopicCreation: false,
  retry: { retries: 10 },
});

const packageDefinition = protoLoader.loadSync(config.protoPath, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const proto = grpc.loadPackageDefinition(packageDefinition).kabrain;
const graphClient = new proto.GraphService(config.graphGrpcTarget, grpc.credentials.createInsecure());

const initStorage = async () => {
  await pool.query('SELECT 1');
  storage.ready = true;
};

const registerEventIfNew = async ({ eventKey, topic, partition, offset, correlationId, payload }) => {
  const res = await pool.query(
    `
      INSERT INTO meta.processed_events (event_key, source_topic, source_partition, source_offset, correlation_id, payload, first_seen_at)
      VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
      ON CONFLICT (event_key) DO NOTHING
      RETURNING id
    `,
    [eventKey, topic, partition, offset, correlationId, JSON.stringify(payload)]
  );
  return res.rowCount > 0;
};

const quarantinePoisonPill = async ({ sourceTopic, sourcePartition, sourceOffset, errorMessage, attempts, payloadRaw, correlationId, idempotencyKey }) => {
  const res = await pool.query(
    `
      INSERT INTO meta.poison_pills (
        source_topic,
        source_partition,
        source_offset,
        error,
        attempts,
        payload_raw,
        correlation_id,
        idempotency_key,
        status,
        created_at,
        updated_at
      )
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'quarantined',NOW(),NOW())
      RETURNING id
    `,
    [
      sourceTopic,
      sourcePartition,
      sourceOffset,
      errorMessage,
      attempts,
      payloadRaw,
      correlationId,
      idempotencyKey,
    ]
  );
  return res.rows[0]?.id;
};

const rpcApplyMutations = ({ mutations, correlationId, idempotencyKey }) =>
  new Promise((resolve, reject) => {
    const metadata = new grpc.Metadata();
    metadata.add('x-correlation-id', correlationId);
    metadata.add('x-idempotency-key', idempotencyKey);
    graphClient.ApplyMutations({ mutations }, metadata, (err, resp) => {
      if (err) return reject(err);
      return resolve(resp);
    });
  });

const safeParse = (value) => {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
};

const normalizeId = (input, fallback) => {
  if (typeof input === 'string' && input.trim().length > 0) return input.trim();
  return fallback;
};

const buildMutationSet = (payload, sourceMeta) => {
  const now = new Date().toISOString();
  const mutations = [];

  const repoId = normalizeId(payload?.repo?.id, 'repo:unknown');
  const repoPayload = {
    id: repoId,
    url: payload?.repo?.url || null,
    default_branch: payload?.repo?.default_branch || null,
    source_event_type: payload?.event_type || 'unknown',
    source_topic: sourceMeta.topic,
    source_partition: sourceMeta.partition,
    source_offset: sourceMeta.offset,
    updated_at: now,
  };

  mutations.push({
    type: 'create_node',
    entity_kind: 'repo',
    entity_id: repoId,
    payload_json: JSON.stringify(repoPayload),
    valid_from: now,
    valid_to: '',
  });

  const changedFiles = Array.isArray(payload?.changed_files) ? payload.changed_files : [];
  for (const file of changedFiles) {
    const filePath = normalizeId(file?.path, 'unknown-file');
    const entityId = `${repoId}:${filePath}`;
    mutations.push({
      type: 'update_node',
      entity_kind: 'file',
      entity_id: entityId,
      payload_json: JSON.stringify({
        path: filePath,
        status: file?.status || 'modified',
        patch_url: file?.patch_url || null,
        blob_url: file?.blob_url || null,
        repo_id: repoId,
        updated_at: now,
      }),
      valid_from: now,
      valid_to: '',
    });
  }

  const pr = payload?.pull_request;
  if (pr?.number) {
    const prId = `${repoId}:pr:${pr.number}`;
    mutations.push({
      type: 'create_node',
      entity_kind: 'pull_request',
      entity_id: prId,
      payload_json: JSON.stringify({
        number: pr.number,
        head_sha: pr.head_sha || null,
        base_sha: pr.base_sha || null,
        title: pr.title || null,
        author: pr.author || null,
        repo_id: repoId,
        updated_at: now,
      }),
      valid_from: now,
      valid_to: '',
    });
  }

  const endpointSpec = payload?.spec;
  if (endpointSpec?.hash) {
    const specId = `${repoId}:spec:${endpointSpec.hash}`;
    mutations.push({
      type: 'create_node',
      entity_kind: 'schema_version',
      entity_id: specId,
      payload_json: JSON.stringify({
        source: endpointSpec.kind || 'openapi',
        path: endpointSpec.path || null,
        uri: endpointSpec.uri || null,
        hash: endpointSpec.hash,
        repo_id: repoId,
        updated_at: now,
      }),
      valid_from: now,
      valid_to: '',
    });
  }

  return mutations;
};

const buildAnalysisJobs = (payload, correlationId, idempotencyKey) => {
  const jobs = [];
  const base = {
    schema_version: '1.0.0',
    correlation_id: correlationId,
    produced_at: new Date().toISOString(),
    target: {
      repo: payload?.repo?.id || null,
      service_id: null,
      endpoint_id: null,
      spec_hash: payload?.spec?.hash || null,
      schema_hash: payload?.db_schema?.hash || null,
    },
  };

  jobs.push({
    ...base,
    idempotency_key: `${idempotencyKey}:drift`,
    job_type: 'drift',
    parameters: {
      event_type: payload?.event_type || 'unknown',
    },
  });

  if (['pull_request', 'spec', 'schema'].includes(payload?.event_type)) {
    jobs.push({
      ...base,
      idempotency_key: `${idempotencyKey}:impact`,
      job_type: 'impact',
      parameters: {
        event_type: payload?.event_type,
      },
    });
  }

  jobs.push({
    ...base,
    idempotency_key: `${idempotencyKey}:embed_refresh`,
    job_type: 'embed_refresh',
    parameters: {
      source_topic: config.sourceTopic,
    },
  });

  return jobs;
};

const produceBatch = async (topic, messages) => {
  if (!messages.length) return;
  await producer.send({
    topic,
    messages: messages.map((value) => {
      const key = value.partition_key || value.repo_id || value.correlation_id || value.idempotency_key || null;
      return {
        key: key ? String(key) : undefined,
        value: JSON.stringify(value),
        headers: {
          'x-correlation-id': value.correlation_id || '',
          'x-idempotency-key': value.idempotency_key || '',
          'x-partition-key': key ? String(key) : '',
        },
      };
    }),
  });
};

const publishRawEvent = async (topic, payloadRaw, key = null) => {
  await producer.send({
    topic,
    messages: [
      {
        key: key || undefined,
        value: payloadRaw,
      },
    ],
  });
};

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const resetConnectivityState = () => {
  state.ready = false;
  state.kafkaConnected = false;
  state.grpcReady = false;
};

const safeDisconnectRuntime = async () => {
  try {
    await consumer.disconnect();
  } catch {}
  try {
    await producer.disconnect();
  } catch {}
};

const buildDlqEvent = ({ payloadRaw, topic, partition, offset, errorMessage, attempts, poisonPillId, correlationId, idempotencyKey }) => ({
  schema_version: '1.0.0',
  idempotency_key: `dlq:${idempotencyKey || `${topic}:${partition}:${offset}`}`,
  correlation_id:
    correlationId || crypto.createHash('sha256').update(`${topic}:${partition}:${offset}`).digest('hex').slice(0, 16),
  produced_at: new Date().toISOString(),
  partition_key: `dlq:${topic}:${partition}`,
  source: {
    topic,
    partition,
    offset,
  },
  poison_pill_id: poisonPillId || null,
  attempts,
  error: errorMessage,
  payload_raw: payloadRaw,
});

const processWithRetry = async ({ topic, partition, message }) => {
  const payloadRaw = message.value?.toString('utf8') || '';
  let lastErr = null;
  let correlationId = null;
  let idempotencyKey = `${topic}:${partition}:${message.offset}`;
  const parsed = safeParse(payloadRaw);
  if (parsed) {
    correlationId = normalizeId(
      parsed.correlation_id,
      crypto.createHash('sha256').update(`${topic}:${partition}:${message.offset}`).digest('hex').slice(0, 16)
    );
    idempotencyKey = normalizeId(parsed.idempotency_key, idempotencyKey);
  }

  for (let attempt = 1; attempt <= config.maxProcessRetries; attempt += 1) {
    try {
      if (attempt > 1) state.retriedMessages += 1;
      await processRepoEvent({ topic, partition, message });
      return;
    } catch (err) {
      lastErr = err;
      if (attempt < config.maxProcessRetries) {
        const backoff = config.retryBaseDelayMs * 2 ** (attempt - 1);
        log.warn({ topic, partition, offset: message.offset, attempt, backoff }, 'repo event processing failed, retrying');
        await delay(backoff);
      }
    }
  }

  const poisonPillId = await quarantinePoisonPill({
    sourceTopic: topic,
    sourcePartition: partition,
    sourceOffset: message.offset,
    errorMessage: lastErr?.message || 'unknown processing error',
    attempts: config.maxProcessRetries,
    payloadRaw,
    correlationId,
    idempotencyKey,
  });

  const dlqEvent = buildDlqEvent({
    payloadRaw,
    topic,
    partition,
    offset: message.offset,
    errorMessage: lastErr?.message || 'unknown processing error',
    attempts: config.maxProcessRetries,
    poisonPillId,
    correlationId,
    idempotencyKey,
  });

  await produceBatch(config.dlqTopic, [dlqEvent]);
  state.producedDlq += 1;
  state.quarantinedMessages += 1;
  state.failedMessages += 1;
  state.lastError = lastErr?.message || 'unknown processing error';
  log.error({ topic, partition, offset: message.offset, err: lastErr }, 'failed to process repo event, sent to DLQ');
};

const processRepoEvent = async ({ topic, partition, message }) => {
  const valueString = message.value?.toString('utf8') || '';
  const payload = safeParse(valueString);
  if (!payload) {
    throw new Error('Invalid JSON payload in repo.events');
  }

  const correlationId = normalizeId(
    payload.correlation_id,
    crypto.createHash('sha256').update(`${topic}:${partition}:${message.offset}`).digest('hex').slice(0, 16)
  );

  const idempotencyKey = normalizeId(payload.idempotency_key, `${topic}:${partition}:${message.offset}`);

  const isNew = await registerEventIfNew({
    eventKey: idempotencyKey,
    topic,
    partition,
    offset: message.offset,
    correlationId,
    payload,
  });

  if (!isNew) {
    state.dedupedMessages += 1;
    log.info({ topic, partition, offset: message.offset, idempotencyKey }, 'duplicate event skipped by dedupe policy');
    return;
  }

  const sourceMeta = {
    topic,
    partition,
    offset: message.offset,
  };

  const mutations = buildMutationSet(payload, sourceMeta);
  const applyResponse = await rpcApplyMutations({
    mutations,
    correlationId,
    idempotencyKey,
  });

  if (!applyResponse?.accepted) {
    throw new Error('GraphService rejected mutation batch');
  }

  const graphUpdateEvent = {
    schema_version: '1.0.0',
    idempotency_key: `${idempotencyKey}:graph.update`,
    correlation_id: correlationId,
    produced_at: new Date().toISOString(),
    repo_id: payload?.repo?.id || null,
    partition_key: payload?.repo?.id || correlationId,
    mutations,
  };

  const jobs = buildAnalysisJobs(payload, correlationId, idempotencyKey);

  await produceBatch(config.graphUpdatesTopic, [graphUpdateEvent]);
  await produceBatch(config.analysisJobsTopic, jobs);

  state.consumed += 1;
  state.producedGraphUpdates += 1;
  state.producedAnalysisJobs += jobs.length;
  state.lastError = null;
};

const startPipeline = async () => {
  await initStorage();
  await producer.connect();
  await consumer.connect();
  state.kafkaConnected = true;

  await new Promise((resolve, reject) => {
    const deadline = new Date(Date.now() + 15_000);
    graphClient.waitForReady(deadline, (err) => {
      if (err) return reject(err);
      return resolve();
    });
  });
  state.grpcReady = true;

  await consumer.subscribe({ topic: config.sourceTopic, fromBeginning: false });
  await consumer.run({
    autoCommit: true,
    partitionsConsumedConcurrently: 1,
    eachMessage: async ({ topic, partition, message }) => {
      await processWithRetry({ topic, partition, message });
    },
  });

  state.ready = true;
  runtime.pipelineStarted = true;
  log.info({ config }, 'ingestion pipeline started');
};

const startPipelineWithRetry = async () => {
  if (runtime.startupInProgress || runtime.pipelineStarted) return;
  runtime.startupInProgress = true;

  let attempt = 0;
  while (!runtime.pipelineStarted) {
    attempt += 1;
    try {
      await startPipeline();
      break;
    } catch (err) {
      state.lastError = err.message;
      resetConnectivityState();
      await safeDisconnectRuntime();

      const backoff = Math.min(30_000, 1000 * 2 ** Math.min(attempt - 1, 5));
      log.error({ err, attempt, backoff }, 'failed to start ingestion pipeline, retrying');
      await delay(backoff);
    }
  }

  runtime.startupInProgress = false;
};

const shutdown = async () => {
  state.ready = false;
  try {
    await consumer.disconnect();
  } catch {}
  try {
    await producer.disconnect();
  } catch {}
  try {
    await pool.end();
  } catch {}
};

startOtel().catch((err) => {
  console.error('OTel start failed', err);
});

app.get('/healthz', (req, res) => {
  const ok = state.ready && state.kafkaConnected && state.grpcReady;
  res.status(ok ? 200 : 503).json({
    status: ok ? 'ok' : 'degraded',
    service: 'ingestion-service',
    state,
  });
});

app.get('/state', (req, res) => {
  res.json({
    service: 'ingestion-service',
    config,
    state,
    storage,
  });
});

app.get('/poison-pills', async (req, res) => {
  try {
    const limit = Number(req.query.limit || 50);
    const status = req.query.status || 'quarantined';
    const data = await pool.query(
      `
        SELECT id, source_topic, source_partition, source_offset, error, attempts, correlation_id, idempotency_key, status, requeue_count, created_at, updated_at
        FROM meta.poison_pills
        WHERE status = $1
        ORDER BY id DESC
        LIMIT $2
      `,
      [status, Math.min(Math.max(limit, 1), 500)]
    );
    res.json({ items: data.rows });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/poison-pills/:id/requeue', async (req, res) => {
  try {
    const id = Number(req.params.id);
    if (!id) {
      return res.status(400).json({ error: 'invalid poison pill id' });
    }

    const found = await pool.query(
      `
        SELECT id, payload_raw, idempotency_key
        FROM meta.poison_pills
        WHERE id = $1
      `,
      [id]
    );

    if (found.rowCount === 0) {
      return res.status(404).json({ error: 'poison pill not found' });
    }

    const item = found.rows[0];
    await publishRawEvent(config.sourceTopic, item.payload_raw, item.idempotency_key || `requeue:${id}`);

    await pool.query(
      `
        UPDATE meta.poison_pills
        SET status = 'requeued',
            requeue_count = requeue_count + 1,
            requeued_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
      `,
      [id]
    );

    return res.json({ ok: true, requeued_id: id });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

app.listen(port, () => {
  log.info({ port }, 'ingestion-service listening');
  startPipelineWithRetry().catch((err) => {
    state.lastError = err.message;
    log.error({ err }, 'pipeline retry loop crashed unexpectedly');
  });
});

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
