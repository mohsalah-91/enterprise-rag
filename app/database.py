from pathlib import Path
import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from app.config import settings

logger = logging.getLogger(__name__)

# path for the migrations folder
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# psycopg's async pool cannot run under Windows' default ProactorEventLoop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize a non-blocking, async connection pool for high-throughput enterprise performance
pool = AsyncConnectionPool(conninfo=settings.DATABASE_URL, open=False)


async def _apply_migrations(cur):
    if not MIGRATIONS_DIR.exists():
        raise RuntimeError(f"migrations directory not found: {MIGRATIONS_DIR}")
    for file_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql_script = file_path.read_text(encoding="utf-8")
        if sql_script.strip():
            logger.info("Applying migrations %s", file_path.name)
            await cur.execute(sql_script)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Action on startup: Open connection pool
    await pool.open()

    # Ensure pgvector extension and structural tables are initialized
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # 1. Activate vector plugin
            await cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # 2. Build table structure matching OpenAI text-embedding-3-small (1536 dimensions)
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    chunk_index INT NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            await _apply_migrations(cur)
            await conn.commit()

    yield
    # Action on shutdown: Cleanly close pool hooks
    await pool.close()


async def get_db_pool():
    """
    Dependency helper to yield our database connection pool.
    """
    return pool
