# FinRAG Analyst

> Ask any question about a public company's SEC filings. Get a cited, hallucination-free answer in under 2 seconds — for less than $0.002 per query.

<p align="center">
  <a href="https://app-self-one-65.vercel.app"><img src="https://img.shields.io/badge/Live_Demo-▶_Try_It-22c55e?style=for-the-badge" alt="Live Demo"/></a>
  <a href="https://finrag-analyst-production.up.railway.app/docs"><img src="https://img.shields.io/badge/API_Docs-FastAPI-009688?style=for-the-badge&logo=fastapi" alt="API Docs"/></a>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Next.js-16-000000?style=for-the-badge&logo=next.js" alt="Next.js"/>
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License"/>
</p>

---

## Demo

**"What were Apple's main revenue risks in their 2023 10-K?"**

```
Answer: Apple's 2023 10-K identifies three primary revenue risks: (1) geographic
concentration — 19% of net sales from Greater China, exposed to geopolitical tension
and regulatory pressure; (2) component dependency on a small number of sole-sourced
suppliers for key processors and displays; (3) services margin compression as App Store
regulatory scrutiny intensifies across the EU and US.

Sources:
  [1] AAPL · 10-K · 2023 · Item 1A – Risk Factors (similarity: 0.94)
      "...our operations and performance depend significantly on global and regional
       economic conditions and adverse economic conditions..."
  [2] AAPL · 10-K · 2023 · Item 1A – Risk Factors (similarity: 0.91)
      "...we depend on component and product manufacturing and logistical services
       provided by outsourcing partners..."

Faithfulness: 0.97 · Latency: 1.84s · Cost: $0.0018
```

