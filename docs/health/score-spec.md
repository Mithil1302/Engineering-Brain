# Knowledge Health Score Spec

## Components (example weights TBD)
- Coverage: endpoints documented.
- Freshness: doc/spec hash alignment.
- Test linkage: tests covering endpoints/models.
- Drift penalties: outstanding breaking/doc drift findings.

## Output
- Score 0–100; breakdown per component; list of top deficits.
- JSON fields: score, components[{name, value, weight}], deficits[], generated_at, repo/service scope.

## Data Sources
- Graph edges: doc-documents-endpoint, test-covers-endpoint, spec hashes, drift findings.

## Open Items
- Final weights; thresholds for “good/ok/poor”.
