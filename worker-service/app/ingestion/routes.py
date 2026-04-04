"""
Ingestion API endpoints.

Provides REST API for triggering ingestion, checking status, and viewing run history.
"""

import logging
import uuid
from typing import List

import psycopg2
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import get_ingestion_pipeline
from .ingestion_pipeline import IngestionPipeline, IngestionResult, IngestionStatus

log = logging.getLogger("ka-chow.ingestion.routes")

router = APIRouter(tags=["ingestion"])


class TriggerIngestionRequest(BaseModel):
    """Request body for POST /ingestion/trigger."""
    repo: str


class TriggerIngestionResponse(BaseModel):
    """Response for POST /ingestion/trigger."""
    run_id: str
    status: str


@router.post("/trigger", response_model=TriggerIngestionResponse)
async def trigger_ingestion(
    request: TriggerIngestionRequest,
    background_tasks: BackgroundTasks,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
):
    """
    Trigger full repository ingestion.
    
    Responds immediately with run_id and status="running".
    Actual ingestion runs in a BackgroundTask.
    
    Args:
        request: Repository to ingest
        background_tasks: FastAPI background tasks
        pipeline: Injected ingestion pipeline
        
    Returns:
        TriggerIngestionResponse with run_id and status
    """
    # Generate new run_id at endpoint level
    run_id = str(uuid.uuid4())
    
    # Queue ingestion in background
    background_tasks.add_task(
        _run_ingestion_background,
        pipeline,
        request.repo,
        run_id,
    )
    
    log.info(f"Triggered ingestion for {request.repo} with run_id={run_id}")
    
    return TriggerIngestionResponse(
        run_id=run_id,
        status="running",
    )


async def _run_ingestion_background(
    pipeline: IngestionPipeline,
    repo: str,
    run_id: str,
):
    """
    Background task wrapper for ingest_repo().
    
    Logs errors but does not raise (background tasks should not crash).
    """
    try:
        result = await pipeline.ingest_repo(
            repo=repo,
            run_id=run_id,
            triggered_by="manual",
        )
        log.info(f"Background ingestion completed: {result.status}")
    except Exception as e:
        log.error(f"Background ingestion failed: {e}", exc_info=True)


@router.get("/status/{repo:path}", response_model=IngestionStatus)
def get_ingestion_status(
    repo: str,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
):
    """
    Get the latest ingestion status for a repository.
    
    Args:
        repo: Repository full name (owner/repo)
        pipeline: Injected ingestion pipeline
        
    Returns:
        IngestionStatus for the most recent run
        
    Raises:
        HTTPException: 404 if no runs found
    """
    return pipeline.get_ingestion_status(repo)


@router.get("/runs/{repo:path}", response_model=List[IngestionStatus])
def get_ingestion_runs(
    repo: str,
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
):
    """
    Get the last 20 ingestion runs for a repository.
    
    Args:
        repo: Repository full name (owner/repo)
        pipeline: Injected ingestion pipeline
        
    Returns:
        List of IngestionStatus ordered by started_at descending
    """
    # Query meta.ingestion_runs directly
    conn = psycopg2.connect(**pipeline.pg_cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, repo, triggered_by, started_at, completed_at,
                       files_processed, chunks_created, embeddings_created,
                       services_detected, status, error_message, commit_sha
                FROM meta.ingestion_runs
                WHERE repo = %s
                ORDER BY started_at DESC
                LIMIT 20
                """,
                (repo,),
            )
            rows = cur.fetchall()
            
            return [
                IngestionStatus(
                    run_id=row[0],
                    repo=row[1],
                    triggered_by=row[2],
                    started_at=row[3],
                    completed_at=row[4],
                    files_processed=row[5],
                    chunks_created=row[6],
                    embeddings_created=row[7],
                    services_detected=row[8],
                    status=row[9],
                    error_message=row[10],
                    commit_sha=row[11],
                )
                for row in rows
            ]
    finally:
        conn.close()
