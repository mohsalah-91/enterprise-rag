# Enterprise RAG

A document question-answering service built so every retrieval stage is inspectable. Hybrid search over Postgres, rank fusion, cross-encoder reranking, and grounded answer synthesis — exposed both as an HTTP API and as MCP tools for Claude Code and Claude Desktop.

The point of this repo is not that it retrieves documents. It's that you can see *why* any given chunk was returned: every result carries its fusion score and its rerank score, and the answer cites the chunks it used.

## How it works

```mermaid
flowchart LR
    Q[User query] --> V[pgvector<br/>dense vector search]
    Q --> L[Postgres GIN + tsvector<br/>lexical search]
    V --> RRF[Reciprocal Rank Fusion]
    L --> RRF
    RRF --> R[Cohere rerank-v3.5]
    R --> C[Claude<br/>answer synthesis]
    C --> A[Answer + cited chunks]
```

**Ingestion.** Documents are split on Markdown heading structure first, with a token-aware recursive splitter as fallback for sections over the target size. Each chunk is stored twice: the clean text that goes to the model, and a breadcrumb-prefixed version (`Context: H1 > H2 > H3`) that gets embedded. Heading hierarchy improves vector quality without polluting the prompt.

**Retrieval.** Dense search over `pgvector` and lexical search over a `tsvector` GIN index run against the same table, and their ranked results are combined with Reciprocal Rank Fusion (k=60). A chunk can surface on semantic similarity, exact keyword match, or both.

**Reranking.** The fused candidate pool goes to Cohere `rerank-v3.5`, a cross-encoder that scores each chunk against the query directly. Retrieval is cheap and approximate; reranking is expensive and accurate. Doing 20 cheaply then 3 expensively is the tradeoff this stage exists to make.

**Synthesis.** The top-k chunks are passed to Claude with a system prompt restricting it to the provided context and requiring inline citations. If retrieval returns nothing, the service says so rather than guessing.

## Requirements

- Python 3.12
- Docker (for Postgres with the `pgvector` extension)
- API keys: OpenAI (embeddings), Cohere (rerank), Anthropic (synthesis)

## Quickstart

```bash
git clone https://github.com/mohsalah-91/enterprise-rag.git
cd enterprise-rag

pip install -r requirements.txt
docker compose up -d
```

Create a `.env` in the repo root:

```
DATABASE_URL=postgresql://rag_admin:CHANGE_ME@localhost:5432/ai_enterprise_db
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
COHERE_API_KEY=...
```

Set the same password in `docker-compose.yml` via `POSTGRES_PASSWORD`.

Start the HTTP API:

```bash
uvicorn app.main:app --reload      # http://127.0.0.1:8000
```

Schema and migrations are applied automatically on startup — no manual migration step.

Add a document and ask a question:

```bash
curl -X POST http://127.0.0.1:8000/documents/ingest \
  -H "Content-Type: application/json" \
  -d '{"title": "Vector Indexing Notes", "content": "# Indexing\n\nWe use pgvector with HNSW and IVFFlat for similarity search."}'

curl -X POST http://127.0.0.1:8000/documents/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "What vector index types are supported?", "top_k": 3}'
```

Interactive API docs are at `http://127.0.0.1:8000/docs`.

## HTTP endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/documents/ingest` | Chunk, embed, and store a document |
| `POST` | `/documents/search` | Hybrid search + rerank, returns scored chunks |
| `POST` | `/documents/answer` | Search, rerank, then synthesize a cited answer |
| `GET` | `/` | Service status |

## MCP tools

The same pipeline is available to Claude Code and Claude Desktop. Start the server (it runs over Streamable HTTP, so it must already be running — the client won't spawn it):

```bash
python mcp_server.py           # http://127.0.0.1:8765/mcp
claude mcp add --transport http enterprise-rag http://127.0.0.1:8765/mcp
```

| Tool | Arguments | Returns |
|---|---|---|
| `query_enterprise_rag` | `query`, `top_k` (default 3) | Answer with cited context |
| `search_raw_chunks` | `query` | Reranked chunks, no synthesis |

Both tools validate input before touching the database or any model: length bounds plus pattern rejection for SQL and prompt-injection payloads. The SQL is already parameterized — this is a policy tripwire, not the primary defense.

See [COOKBOOK.md](COOKBOOK.md) for Claude Desktop setup and a Python client example.

**Why Streamable HTTP and not stdio:** on Windows, the stdio transport hangs the moment a tool makes an outbound async HTTP call to OpenAI, Cohere, or Anthropic. Reproducible independent of event-loop policy, DB access, or client construction order, and consistent with open Windows stdio issues in the MCP Python SDK tracker (GH #2832, #2653). Streamable HTTP runs on the same async stack the FastAPI app already uses without issue.

## Continuous integration

`.github/workflows/rag-ci.yml` runs on every push. It starts Postgres with `pgvector`, launches the MCP server, registers it with the Claude Code CLI, seeds a document containing a known fact, and asks a question about it.

It then asserts two things: that the response contains a fact only present in the seeded document, and that the server log records an actual `CallToolRequest`. The second check matters — without it, a model that answered plausibly from its own knowledge without ever calling the tool would pass the build.

## Project layout

```
app/
  config.py        Pydantic settings, validated at startup
  database.py      Async connection pool, schema, migration runner
  ingest.py        Hierarchical chunking + embedding generation
  router.py        FastAPI endpoints and the shared pipeline functions
  hooks/           Pre-tool input validation
mcp_server.py      MCP tools (calls router.py directly, no HTTP hop)
migrations/        Versioned SQL, applied on startup
scripts/           CI helpers
```

The HTTP endpoints and the MCP tools call the same underlying functions rather than the MCP layer proxying HTTP. There is exactly one implementation of hybrid search and answer synthesis, so the two surfaces can't drift apart.

## Scope and limitations

Stated plainly, because the gap between "works on my corpus" and "works" is where most RAG projects quietly live:

- **No evaluation suite yet.** Retrieval quality is verified by integration test, not measured. There is no labeled question set, no faithfulness or context-precision scoring.
- **No vector index.** The `embedding` column has no HNSW or IVFFlat index, so dense search is an exact sequential scan. Correct and fast at small corpus sizes; the first thing that breaks at scale.
- **No auth or rate limiting** on the HTTP surface. Local and CI use only.
- **Single-tenant, no document provenance.** Chunks carry a title and index but not a document ID or source path.
- **Not deployed anywhere.** Runs locally and in CI.

## Roadmap

1. Evaluation harness — labeled question set, Ragas scoring for faithfulness, answer relevancy, context precision, and context recall
2. Retrieval ablation using that harness — dense only vs. lexical only vs. RRF vs. RRF + rerank, on one corpus with one question set
3. Per-stage latency (p50/p95), token counts, and cost per query; add HNSW and measure where sequential scan stops being viable
4. Unit tests for chunking, breadcrumb construction, RRF scoring, and input validation
5. Batch embedding on ingest; `doc_id` and `source_path` columns for provenance

## License

MIT
