"""
Phase 1 — Data Ingestion Pipeline (production, web-ready)
----------------------------------------------------------
Designed to run as a FastAPI background task.
Every step emits a progress event via `emit()` callback,
which FastAPI SSE streams live to the frontend.

Steps per filing:
  1. download  — SEC EDGAR → full-submission.txt
  2. extract   — pull primary HTM from SGML bundle
  3. parse     — LlamaParse HTM → clean markdown
  4. chunk     — SemanticSplitter → list of text chunks
  5. embed     — BAAI/bge-large-en-v1.5 → vectors
  6. store     — upsert into Qdrant Cloud
"""

import os
import re
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Callable

from llama_cloud_services import LlamaParse
from llama_index.core import Document
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from sec_edgar_downloader import Downloader

from config import (
    LLAMA_CLOUD_API_KEY,
    SEC_USER_AGENT_NAME, SEC_USER_AGENT_EMAIL,
    DATA_RAW_DIR,
    TICKERS, FILING_TYPES,
    EMBED_MODEL_NAME, SEC_SECTIONS,
)
import vector_store

# ── Type alias for a progress callback ────────────────────────────────────────
ProgressFn = Callable[[dict], None]


# ── Shared embedding model (loaded once, reused across all files) ─────────────
_embed_model: HuggingFaceEmbedding | None = None
_chunker: SemanticSplitterNodeParser | None = None


def get_chunker(emit: ProgressFn) -> SemanticSplitterNodeParser:
    global _embed_model, _chunker
    if _chunker is None:
        emit({"type": "system", "message": f"Loading embedding model {EMBED_MODEL_NAME}…"})
        _embed_model = HuggingFaceEmbedding(model_name=EMBED_MODEL_NAME)
        _chunker = SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            embed_model=_embed_model,
        )
        emit({"type": "system", "message": "Embedding model loaded and cached ✓"})
    return _chunker


# ── Step 1 — Download ──────────────────────────────────────────────────────────

def download_filings(
    tickers: list[str],
    filing_types: list[str],
    limit: int,
    emit: ProgressFn,
) -> None:
    os.makedirs(DATA_RAW_DIR, exist_ok=True)
    dl = Downloader(SEC_USER_AGENT_NAME, SEC_USER_AGENT_EMAIL, DATA_RAW_DIR)

    for ticker in tickers:
        for form_type in filing_types:
            emit({"type": "step", "step": "download", "ticker": ticker,
                  "form_type": form_type, "status": "started",
                  "message": f"Downloading {ticker} {form_type} from SEC EDGAR…"})
            try:
                dl.get(form_type, ticker, limit=limit)
                emit({"type": "step", "step": "download", "ticker": ticker,
                      "form_type": form_type, "status": "done",
                      "message": f"{ticker} {form_type} downloaded ✓"})
            except Exception as e:
                emit({"type": "step", "step": "download", "ticker": ticker,
                      "form_type": form_type, "status": "error", "message": str(e)})


# ── Step 2 — Extract HTM from SGML bundle ─────────────────────────────────────

