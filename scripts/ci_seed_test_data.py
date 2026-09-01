"""
CI-only helper for .github/workflows/rag-ci.yml.

Ensures the database schema exists, applies the fts_tokens migration
(migrations/001_add_fts_tokens.sql), and seeds one test document -- so the
workflow's query_enterprise_rag smoke test has real content to retrieve
instead of hitting the "no relevant information" fallback.

Runs app.database.lifespan directly (the same schema-creation code path a
real MCP client session triggers on connect) rather than duplicating its
DDL, since this script runs standalone before any MCP client has connected.
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
    migration_path = os.path.join(REPO_ROOT, "migrations", "001_add_fts_tokens.sql")
    async with lifespan(None):
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                with open(migration_path) as f:
                    await cur.execute(f.read())

                await cur.execute(
                    "INSERT INTO document_chunks (title, chunk_index, content) VALUES (%s, %s, %s)",
                    (SEED_TITLE, 0, SEED_CONTENT),
                )
            await conn.commit()
    print("Schema ensured, migration applied, and CI test document seeded.")


if __name__ == "__main__":
    asyncio.run(main())
