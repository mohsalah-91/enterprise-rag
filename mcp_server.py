"""
MCP server exposing the Enterprise RAG pipeline (pgvector + BM25 hybrid search,
Cohere rerank, Claude answer synthesis) as tools for Claude Code / Claude Desktop.

Run directly for local stdio use:
    python mcp_server.py
"""
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.database import lifespan, pool
from app.router import SearchResultResponse, _hybrid_search_and_rerank, _synthesize_answer

mcp = FastMCP("enterprise-rag", lifespan=lifespan)


def _serialize_chunks(chunks: List[SearchResultResponse]) -> List[Dict[str, Any]]:
    return [chunk.model_dump() for chunk in chunks]


@mcp.tool()
async def query_enterprise_rag(query: str, top_k: int = 3) -> Dict[str, Any]:
    """
    Answer a natural-language question using the enterprise knowledge base.

    Runs hybrid search (pgvector dense + Postgres full-text lexical) fused with
    Reciprocal Rank Fusion, reranks the candidates with Cohere, then asks Claude
    to synthesize an answer strictly grounded in the retrieved chunks, citing
    their chunk IDs or titles.

    Args:
        query: The natural-language question to answer.
        top_k: Max number of reranked chunks to use as context (default 3).

    Returns:
        A dict with `query`, `answer`, `retrieved_context`, and `model_used`.
    """
    retrieved_context = await _hybrid_search_and_rerank(query, top_k, pool)
    answer = await _synthesize_answer(query, retrieved_context)
    return answer.model_dump()


@mcp.tool()
async def search_raw_chunks(query: str) -> List[Dict[str, Any]]:
    """
    Run hybrid search + Cohere rerank and return the raw reranked document
    chunks, without invoking Claude for answer synthesis.

    Args:
        query: The semantic or keyword search query.

    Returns:
        A list of reranked chunk dicts (id, title, content, chunk_index,
        rrf_score, rerank_score).
    """
    results = await _hybrid_search_and_rerank(query, settings.RAG_DEFAULT_TOP_K, pool)
    return _serialize_chunks(results)


if __name__ == "__main__":
    mcp.run()