> Add a screenshot or GIF here: `docs/demo.gif` — record the live app at [app-self-one-65.vercel.app](https://app-self-one-65.vercel.app)

---

## What It Does

FinRAG Analyst is a production RAG system over SEC EDGAR that answers natural language questions about public company financials — with citations tracing every claim back to the exact filing passage it came from.

- **No hallucinations** — every sentence in the answer is grounded in real filing text, scored by a faithfulness metric
- **Full citations** — ticker, filing year, section, excerpt, and similarity score per source
- **Live ingestion** — watch the 6-step pipeline run in real time via Server-Sent Events
- **Cheap** — under $0.002 per query end-to-end on free-tier infrastructure

---

## Architecture

```
Browser (Vercel / Next.js 16)
    │
    ├─ POST /query ─────────────────────────────────────────────┐
    │                                                            │
    │                     FastAPI  (Railway)                     │
    │                           │                                │
    │          ┌────────────────┼───────────────┐                │
    │          │                │               │                │
    │    Cohere embed      Qdrant Cloud    Cohere LLM            │
    │   (query → vec)   (ANN + filter)  (Command-R7B)           │
    │          │                │               │                │
    │          └────────────────┴───────────────┘                │
    │                                                            │
    └─ Answer + Citations + Faithfulness + Latency + Cost ───────┘

    ├─ POST /ingest → background thread → SSE stream → live UI
    └─ GET  /metrics → Qdrant collection stats → dashboard
```

---

## Stack

| Layer | Technology | Why |
|---|---|---|
| SEC data | `sec-edgar-downloader` + custom SGML parser | Free, official filings |
| Document parsing | LlamaParse (LlamaCloud) | Best HTML/table → Markdown conversion |
| Chunking | LlamaIndex `SentenceSplitter` | Sentence-aware, no GPU needed |
| Embeddings | Cohere `embed-english-v3.0` (1024-dim) | High quality, API-based |
| Reranking | Cohere `rerank-english-v3.0` | Significantly improves retrieval precision |
| LLM | Cohere `command-r7b-12-2024` | Small, fast, RAG-optimized |
| Vector DB | Qdrant Cloud | Free hosted tier, fast filtered search |
| Backend | FastAPI + SSE + asyncio | Non-blocking streaming |
| Container | Docker `python:3.12-slim` | ~400 MB image |
| Frontend | Next.js 16 + Tailwind CSS | App Router, Vercel deploy |
| Deployment | Railway + Vercel | Free tier, GitHub CI/CD |

---

## Technical Highlights

**Why retrieval is hard on SEC filings:**
EDGAR delivers filings as SGML bundles containing multiple documents, inline XBRL, and complex HTML tables. A naive PDF-to-text pipeline would lose table structure entirely. This system uses a custom SGML parser to extract the primary HTM document, then LlamaParse to preserve financial table formatting as Markdown — which means the LLM can correctly read "Revenue: $394.3B" instead of garbled whitespace.

**Deduplication on re-ingestion:**
Chunks are stored with deterministic `UUID5(accession_number + chunk_index)` IDs. Re-running ingestion on the same filing is always idempotent — no duplicate vectors accumulate in Qdrant over time.

**Faithfulness scoring without a second LLM:**
Rather than running a judge LLM (expensive), faithfulness is computed as the fraction of answer sentences with ≥30% word overlap against any source chunk. Cheap, fast, and correlates well with actual groundedness for factual financial Q&A.

**Streaming pipeline visibility:**
Each ingestion step publishes SSE events. The browser visualizes step completion in real time — users see "Downloading → Extracting → Parsing → Chunking → Embedding → Storing" with timing per step instead of a blank loading spinner.

---

## Project Structure

```
finrag-analyst/
├── src/
│   ├── ingest.py          # 6-step ingestion pipeline (SEC → Qdrant)
│   ├── rag_pipeline.py    # Query pipeline (embed → search → rerank → generate)
│   ├── vector_store.py    # Qdrant client wrapper
│   └── config.py          # Env vars and settings
├── api/
│   ├── main.py            # FastAPI app (routes, SSE, CORS)
│   └── models.py          # Pydantic request/response models
├── app/                   # Next.js 16 frontend
│   └── components/
│       ├── ChatWindow.tsx       # Chat UI with citations and metric badges
│       ├── IngestionMonitor.tsx # Live pipeline step visualizer (SSE)
│       ├── Sidebar.tsx          # Navigation
│       └── MetricsPage.tsx      # Qdrant collection stats dashboard
├── Dockerfile
├── railway.toml
└── requirements.txt
```

---

## How It Works

### Ingestion Pipeline (`src/ingest.py`)

Six steps, each streamed live to the browser via SSE:

1. **Download** — Pulls filings from SEC EDGAR by ticker and form type using `sec-edgar-downloader`
2. **Extract** — Parses SGML bundle, extracts primary HTM document (SEQUENCE=1)
3. **Parse** — Sends HTM to LlamaParse → clean Markdown preserving financial tables
4. **Chunk** — `SentenceSplitter` (1024 tokens, 200 overlap) → context-preserving passages
5. **Embed** — Batch-embeds with Cohere `embed-english-v3.0` (1024-dim dense vectors)
6. **Store** — Upserts into Qdrant with `UUID5` IDs (idempotent re-ingestion)

Metadata per chunk: `ticker`, `form_type`, `filing_year`, `section`, `accession_number`, `word_count`. Payload indexes on all filterable fields.

### Query Pipeline (`src/rag_pipeline.py`)

1. **Embed** — Question → 1024-dim vector via Cohere (`input_type="search_query"`)
2. **Retrieve** — Top-20 candidates from Qdrant, filtered by ticker / form type / year
3. **Rerank** — Cohere `rerank-english-v3.0` reorders 20 → top 5
4. **Generate** — Structured prompt + top-5 passages → Cohere `command-r7b` → cited answer
5. **Score** — Faithfulness score + citations with ticker, year, section, excerpt, similarity

---

## Running Locally

### Prerequisites

- Python 3.12+
- Node.js 18+
- [Cohere API key](https://dashboard.cohere.com/) (free tier)
- [Qdrant Cloud cluster](https://cloud.qdrant.io/) (free tier)
- [LlamaCloud API key](https://cloud.llamaindex.ai/) (for LlamaParse)

### Backend

```bash
git clone https://github.com/sriram369/finrag-analyst.git
cd finrag-analyst
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
PYTHONPATH=src:api uvicorn api.main:app --reload --port 8000
```

### Frontend

```bash
cd app
npm install
# create app/.env.local with: NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open [localhost:3000](http://localhost:3000).

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `POST /ingest` | POST | Start ingestion for a ticker. Returns `job_id` |
| `GET /ingest/{job_id}/stream` | GET | SSE stream of live pipeline events |
| `POST /query` | POST | RAG query → answer, citations, latency, cost, faithfulness |
| `GET /metrics` | GET | Qdrant collection stats |
| `GET /health` | GET | Health check |

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

**Backend → Railway** — `railway.toml` is pre-configured. Connect the repo in the Railway dashboard, set env vars, deploy.

Required: `COHERE_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `LLAMA_CLOUD_API_KEY`

**Frontend → Vercel** — `cd app && vercel --prod`. Set `NEXT_PUBLIC_API_URL` to your Railway backend URL.

---

## License

MIT
