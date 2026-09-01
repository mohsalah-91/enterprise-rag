"""
MCP server exposing the Enterprise RAG pipeline (pgvector + BM25 hybrid search,
Cohere rerank, Claude answer synthesis) as tools for Claude Code / Claude Desktop.

Runs over Streamable HTTP rather than stdio: the stdio transport reliably hangs
on Windows once a tool makes an outbound async HTTP call (OpenAI/Cohere/Anthropic),
regardless of event loop policy -- see the mcp Python SDK's Windows stdio issues
(e.g. GH #2832, #2653). Streamable HTTP uses the same async stack this repo's
FastAPI app already runs fine on, and does not exhibit the hang.

Run directly:
    python mcp_server.py
Serves at http://127.0.0.1:8765/mcp by default; override with the
MCP_SERVER_PORT environment variable (e.g. for CI).
"""
import os
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.database import lifespan, pool
from app.hooks.pre_tool_use import validate_mcp_input
from app.router import SearchResultResponse, _hybrid_search_and_rerank, _synthesize_answer

MCP_SERVER_PORT = int(os.environ.get("MCP_SERVER_PORT", "8765"))

mcp = FastMCP("enterprise-rag", lifespan=lifespan, host="127.0.0.1", port=MCP_SERVER_PORT)


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
    validation = validate_mcp_input("query_enterprise_rag", {"query": query, "top_k": top_k})
    if not validation.is_valid:
        raise ValueError(validation.message)

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
    validation = validate_mcp_input("search_raw_chunks", {"query": query})
    if not validation.is_valid:
        raise ValueError(validation.message)

    results = await _hybrid_search_and_rerank(query, settings.RAG_DEFAULT_TOP_K, pool)
    return _serialize_chunks(results)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
