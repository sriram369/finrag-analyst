"""
FinRAG Analyst — FastAPI Backend
Deployed on Railway.

Endpoints:
  POST /ingest              → start ingestion job, returns job_id
  GET  /ingest/{job_id}/stream → SSE stream of real-time progress
  POST /query               → RAG query, returns answer + citations + metrics
  GET  /metrics             → system-level stats from Qdrant
  GET  /health              → Railway health check
"""

import sys
import os
import uuid
import json
import asyncio
import time
from contextlib import asynccontextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from models import IngestRequest, QueryRequest, QueryResponse, Citation
from config import TICKERS, FILING_TYPES

# ── Active ingestion jobs: job_id → asyncio.Queue ────────────────────────────
_jobs: dict[str, asyncio.Queue] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up Qdrant connection on startup
    try:
        import vector_store
        vector_store.ensure_collection()
    except Exception as e:
        print(f"[startup] Qdrant not yet configured or unreachable: {e}")
    yield


app = FastAPI(title="FinRAG Analyst API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your Vercel URL in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Ingestion ─────────────────────────────────────────────────────────────────

def _run_ingestion_sync(job_id: str, request: IngestRequest) -> None:
    """Runs in a thread pool. Calls ingest.run_pipeline with a sync emit."""
    from ingest import run_pipeline

    queue = _jobs[job_id]

    def emit(event: dict) -> None:
        # put_nowait is safe from non-async context
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass

    try:
        run_pipeline(
            tickers=request.tickers,
            filing_types=request.filing_types,
            limit=request.limit,
            emit=emit,
        )
    except Exception as e:
        queue.put_nowait({"type": "error", "message": str(e)})
    finally:
        queue.put_nowait({"type": "__end__"})   # sentinel — close SSE stream


@app.post("/ingest")
async def start_ingest(request: IngestRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = asyncio.Queue(maxsize=500)

    # Run the blocking pipeline in a thread so it doesn't block the event loop
    background_tasks.add_task(
        asyncio.get_event_loop().run_in_executor,
        None,
        _run_ingestion_sync,
        job_id,
        request,
    )

    return {"job_id": job_id, "tickers": request.tickers,
            "filing_types": request.filing_types}


@app.get("/ingest/{job_id}/stream")
async def stream_progress(job_id: str):
    """
    Server-Sent Events stream — the frontend connects here and receives
    a live JSON event for every step of the ingestion pipeline.
    """
    queue = _jobs.get(job_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60.0)
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"heartbeat\"}\n\n"
                continue

            yield f"data: {json.dumps(event)}\n\n"

            if event.get("type") in ("done", "error", "__end__"):
                _jobs.pop(job_id, None)   # clean up job
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # disable Nginx buffering on Railway
        },
    )


# ── Query (RAG pipeline) ──────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Full RAG pipeline:
    HyDE expansion → hybrid retrieval → Cohere rerank → Gemini generation
    (Phase 3 + 4 — wired in once those modules are built)
    """
    start = time.time()

    # Phase 3/4 stubs — will be replaced when retriever.py + rag_pipeline.py are done
    try:
        from rag_pipeline import answer_question
        result = await asyncio.get_event_loop().run_in_executor(
            None, answer_question, request.question,
            request.ticker, request.form_type, request.filing_year,
        )
    except ImportError:
        # Pipeline not yet built — return a placeholder
        result = {
            "answer": "RAG pipeline coming soon — ingestion is Phase 1, retrieval is Phase 3.",
            "citations": [],
            "faithfulness": None,
            "cost_usd": 0.0,
        }

    latency_ms = int((time.time() - start) * 1000)

    return QueryResponse(
        answer=result["answer"],
        citations=[Citation(**c) for c in result.get("citations", [])],
        cost_usd=result.get("cost_usd", 0.0),
        latency_ms=latency_ms,
        faithfulness=result.get("faithfulness"),
    )


# ── Metrics ───────────────────────────────────────────────────────────────────

@app.get("/metrics")
async def metrics():
    import vector_store
    info = vector_store.collection_info()
    return {
        "total_chunks":    info["total_chunks"],
        "collection_status": info["status"],
        "tickers_available": TICKERS,
        "filing_types":    FILING_TYPES,
    }
