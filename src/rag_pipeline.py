"""
FinRAG RAG Pipeline
====================
Question → Cohere embed → Qdrant vector search → Cohere rerank → Gemini answer

answer_question() is the single public function called by the API.
"""

import cohere
from llama_index.embeddings.cohere import CohereEmbedding

import vector_store
from config import COHERE_API_KEY

# ── Clients (module-level, reused across requests) ────────────────────────────
_embed_model = CohereEmbedding(
    api_key=COHERE_API_KEY,
    model_name="embed-english-v3.0",
    input_type="search_query",
)
_co = cohere.Client(COHERE_API_KEY)

# ── Prompt template ───────────────────────────────────────────────────────────
_SYSTEM = (
    "You are FinRAG Analyst, an expert financial analyst that answers questions "
    "strictly based on SEC filings (10-K, 10-Q).\n\n"
    "Rules:\n"
    "- Answer ONLY from the provided context passages. Never hallucinate.\n"
    "- Be concise but thorough. Use bullet points for lists.\n"
    "- If the context doesn't contain the answer, say "
    "\"I couldn't find that information in the available filings.\"\n"
    "- Always reference which company/filing the information comes from.\n"
    "- For numbers, reproduce them exactly as stated in the filing.\n"
)

_USER_TMPL = "Context passages from SEC filings:\n{context}\n\n---\nQuestion: {question}\n\nAnswer:"


def _embed_query(text: str) -> list[float]:
    return _embed_model.get_text_embedding(text)


def _rerank(query: str, chunks: list[dict], top_n: int = 5) -> list[dict]:
    """Cohere rerank — falls back to vector order on failure (trial limits etc.)."""
    if not chunks:
        return chunks
    try:
        docs = [c["text"][:2000] for c in chunks]
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
        header = (
            f"[{i}] {m.get('ticker','?')} | "
            f"{m.get('form_type','?')} {m.get('filing_year','?')} | "
            f"{m.get('section','?')}"
        )
        parts.append(f"{header}\n{c['text'].strip()}")
    return "\n\n---\n\n".join(parts)


def _faithfulness_score(answer: str, chunks: list[dict]) -> float:
    """Lexical faithfulness: fraction of answer sentences supported by context."""
    if not chunks or not answer.strip():
        return 1.0
    context_words = set()
    for c in chunks:
        context_words.update(c["text"].lower().split())

    sentences = [s.strip() for s in answer.replace("\n", " ").split(".") if len(s.strip()) > 20]
    if not sentences:
        return 1.0

    supported = sum(
        1 for sent in sentences
        if (words := set(sent.lower().split()))
        and len(words & context_words) / len(words) >= 0.30
    )
    return round(supported / len(sentences), 2)


def answer_question(
    question: str,
    ticker: str | None = None,
    form_type: str | None = None,
    filing_year: int | None = None,
) -> dict:
    """Full RAG pipeline. Returns {answer, citations, cost_usd, faithfulness}."""

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
            "answer": (
                "No relevant filings found in the knowledge base. "
                "Please ingest some SEC filings first via the **Ingest Data** page."
            ),
            "citations": [],
            "cost_usd": 0.0,
            "faithfulness": 1.0,
        }

    # 3. Cohere rerank → top-5
    top_chunks = _rerank(question, raw_chunks, top_n=5)

    # 4. Build context + call Cohere Command-R
    context = _build_context(top_chunks)
    prompt = _USER_TMPL.format(context=context, question=question)

    response = _co.chat(
        message=prompt,
        model="command-r7b-12-2024",
        preamble=_SYSTEM,
        temperature=0.1,
        max_tokens=1024,
    )
    answer_text = response.text.strip()

    # 5. Estimate cost (Command-R: $0.15/1M input, $0.60/1M output)
    in_tok = len(prompt) // 4
    out_tok = len(answer_text) // 4
    cost = (in_tok * 0.15 + out_tok * 0.60) / 1_000_000

    # 6. Faithfulness + citations
    faith = _faithfulness_score(answer_text, top_chunks)

    citations = [
        {
            "chunk_id":    c["metadata"].get("chunk_id", ""),
            "ticker":      c["metadata"].get("ticker", ""),
            "form_type":   c["metadata"].get("form_type", ""),
            "filing_year": c["metadata"].get("filing_year", 0),
            "section":     c["metadata"].get("section", ""),
            "excerpt":     c["text"][:400],
            "score":       round(c["score"], 3),
        }
        for c in top_chunks
    ]

    return {
        "answer":      answer_text,
        "citations":   citations,
        "cost_usd":    cost,
        "faithfulness": faith,
    }
