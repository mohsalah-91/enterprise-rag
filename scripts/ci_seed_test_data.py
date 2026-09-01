"""
CI-only helper for .github/workflows/rag-ci.yml.

Applies the fts_tokens migration (migrations/001_add_fts_tokens.sql) and
seeds one test document, so the workflow's query_enterprise_rag smoke test
has real content to retrieve instead of hitting the "no relevant
information" fallback. Must run after mcp_server.py's lifespan has already
created the document_chunks table (the migration ALTERs an existing table).
"""
import os

import psycopg

SEED_TITLE = "CI Verification Document"
SEED_CONTENT = (
    "We utilize pgvector with HNSW and IVFFlat indexing for vector "
    "similarity search."
)


def main() -> None:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            with open("migrations/001_add_fts_tokens.sql") as f:
                cur.execute(f.read())

            cur.execute(
                "INSERT INTO document_chunks (title, chunk_index, content) VALUES (%s, %s, %s)",
                (SEED_TITLE, 0, SEED_CONTENT),
            )
        print("Migration applied and CI test document seeded.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
