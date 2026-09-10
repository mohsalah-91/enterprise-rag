"""
CI-only helper for .github/workflows/rag-ci.yml.

Seeds one test document so the workflow's query_enterprise_rag smoke test
has real content to retrieve instead of hitting the "no relevant
information" fallback.

Runs app.database.lifespan directly, which creates the schema and applies
migrations -- the same code path a real MCP client session triggers on
connect.
"""
import asyncio
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from app.database import lifespan, pool

SEED_TITLE = "CI Verification Document"
SEED_CONTENT = (
    "We utilize pgvector with HNSW and IVFFlat indexing for vector "
    "similarity search."
)


async def main() -> None:
    async with lifespan(None):
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO document_chunks (title, chunk_index, content) VALUES (%s, %s, %s)",
                    (SEED_TITLE, 0, SEED_CONTENT),
                )
            await conn.commit()
    print("Schema ensured, migration applied, and CI test document seeded.")


if __name__ == "__main__":
    asyncio.run(main())
