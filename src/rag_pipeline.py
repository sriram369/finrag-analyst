"""
FinRAG RAG Pipeline
====================
Question → Cohere embed → Qdrant vector search → Cohere rerank → Gemini answer

answer_question() is the single public function called by the API.
"""

import os
import time
import cohere
import google.generativeai as genai

import vector_store
from config import COHERE_API_KEY, GOOGLE_API_KEY

# ── Clients (module-level so they're reused across requests) ──────────────────
_co = cohere.Client(COHERE_API_KEY)
genai.configure(api_key=GOOGLE_API_KEY)
_gemini = genai.GenerativeModel("gemini-1.5-flash")

# ── Prompt template ───────────────────────────────────────────────────────────
_SYSTEM = """You are FinRAG Analyst, an expert financial analyst that answers questions \
strictly based on SEC filings (10-K, 10-Q).

Rules:
- Answer ONLY from the provided context passages. Never hallucinate.
- Be concise but thorough. Use bullet points for lists.
- If the context doesn't contain the answer, say "I couldn't find that information in the available filings."
- Always reference which company/filing the information comes from.
- For numbers, reproduce them exactly as stated in the filing.
"""

_USER_TMPL = """Context passages from SEC filings:
{context}

---
Question: {question}

Answer:"""


def _embed_query(text: str) -> list[float]:
    """Embed a query string using Cohere embed-english-v3.0."""
    resp = _co.embed(
        texts=[text],
        model="embed-english-v3.0",
        input_type="search_query",
    )
    return resp.embeddings[0]


def _rerank(query: str, chunks: list[dict], top_n: int = 5) -> list[dict]:
    """
    Cohere rerank — re-orders the retrieved chunks by relevance.
    Falls back to original order if rerank fails (e.g. trial limits).
    """
    if not chunks:
        return chunks
    try:
        docs = [c["text"][:2000] for c in chunks]   # Cohere 2k char limit per doc
        resp = _co.rerank(
            query=query,
            documents=docs,
            model="rerank-english-v3.0",
            top_n=min(top_n, len(chunks)),
        )
        return [chunks[r.index] for r in resp.results]
    except Exception as e:
        print(f"[rerank] Falling back to vector order: {e}")
        return chunks[:top_n]


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        m = c["metadata"]
        header = f"[{i}] {m.get('ticker','?')} | {m.get('form_type','?')} {m.get('filing_year','?')} | {m.get('section','?')}"
        parts.append(f"{header}\n{c['text'].strip()}")
    return "\n\n---\n\n".join(parts)


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    # Gemini 1.5 Flash pricing: $0.075/1M input, $0.30/1M output (USD)
    return (input_tokens * 0.075 + output_tokens * 0.30) / 1_000_000


def _faithfulness_score(answer: str, chunks: list[dict]) -> float:
    """
    Simple lexical faithfulness: what fraction of answer sentences
    have a supporting chunk with >=30% word overlap.
    Not perfect, but zero-cost and fast.
    """
    if not chunks or not answer.strip():
        return 1.0
    context_words = set()
    for c in chunks:
        context_words.update(c["text"].lower().split())

    sentences = [s.strip() for s in answer.replace("\n", " ").split(".") if len(s.strip()) > 20]
    if not sentences:
        return 1.0

    supported = 0
    for sent in sentences:
        words = set(sent.lower().split())
        if not words:
            continue
        overlap = len(words & context_words) / len(words)
        if overlap >= 0.30:
            supported += 1
    return round(supported / len(sentences), 2)


def answer_question(
    question: str,
    ticker: str | None = None,
    form_type: str | None = None,
    filing_year: int | None = None,
) -> dict:
    """
    Full RAG pipeline.
    Returns: {answer, citations, cost_usd, faithfulness}
    """
    # 1. Embed question
    q_vec = _embed_query(question)

    # 2. Vector search (top-20 candidates)
    raw_chunks = vector_store.search(
        query_vector=q_vec,
        ticker=ticker,
        form_type=form_type,
        filing_year=filing_year,
        top_k=20,
    )

    if not raw_chunks:
        return {
            "answer": "No relevant filings found. Please ingest some SEC filings first via the Ingest Data page.",
            "citations": [],
            "cost_usd": 0.0,
            "faithfulness": 1.0,
        }

    # 3. Cohere rerank → top-5
    top_chunks = _rerank(question, raw_chunks, top_n=5)

    # 4. Build context + call Gemini
    context = _build_context(top_chunks)
    prompt = _USER_TMPL.format(context=context, question=question)

    response = _gemini.generate_content(
        [_SYSTEM, prompt],
        generation_config={"temperature": 0.1, "max_output_tokens": 1024},
    )
    answer_text = response.text.strip()

    # 5. Estimate cost (Gemini token counts not always available — fallback to char estimate)
    try:
        in_tok = response.usage_metadata.prompt_token_count
        out_tok = response.usage_metadata.candidates_token_count
    except Exception:
        in_tok = len(prompt) // 4
        out_tok = len(answer_text) // 4
    cost = _estimate_cost(in_tok, out_tok)

    # 6. Faithfulness score
    faith = _faithfulness_score(answer_text, top_chunks)

    # 7. Build citations
    citations = []
    for c in top_chunks:
        m = c["metadata"]
        citations.append({
            "chunk_id":    m.get("chunk_id", ""),
            "ticker":      m.get("ticker", ""),
            "form_type":   m.get("form_type", ""),
            "filing_year": m.get("filing_year", 0),
            "section":     m.get("section", ""),
            "excerpt":     c["text"][:400],
            "score":       round(c["score"], 3),
        })

    return {
        "answer":      answer_text,
        "citations":   citations,
        "cost_usd":    cost,
        "faithfulness": faith,
    }