def extract_primary_document(submission_path: Path, emit: ProgressFn) -> Path | None:
    """
    SEC full-submission.txt is an SGML bundle of all docs.
    We extract SEQUENCE=1 (the actual 10-K/10-Q HTML) from it.
    """
    out_path = submission_path.parent / "primary_document.htm"
    if out_path.exists() and out_path.stat().st_size > 1000:
        return out_path  # already extracted

    accession = submission_path.parent.name
    emit({"type": "step", "step": "extract", "accession": accession,
          "status": "started", "message": f"Extracting HTML from {accession}…"})

    in_primary = False
    in_text_block = False
    found_sequence_1 = False
    lines = []

    with open(submission_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip() == "<DOCUMENT>":
                in_primary = True
                found_sequence_1 = False
                continue
            if in_primary:
                if re.match(r"<SEQUENCE>1\s*$", line.strip()):
                    found_sequence_1 = True
                if line.strip() == "<TEXT>" and found_sequence_1:
                    in_text_block = True
                    continue
                if in_text_block and line.strip() in ("</TEXT>", "</DOCUMENT>"):
                    break
                if line.strip() == "</DOCUMENT>" and not found_sequence_1:
                    in_primary = False
                    continue
                if in_text_block:
                    lines.append(line)

    if not lines:
        emit({"type": "step", "step": "extract", "accession": accession,
              "status": "error", "message": "Could not extract primary document"})
        return None

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    size_mb = round(out_path.stat().st_size / 1024 / 1024, 1)
    emit({"type": "step", "step": "extract", "accession": accession,
          "status": "done", "message": f"Extracted {size_mb} MB HTM ✓"})
    return out_path


# ── Step 3 — Parse with LlamaParse ────────────────────────────────────────────

def parse_filing(file_path: Path, emit: ProgressFn) -> str:
    emit({"type": "step", "step": "parse", "file": file_path.name,
          "status": "started", "message": f"Sending {file_path.name} to LlamaParse…"})
    try:
        parser = LlamaParse(
            api_key=LLAMA_CLOUD_API_KEY,
            result_type="markdown",
            verbose=False,
            language="en",
        )
        documents = parser.load_data(str(file_path))
        text = "\n\n".join(doc.text for doc in documents)
        emit({"type": "step", "step": "parse", "file": file_path.name,
              "status": "done", "message": f"Parsed {len(text):,} chars ✓"})
        return text
    except Exception as e:
        emit({"type": "step", "step": "parse", "file": file_path.name,
              "status": "error", "message": str(e)})
        return ""


# ── Step 4 — Detect SEC section ───────────────────────────────────────────────

def detect_section(snippet: str) -> str:
    s = snippet.lower()
    for key, label in SEC_SECTIONS.items():
        pattern = key.replace("_", r"[\s\.\:]*")
        if re.search(pattern, s):
            return label
    return "General"


def extract_metadata(file_path: Path, ticker: str, filing_types: list[str]) -> dict:
    parts = file_path.parts
    form_type = next((ft for ft in filing_types if ft in parts), "unknown")
    # Accession dirs look like 0000320193-24-000123 — extract year from the middle part
    accession = file_path.parent.name   # e.g. 0000320193-24-000123
    year_short_match = re.search(r"-(\d{2})-", accession)
    if year_short_match:
        yr = int(year_short_match.group(1))
        filing_year = 2000 + yr if yr < 50 else 1900 + yr
    else:
        year_match = re.search(r"(20\d{2})", str(file_path))
        filing_year = int(year_match.group(1)) if year_match else datetime.now().year
    return {"ticker": ticker, "form_type": form_type,
            "filing_year": filing_year, "accession": accession,
            "source_file": str(file_path)}


# ── Step 5 — Semantic chunk ───────────────────────────────────────────────────

def chunk_text(text: str, metadata: dict, chunker: SemanticSplitterNodeParser,
               emit: ProgressFn) -> list[dict]:
    emit({"type": "step", "step": "chunk", "ticker": metadata["ticker"],
          "status": "started", "message": "Semantic chunking…"})
    try:
        nodes = chunker.get_nodes_from_documents([Document(text=text, metadata=metadata)])
        chunks = []
        for i, node in enumerate(nodes):
            ct = node.get_content()
            if len(ct.split()) < 30:
                continue
            chunks.append({
                "chunk_id": f"{metadata['ticker']}_{metadata['form_type']}_{metadata['accession']}_{i:04d}",
                "text": ct,
                "metadata": {**metadata, "section": detect_section(ct[:200]),
                             "chunk_index": i, "word_count": len(ct.split())},
            })
        emit({"type": "step", "step": "chunk", "ticker": metadata["ticker"],
              "status": "done", "message": f"Created {len(chunks)} chunks ✓"})
        return chunks
    except Exception as e:
        emit({"type": "step", "step": "chunk", "ticker": metadata["ticker"],
              "status": "error", "message": str(e)})
        return []


# ── Step 6 — Embed + store in Qdrant ─────────────────────────────────────────

def embed_and_store(chunks: list[dict], emit: ProgressFn) -> int:
    if not chunks:
        return 0
    emit({"type": "step", "step": "embed", "count": len(chunks),
          "status": "started", "message": f"Embedding {len(chunks)} chunks…"})
    try:
        texts = [c["text"] for c in chunks]
        vectors = _embed_model.get_text_embedding_batch(texts, show_progress=False)

        emit({"type": "step", "step": "store", "count": len(chunks),
              "status": "started", "message": "Storing in Qdrant Cloud…"})
        stored = vector_store.upsert_chunks(chunks, vectors)

        emit({"type": "step", "step": "store", "count": stored,
              "status": "done", "message": f"Stored {stored} vectors in Qdrant ✓"})
        return stored
    except Exception as e:
        emit({"type": "step", "step": "embed", "status": "error", "message": str(e)})
        return 0


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    tickers: list[str] = TICKERS,
    filing_types: list[str] = FILING_TYPES,
    limit: int = 5,
    emit: ProgressFn = lambda e: print(json.dumps(e)),
) -> dict:
    """
    Full ingestion pipeline. `emit` is called with a progress dict at every step.
    FastAPI passes an asyncio.Queue.put_nowait as the emit function.
    Returns summary stats.
    """
    total_chunks = 0

    # Ensure Qdrant collection exists
    try:
        vector_store.ensure_collection()
    except Exception as e:
        emit({"type": "error", "message": f"Qdrant connection failed: {e}"})
        return {"error": str(e)}

    # Load chunker (cached after first call)
    chunker = get_chunker(emit)

    # Step 1 — Download
    emit({"type": "phase", "phase": "download", "message": "Starting SEC EDGAR downloads…"})
    download_filings(tickers, filing_types, limit, emit)

    # Steps 2–6 — per filing
    emit({"type": "phase", "phase": "process", "message": "Processing filings…"})

    for ticker in tickers:
        ticker_dir = Path(DATA_RAW_DIR) / "sec-edgar-filings" / ticker
        if not ticker_dir.exists():
            emit({"type": "warning", "message": f"No files for {ticker} — skipping"})
            continue

        submission_files = list(ticker_dir.rglob("full-submission.txt"))
        emit({"type": "ticker_start", "ticker": ticker, "total_filings": len(submission_files)})

        for sub in submission_files:
            # Step 2 — Extract
            htm = extract_primary_document(sub, emit)
            if not htm:
                continue

            # Step 3 — Parse
            text = parse_filing(htm, emit)
            if not text.strip():
                continue

            # Step 4 — Metadata + Step 5 — Chunk
            metadata = extract_metadata(htm, ticker, filing_types)
            chunks = chunk_text(text, metadata, chunker, emit)

            # Step 6 — Embed + Store
            stored = embed_and_store(chunks, emit)
            total_chunks += stored

        emit({"type": "ticker_done", "ticker": ticker})

    summary = {"type": "done", "total_chunks": total_chunks,
               "tickers": tickers, "message": f"Ingestion complete — {total_chunks} chunks stored in Qdrant ✓"}
    emit(summary)
    return summary


# ── CLI fallback (for local testing) ──────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=["AAPL"])
    parser.add_argument("--filing-types", nargs="+", default=["10-K"])
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()

    run_pipeline(
        tickers=args.tickers,
        filing_types=args.filing_types,
        limit=args.limit,
    )
