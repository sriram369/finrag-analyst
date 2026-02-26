from pydantic import BaseModel


class IngestRequest(BaseModel):
    tickers: list[str] = ["AAPL"]
    filing_types: list[str] = ["10-K"]
    limit: int = 2


class QueryRequest(BaseModel):
    question: str
    ticker: str | None = None
    form_type: str | None = None
    filing_year: int | None = None


class Citation(BaseModel):
    chunk_id: str
    ticker: str
    form_type: str
    filing_year: int
    section: str
    excerpt: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    cost_usd: float
    latency_ms: int
    faithfulness: float | None = None
