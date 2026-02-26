import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────────────────────────
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "")
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "")
COHERE_API_KEY      = os.getenv("COHERE_API_KEY", "")

# ── Qdrant Cloud (vector database) ───────────────────────────────────────────
QDRANT_URL          = os.getenv("QDRANT_URL", "")        # e.g. https://xyz.qdrant.io
QDRANT_API_KEY      = os.getenv("QDRANT_API_KEY", "")
QDRANT_COLLECTION   = os.getenv("QDRANT_COLLECTION", "finrag")

# ── SEC EDGAR identity (required by SEC) ──────────────────────────────────────
SEC_USER_AGENT_NAME  = os.getenv("SEC_USER_AGENT_NAME", "FinRAG Analyst")
SEC_USER_AGENT_EMAIL = os.getenv("SEC_USER_AGENT_EMAIL", "finrag@example.com")

# ── Paths (local / Railway ephemeral disk) ────────────────────────────────────
ROOT_DIR           = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_RAW_DIR       = os.getenv("DATA_RAW_DIR",       os.path.join(ROOT_DIR, "data", "raw"))
DATA_PROCESSED_DIR = os.getenv("DATA_PROCESSED_DIR", os.path.join(ROOT_DIR, "data", "processed"))

# ── Companies ─────────────────────────────────────────────────────────────────
TICKERS       = ["AAPL", "MSFT", "NVDA", "JPM", "GS", "META", "GOOGL", "AMZN", "TSLA", "BLK"]
FILING_TYPES  = ["10-K", "10-Q"]

# ── Chunking ──────────────────────────────────────────────────────────────────
EMBED_MODEL_NAME = "BAAI/bge-large-en-v1.5"
EMBED_DIMENSION  = 1024

# ── SEC regulatory sections ───────────────────────────────────────────────────
SEC_SECTIONS = {
    "item_1":  "Business Overview",
    "item_1a": "Risk Factors",
    "item_1b": "Unresolved Staff Comments",
    "item_2":  "Properties",
    "item_3":  "Legal Proceedings",
    "item_7":  "MD&A",
    "item_7a": "Quantitative Disclosures About Market Risk",
    "item_8":  "Financial Statements",
    "item_9a": "Controls and Procedures",
}
