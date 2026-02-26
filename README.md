# FinRAG Analyst

Production Financial RAG system that answers natural language questions about SEC EDGAR filings (10-K, 10-Q) with cited, hallucination-free responses and real-time pipeline monitoring.

**Live:** [app-self-one-65.vercel.app](https://app-self-one-65.vercel.app) · **API:** [finrag-analyst-production.up.railway.app](https://finrag-analyst-production.up.railway.app)

---

## What It Does

Ask any question about a public company's financials — revenue, risk factors, debt, guidance — and get a precise answer drawn directly from official SEC filings, with citations showing exactly which passage from which document the answer came from.

- No hallucinations: answers are grounded in real filing text
- Full citations: ticker, filing year, section, and source excerpt per answer
- Live ingestion: watch the pipeline run step-by-step in the browser via SSE
- Under $0.002 per query end-to-end on free-tier infrastructure

---

## Architecture

```
User Browser (Vercel — Next.js)
       │
       ├─ POST /query ──────────────────────────────────────────────────────┐
       │                                                                     │
       │                              FastAPI (Railway)                      │
       │                                    │                                │
       │              ┌─────────────────────┼──────────────────────┐         │
       │              │                     │                       │         │
       │        Cohere embed          Qdrant Cloud           Cohere LLM      │
       │        (question →           (vector search         (Command-R7B    │
       │         1024-dim vec)         + filter)              → answer)      │
       │              │                     │                       │         │
       │              └─────────────────────┴───────────────────────┘         │
       │                                                                     │
       └─ Answer + Citations + Faithfulness Score + Cost + Latency ──────────┘

       ├─ POST /ingest → Background thread → SSE stream → Live UI update
       └─ GET /metrics → Qdrant collection stats → Dashboard
```

---

## Stack

| Layer | Technology | Why |
|---|---|---|
| SEC data | `sec-edgar-downloader` + custom SGML parser | Free, official EDGAR filings |
| Document parsing | LlamaParse (LlamaCloud API) | Best-in-class HTML/table → Markdown |
| Chunking | LlamaIndex `SentenceSplitter` | Sentence-aware splits, no GPU needed |
| Embeddings | Cohere `embed-english-v3.0` (1024-dim) | High quality, API-based |
| Reranking | Cohere `rerank-english-v3.0` | Improves retrieval precision significantly |
| LLM | Cohere `command-r7b-12-2024` | Small, fast, RAG-optimized |
| Vector DB | Qdrant Cloud | Free hosted tier, fast filtered search |
| Backend | FastAPI + SSE + asyncio | Non-blocking streaming, Railway deploy |
| Container | Docker `python:3.12-slim` | ~400 MB image |
| Frontend | Next.js 16 + Tailwind CSS | App Router, Vercel deploy |
| Deployment | Railway (backend) + Vercel (frontend) | Free tier, GitHub CI/CD |

---

## Project Structure

```
finrag-analyst/
├── src/
│   ├── ingest.py          # 6-step ingestion pipeline
│   ├── rag_pipeline.py    # Query pipeline (embed → search → rerank → generate)
│   ├── vector_store.py    # Qdrant client wrapper
│   └── config.py          # Env vars and settings
├── api/
│   ├── main.py            # FastAPI app (routes, SSE, CORS)
│   └── models.py          # Pydantic request/response models
├── app/                   # Next.js 16 frontend
│   └── components/
│       ├── ChatWindow.tsx       # Chat UI with citations and metric badges
│       ├── IngestionMonitor.tsx # Live pipeline step visualizer
│       ├── Sidebar.tsx          # Navigation
│       └── MetricsPage.tsx      # Qdrant stats dashboard
├── Dockerfile
├── railway.toml
└── requirements.txt
```

---

## How It Works

### Ingestion Pipeline (`src/ingest.py`)

Six steps, streamed live to the browser via SSE:

1. **Download** — Pulls filings from SEC EDGAR by ticker and form type (10-K, 10-Q) using `sec-edgar-downloader`
2. **Extract** — SEC delivers SGML bundles (`full-submission.txt`). A custom parser extracts the primary HTM document (SEQUENCE=1)
3. **Parse** — Sends the HTM to LlamaParse, which converts complex financial HTML and tables into clean Markdown
4. **Chunk** — LlamaIndex `SentenceSplitter` (1024 tokens, 200 overlap) splits the document into context-preserving passages
5. **Embed** — Batch-embeds chunks with Cohere `embed-english-v3.0` (1024-dim dense vectors)
6. **Store** — Upserts vectors + metadata into Qdrant using deterministic UUID5 IDs (accession number + chunk index), preventing duplicate storage on re-ingestion

Metadata stored per chunk: `ticker`, `form_type`, `filing_year`, `section`, `accession_number`, `word_count`. Payload indexes created on all filterable fields for fast filtered search.

### Query Pipeline (`src/rag_pipeline.py`)

Every chat message runs through five steps:

1. **Embed** — Question → 1024-dim vector via Cohere (`input_type="search_query"`)
2. **Retrieve** — Top-20 candidate chunks from Qdrant, optionally filtered by ticker / form type / year
3. **Rerank** — Cohere `rerank-english-v3.0` reorders the 20 candidates by semantic relevance, keeping top 5
4. **Generate** — Structured prompt + top-5 passages → Cohere `command-r7b-12-2024` → cited answer
5. **Score** — Faithfulness score (fraction of answer sentences with ≥30% word overlap with source chunks) + citations with ticker, year, section, excerpt, and similarity score

---

## Running Locally

### Prerequisites

- Python 3.12
- Node.js 18+
- [Cohere API key](https://dashboard.cohere.com/) (free trial)
- [Qdrant Cloud cluster](https://cloud.qdrant.io/) (free tier)
- [LlamaCloud API key](https://cloud.llamaindex.ai/) (for LlamaParse)

### Backend

```bash
# Clone and set up Python env
git clone https://github.com/sriram369/finrag-analyst.git
cd finrag-analyst
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure env vars
cp .env.example .env
# Fill in: COHERE_API_KEY, QDRANT_URL, QDRANT_API_KEY, LLAMA_CLOUD_API_KEY

# Run the API
PYTHONPATH=src:api uvicorn api.main:app --reload --port 8000
```

### Frontend

```bash
cd app
npm install
# Set NEXT_PUBLIC_API_URL=http://localhost:8000 in app/.env.local
npm run dev
```

Open [localhost:3000](http://localhost:3000).

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/ingest` | POST | Start ingestion job for a ticker. Returns `job_id` |
| `/ingest/{job_id}/stream` | GET | SSE stream of live pipeline progress events |
| `/query` | POST | RAG query — returns answer, citations, latency, cost, faithfulness |
| `/metrics` | GET | Live Qdrant collection stats |
| `/health` | GET | Health check |

### Example Query

```bash
curl -X POST https://finrag-analyst-production.up.railway.app/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are Apple'\''s main risk factors in their latest 10-K?",
    "ticker": "AAPL",
    "form_type": "10-K"
  }'
```

---

## Deployment

### Backend (Railway)

The Dockerfile builds a `python:3.12-slim` image (~400 MB). Railway injects `$PORT` at runtime.

```bash
# railway.toml already configured — just connect repo in Railway dashboard
```

Required env vars on Railway: `COHERE_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `LLAMA_CLOUD_API_KEY`

### Frontend (Vercel)

```bash
cd app
vercel --prod
# Set NEXT_PUBLIC_API_URL to your Railway backend URL in Vercel project settings
```

---

## Environment Variables

```env
# Backend (Railway / .env)
COHERE_API_KEY=your_cohere_key
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_key
LLAMA_CLOUD_API_KEY=your_llamacloud_key

# Frontend (Vercel / app/.env.local)
NEXT_PUBLIC_API_URL=https://finrag-analyst-production.up.railway.app
```

---

## License

MIT
