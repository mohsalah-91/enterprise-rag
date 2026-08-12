import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from app.config import settings

# Initialize a non-blocking, async connection pool for high-throughput enterprise performance
pool = AsyncConnectionPool(conninfo=settings.DATABASE_URL, open=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Action on startup: Open connection pool
    await pool.open()
    
    # Ensure pgvector extension is explicitly initialized in the target DB schema
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await conn.commit()
            
    yield
    # Action on shutdown: Cleanly close pool hooks
    await pool.close()@asynccontextmanager
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
            await conn.commit()
            
    yield
    # Action on shutdown: Cleanly close pool hooks
    await pool.close()
    # Add this function to the bottom of app/database.py
async def get_db_pool():
    """
    Dependency helper to yield our database connection pool.
    """
    return pool