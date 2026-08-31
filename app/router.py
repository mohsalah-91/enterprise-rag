from typing import Optional, List
import cohere
from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.config import settings
from app.database import get_db_pool
from app.ingest import IngestionService, generate_query_embedding

# 1. Initialize the Router
router = APIRouter(prefix="/documents", tags=["Documents"])

# Async Cohere client for reranking (non-blocking, safe to call from async endpoints)
cohere_client = cohere.AsyncClientV2(api_key=settings.COHERE_API_KEY)

# Async Anthropic client for answer synthesis (non-blocking, safe to call from async endpoints)
anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


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


class AnswerRequest(BaseModel):
    query: str = Field(..., min_length=3, description="The natural-language question to answer")
    top_k: int = Field(3, ge=1, le=10, description="Max number of reranked chunks to use as context")


class AnswerResponse(BaseModel):
    query: str
    answer: str
    retrieved_context: List[SearchResultResponse]
    model_used: str


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


async def _hybrid_search_and_rerank(query: str, limit: int, pool) -> List[SearchResultResponse]:
    """
    Executes Hybrid Search combining Dense Vector Search (pgvector) and
    Sparse Lexical Search (Postgres tsvector/BM25) using Reciprocal Rank Fusion (RRF),
    then reranks the fused candidate pool with Cohere's rerank-v3.5 model.
    """
    candidate_fetch_limit = 20
    rrf_k = 60.0  # Standard smoothing constant for RRF

    # 1. Generate query embedding for vector path
    query_vector = await generate_query_embedding(query)

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
                await cur.execute(lexical_sql, (query, query, candidate_fetch_limit))
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
            query=query,
            documents=[doc_map[doc_id]["content"] for doc_id, _ in candidates],
            top_n=limit
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
    return await _hybrid_search_and_rerank(payload.query, payload.limit, pool)


async def _synthesize_answer(query: str, retrieved_context: List[SearchResultResponse]) -> AnswerResponse:
    """
    Step B + Step C of the answer pipeline: builds a strictly-grounded system
    prompt from the retrieved chunks and calls Claude to synthesize a cited answer.
    Shared by the /answer HTTP endpoint and the MCP `query_enterprise_rag` tool
    so both surfaces stay identical.
    """
    if not retrieved_context:
        return AnswerResponse(
            query=query,
            answer="I could not find any relevant information in the knowledge base to answer this query.",
            retrieved_context=[],
            model_used=settings.ANSWER_MODEL
        )

    # Step B: Build a strictly-grounded system prompt with citation instructions
    context_blocks = "\n\n".join(
        f"[Chunk ID: {chunk.id} | Title: {chunk.title} | Chunk Index: {chunk.chunk_index}]\n{chunk.content}"
        for chunk in retrieved_context
    )

    system_prompt = (
        "You are an enterprise document assistant. Answer the user's query using ONLY the "
        "information contained in the context chunks provided below. Do not use any prior "
        "or outside knowledge. If the context does not contain enough information to answer "
        "the query, say so explicitly instead of guessing. When you use information from a "
        "chunk, cite it inline using its Chunk ID or Title (e.g., \"(Source: Chunk ID 12, "
        "'Q2 Financial Report')\").\n\n"
        f"Context:\n{context_blocks}"
    )

    # Step C: Call the Anthropic Messages API to synthesize the grounded answer
    try:
        response = await anthropic_client.messages.create(
            model=settings.ANSWER_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": query}]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Anthropic answer synthesis failure: {str(e)}"
        )

    answer_text = next((block.text for block in response.content if block.type == "text"), "")

    return AnswerResponse(
        query=query,
        answer=answer_text,
        retrieved_context=retrieved_context,
        model_used=settings.ANSWER_MODEL
    )


@router.post("/answer", response_model=AnswerResponse, status_code=status.HTTP_200_OK)
async def answer_query(
    payload: AnswerRequest,
    pool = Depends(get_db_pool)
):
    """
    Answers a natural-language query by retrieving the most relevant document
    chunks via hybrid search + Cohere reranking, then synthesizing a grounded
    answer with Claude, citing the source chunks it drew from.
    """
    # Step A: Hybrid search + Cohere rerank to get the top N relevant chunks
    retrieved_context = await _hybrid_search_and_rerank(payload.query, payload.top_k, pool)
    return await _synthesize_answer(payload.query, retrieved_context)