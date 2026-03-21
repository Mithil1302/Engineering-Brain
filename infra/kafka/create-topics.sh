#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-kafka:9092}"
TOPICS=(
  "repo.events"
  "repo.events.dlq"
  "graph.updates"
  "analysis.jobs"
  "pr.checks"
  "pr.checks.dlq"
  "agent.requests"
  "ci.events"
)

printf "Waiting for Kafka at %s...\n" "$BOOTSTRAP_SERVER"
until kafka-topics --bootstrap-server "$BOOTSTRAP_SERVER" --list >/dev/null 2>&1; do
  sleep 2
done

for topic in "${TOPICS[@]}"; do
  kafka-topics \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 3 \
    --replication-factor 1
  echo "Ensured topic: $topic"
done

echo "Kafka topic bootstrap complete."
