"""
Qdrant Cloud vector store operations.
All chunks from every filing are stored here.
"""

import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue, QueryRequest,
)
from config import QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION, EMBED_DIMENSION

# Fixed namespace for deterministic UUIDs from chunk_id strings
_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def ensure_collection() -> None:
    """Create the Qdrant collection and payload indexes if they don't exist."""
    from qdrant_client.models import PayloadSchemaType
    client = get_client()
    existing = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIMENSION, distance=Distance.COSINE),
        )

    # Always ensure payload indexes exist (safe to call on existing collections —
    # Qdrant will backfill indexes over any pre-existing points)
    for field, ftype in [
        ("ticker",      PayloadSchemaType.KEYWORD),
        ("form_type",   PayloadSchemaType.KEYWORD),
        ("filing_year", PayloadSchemaType.INTEGER),
        ("section",     PayloadSchemaType.KEYWORD),
    ]:
        try:
            client.create_payload_index(
                collection_name=QDRANT_COLLECTION,
                field_name=field,
                field_schema=ftype,
            )
        except Exception:
            pass  # index already exists — that's fine


def upsert_chunks(chunks: list[dict], vectors: list[list[float]]) -> int:
    """
    Store chunks + their vectors in Qdrant.
    Uses uuid5(chunk_id) for IDs — deterministic and collision-free.
    Returns number of points upserted.
    """
    client = get_client()
    points = [
        PointStruct(
            id=str(uuid.uuid5(_NS, chunk["chunk_id"])),  # UUID string — no collisions
            vector=vector,
            payload={
                "chunk_id": chunk["chunk_id"],
                "text":     chunk["text"],
                **chunk["metadata"],
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    return len(points)


def search(
    query_vector: list[float],
    ticker: str | None = None,
    form_type: str | None = None,
    filing_year: int | None = None,
    top_k: int = 20,
) -> list[dict]:
    """
    Vector search with optional metadata filters.
    Returns list of {text, metadata, score}.
    Uses query_points() — qdrant-client v1.7+ API.
    """
    client = get_client()

    conditions = []
    if ticker:
        conditions.append(FieldCondition(key="ticker", match=MatchValue(value=ticker)))
    if form_type:
        conditions.append(FieldCondition(key="form_type", match=MatchValue(value=form_type)))
    if filing_year:
        conditions.append(FieldCondition(key="filing_year", match=MatchValue(value=filing_year)))

    query_filter = Filter(must=conditions) if conditions else None

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    ).points

    return [
        {
            "text":     hit.payload.get("text", ""),
            "metadata": {k: v for k, v in hit.payload.items() if k != "text"},
            "score":    hit.score,
        }
        for hit in results
    ]


def collection_info() -> dict:
    """Return basic stats about the collection."""
    client = get_client()
    try:
        info = client.get_collection(QDRANT_COLLECTION)
        return {
            "total_chunks": info.points_count,
            "status":       str(info.status),
        }
    except Exception:
        return {"total_chunks": 0, "status": "not_found"}
