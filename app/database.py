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
    await pool.close()