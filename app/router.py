from typing import Optional, List
import cohere
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.config import settings
from app.database import get_db_pool
from app.ingest import IngestionService, generate_query_embedding

# 1. Initialize the Router
router = APIRouter(prefix="/documents", tags=["Documents"])

# Async Cohere client for reranking (non-blocking, safe to call from async endpoints)
cohere_client = cohere.AsyncClientV2(api_key=settings.COHERE_API_KEY)


# =====================================================================
# SCHEMAS (Request & Response Validation Models)
# =====================================================================

class DocumentIngestRequest(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "Q2 Financial Report"})
    content: str = Field(..., json_schema_extra={"example": "# Enterprise Metrics\n\nRevenue grew by 15% quarter-over-quarter..."})
    doc_id: Optional[str] = Field("doc_001", description="Unique identifier for the document")
    source_path: Optional[str] = Field("manual_upload", description="Source path or file origin")


class SearchQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="The semantic or keyword search query")
    limit: int = Field(3, ge=1, le=10, description="Max number of relevant results to return")


class SearchResultResponse(BaseModel):
    id: int
    title: str
    content: str
    chunk_index: int
    rrf_score: float
    rerank_score: float


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_document(
    payload: DocumentIngestRequest,
    pool = Depends(get_db_pool)
):
    """
    Accepts raw enterprise documents, runs hierarchical structural chunking,
    generates 1536-dimension vectors from enriched context, and persists them into pgvector.
    """
    chunks = IngestionService.chunk_text(
        text=payload.content,
        doc_id=payload.doc_id or "doc",
        source_path=payload.source_path or "raw_input"
    )
    
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Document content yields zero structural chunks."
        )
    
    enriched_texts = [chunk["enriched_content"] for chunk in chunks]
    
    try:
        embeddings = await IngestionService.generate_embeddings(enriched_texts)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, 
            detail=f"OpenAI embedding endpoint failure: {str(e)}"
        )
        
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            try:
                for chunk, vector in zip(chunks, embeddings):
                    await cur.execute(
                        """
                        INSERT INTO document_chunks (title, chunk_index, content, embedding)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (payload.title, chunk["chunk_index"], chunk["content"], vector)
                    )
                await conn.commit()
            except Exception as db_err:
                await conn.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database transaction aborted: {str(db_err)}"
                )

    return {
        "message": "Document successfully ingested with hierarchical context",
        "chunks_processed": len(chunks)
    }


@router.post("/search", response_model=List[SearchResultResponse], status_code=status.HTTP_200_OK)
async def search_documents(
    payload: SearchQueryRequest,
    pool = Depends(get_db_pool)
):
    """
    Executes Hybrid Search combining Dense Vector Search (pgvector) and
    Sparse Lexical Search (Postgres tsvector/BM25) using Reciprocal Rank Fusion (RRF),
    then reranks the fused candidate pool with Cohere's rerank-v3.5 model.
    """
    candidate_fetch_limit = 20
    rrf_k = 60.0  # Standard smoothing constant for RRF

    # 1. Generate query embedding for vector path
    query_vector = await generate_query_embedding(payload.query)
    
    # 2. Parallel Queries: Vector + Full-Text Search
    vector_sql = """
        SELECT id, title, content, chunk_index
        FROM document_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """

    lexical_sql = """
        SELECT id, title, content, chunk_index,
               ts_rank_cd(fts_tokens, websearch_to_tsquery('english', %s)) AS rank_score
        FROM document_chunks
        WHERE fts_tokens @@ websearch_to_tsquery('english', %s)
        ORDER BY rank_score DESC
        LIMIT %s;
    """

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # Execute Dense Search
                await cur.execute(vector_sql, (query_vector, candidate_fetch_limit))
                vector_rows = await cur.fetchall()

                # Execute Lexical Search
                await cur.execute(lexical_sql, (payload.query, payload.query, candidate_fetch_limit))
                lexical_rows = await cur.fetchall()

        # 3. Compute Reciprocal Rank Fusion (RRF)
        rrf_scores = {}
        doc_map = {}

        # Rank Vector Results
        for rank, row in enumerate(vector_rows, start=1):
            doc_id, title, content, chunk_index = row[0], row[1], row[2], row[3]
            doc_map[doc_id] = {"id": doc_id, "title": title, "content": content, "chunk_index": chunk_index}
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

        # Rank Lexical Results
        for rank, row in enumerate(lexical_rows, start=1):
            doc_id, title, content, chunk_index = row[0], row[1], row[2], row[3]
            if doc_id not in doc_map:
                doc_map[doc_id] = {"id": doc_id, "title": title, "content": content, "chunk_index": chunk_index}
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

        # 4. Sort documents by top RRF score and take a candidate pool for reranking
        sorted_docs = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
        rerank_candidate_limit = 20
        candidates = sorted_docs[:rerank_candidate_limit]

        if not candidates:
            return []

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Hybrid search execution failed: {str(e)}"
        )

    # 5. Rerank the candidate pool with Cohere to sharpen relevance ordering
    try:
        rerank_response = await cohere_client.rerank(
            model=settings.RERANK_MODEL,
            query=payload.query,
            documents=[doc_map[doc_id]["content"] for doc_id, _ in candidates],
            top_n=payload.limit
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cohere rerank endpoint failure: {str(e)}"
        )

    results = []
    for reranked_doc in rerank_response.results:
        doc_id, rrf_score = candidates[reranked_doc.index]
        doc_info = doc_map[doc_id]
        results.append(
            SearchResultResponse(
                id=doc_info["id"],
                title=doc_info["title"],
                content=doc_info["content"],
                chunk_index=doc_info["chunk_index"],
                rrf_score=round(rrf_score, 6),
                rerank_score=round(reranked_doc.relevance_score, 6)
            )
        )

    return results