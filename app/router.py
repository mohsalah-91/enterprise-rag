from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.database import get_db_pool
from app.ingest import IngestionService, generate_query_embedding

# 1. Initialize the Router
router = APIRouter(prefix="/documents", tags=["Documents"])


# =====================================================================
# SCHEMAS (Request & Response Validation Models)
# =====================================================================

class DocumentIngestRequest(BaseModel):
    title: str = Field(..., json_schema_extra={"example": "Q2 Financial Report"})
    content: str = Field(..., json_schema_extra={"example": "# Enterprise Metrics\n\nRevenue grew by 15% quarter-over-quarter..."})
    doc_id: Optional[str] = Field("doc_001", description="Unique identifier for the document")
    source_path: Optional[str] = Field("manual_upload", description="Source path or file origin")


class SearchQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="The semantic search query")
    limit: int = Field(3, ge=1, le=10, description="Max number of relevant results to return")


class SearchResultResponse(BaseModel):
    id: int
    title: str
    content: str
    chunk_index: int
    similarity: float


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_document(
    payload: DocumentIngestRequest,
    pool = Depends(get_db_pool)  # Injecting the DB connection pool cleanly
):
    """
    Accepts raw enterprise documents, runs hierarchical structural chunking,
    generates 1536-dimension vectors from enriched context, and persists them into pgvector.
    """
    # 1. Break text down using Hierarchical Structural Pipeline
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
    
    # 2. Extract context-prepended text for OpenAI vector generation
    enriched_texts = [chunk["enriched_content"] for chunk in chunks]
    
    try:
        embeddings = await IngestionService.generate_embeddings(enriched_texts)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, 
            detail=f"OpenAI embedding endpoint failure: {str(e)}"
        )
        
    # 3. Secure connection from pool and insert chunks into pgvector
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


@router.post("/search", response_model=list[SearchResultResponse], status_code=status.HTTP_200_OK)
async def search_documents(
    payload: SearchQueryRequest,
    pool = Depends(get_db_pool)  # Injecting the DB connection pool cleanly
):
    """
    Accepts a search query, embeds it into a semantic vector, and returns
    the top-matching document chunks based on Cosine Similarity.
    """
    # 1. Generate the embedding vector for the user's search query string
    query_vector = await generate_query_embedding(payload.query)
    
    # 2. Query Postgres using the Cosine Distance operator (<=>) from pgvector
    query_sql = """
        SELECT 
            id, 
            title, 
            content, 
            chunk_index,
            (1 - (embedding <=> %s::vector)) AS similarity
        FROM document_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """
    
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query_sql, (query_vector, query_vector, payload.limit))
                rows = await cur.fetchall()
                
                results = []
                for row in rows:
                    results.append(
                        SearchResultResponse(
                            id=row[0],
                            title=row[1],
                            content=row[2],
                            chunk_index=row[3],
                            similarity=round(row[4], 4)
                        )
                    )
                return results
                
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database query execution failed: {str(e)}"
        )