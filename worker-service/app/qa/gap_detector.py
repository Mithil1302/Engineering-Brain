"""
Documentation Gap Detection System

Mines QA event logs to identify unanswered or low-confidence questions,
surfacing them as documentation gaps with frequency, severity, and remediation.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal


@dataclass
class KnowledgeGap:
    """Represents a detected documentation gap."""
    
    question_sample: str        # most recent question in the group
    intent: str
    frequency: int              # row count in the question group
    avg_confidence: float
    suggested_doc_title: str    # LLM-generated from question_sample
    suggested_doc_location: str # service name inferred from question entities
    gap_severity: Literal["critical", "high", "medium", "low"]


@dataclass
class GapReport:
    """Aggregates KnowledgeGap instances by service with documentation debt score."""
    
    repo: str
    generated_at: datetime
    total_gaps: int
    gaps_by_service: dict[str, list[KnowledgeGap]]
    top_gaps: list[KnowledgeGap]        # top 10 by frequency
    documentation_debt_score: float     # Documentation_Debt_Score


class GapDetector:
    """Detects documentation gaps by analyzing QA event logs."""
    
    SEVERITY_WEIGHTS: dict[str, int] = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1
    }
    
    def __init__(self, pg_cfg: dict, llm):
        """Initialize GapDetector with PostgreSQL configuration and LLM client.
        
        Args:
            pg_cfg: Database configuration dict with host, port, database, user, password
            llm: LLMClient instance for generating documentation titles
        """
        self.pg_cfg = pg_cfg
        self.llm = llm
    
    def detect_gaps(self, repo: str, lookback_days: int = 7) -> list[KnowledgeGap]:
        """
        Query meta.qa_event_log and flag gaps where:
        - had_rag_results = false, OR
        - avg(confidence) < 0.5
        Groups by LEFT(question, 50) to cluster similar questions.
        Uses idx_qa_event_log_gap_detection partial index for performance.
        """
        with psycopg2.connect(**self.pg_cfg) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        LEFT(question, 50)   AS question_prefix,
                        MAX(question)        AS question_sample,
                        MAX(intent)          AS intent,
                        COUNT(*)             AS frequency,
                        AVG(confidence)      AS avg_confidence,
                        BOOL_OR(had_rag_results = false) AS any_no_rag
                    FROM meta.qa_event_log
                    WHERE repo = %s
                      AND created_at >= NOW() - INTERVAL '%s days'
                    GROUP BY LEFT(question, 50)
                    HAVING
                        BOOL_OR(had_rag_results = false) = true
                        OR AVG(confidence) < 0.5
                    ORDER BY COUNT(*) DESC
                """, (repo, lookback_days))

                gaps = []
                for row in cur.fetchall():
                    severity = self._compute_severity(
                        int(row["frequency"]), float(row["avg_confidence"] or 0.0)
                    )
                    doc_title = self._generate_doc_title(row["question_sample"])
                    service = self._infer_service(row["question_sample"], repo)
                    gaps.append(KnowledgeGap(
                        question_sample=row["question_sample"],
                        intent=row["intent"] or "general",
                        frequency=int(row["frequency"]),
                        avg_confidence=float(row["avg_confidence"] or 0.0),
                        suggested_doc_title=doc_title,
                        suggested_doc_location=service,
                        gap_severity=severity,
                    ))
                return gaps

    def _compute_severity(self, frequency: int, avg_confidence: float) -> str:
        """
        Compute gap severity based on frequency and confidence.
        Priority order: critical > high > medium > low.
        """
        if frequency > 10 and avg_confidence < 0.3:
            return "critical"
        elif frequency > 5 or avg_confidence < 0.4:
            return "high"
        elif frequency > 2:
            return "medium"
        else:
            return "low"
    
    def _generate_doc_title(self, question: str) -> str:
        """Single LLM call to suggest a documentation title."""
        try:
            result = self.llm.generate(
                f"What documentation title would best answer: {question}?",
                temperature=0.3,
                max_output_tokens=30,
            )
            return result.text.strip().strip('"')
        except Exception:
            return f"Documentation for: {question[:60]}"
    
    def _infer_service(self, question: str, repo: str) -> str:
        """Infer service name by matching question against known service names."""
        import re
        known_services = self._get_known_services(repo)
        for service in known_services:
            if re.search(rf'\b{re.escape(service)}\b', question, re.IGNORECASE):
                return service
        return "general"
    
    def _get_known_services(self, repo: str) -> list[str]:
        """Query meta.graph_nodes for known service names."""
        with psycopg2.connect(**self.pg_cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT label FROM meta.graph_nodes
                    WHERE repo = %s AND node_type = 'service'
                """, (repo,))
                return [row[0] for row in cur.fetchall()]
    
    def generate_gap_report(self, repo: str, lookback_days: int = 7) -> GapReport:
        """Generate full gap report with service grouping and debt score."""
        gaps = self.detect_gaps(repo, lookback_days)

        gaps_by_service: dict[str, list[KnowledgeGap]] = {}
        for gap in gaps:
            svc = gap.suggested_doc_location
            gaps_by_service.setdefault(svc, []).append(gap)

        debt_score = float(sum(
            gap.frequency * self.SEVERITY_WEIGHTS[gap.gap_severity]
            for gap in gaps
        ))

        return GapReport(
            repo=repo,
            generated_at=datetime.now(timezone.utc),
            total_gaps=len(gaps),
            gaps_by_service=gaps_by_service,
            top_gaps=sorted(gaps, key=lambda g: g.frequency, reverse=True)[:10],
            documentation_debt_score=debt_score,
        )
