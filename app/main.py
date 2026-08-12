from fastapi import FastAPI, status
from app.database import lifespan
from app.config import settings
from app.router import router as document_router # Import our router

app = FastAPI(
    title="Enterprise AI Knowledge Retrieval API",
    version="1.0.0",
    lifespan=lifespan
)

# Attach ingestion endpoints to the application core
app.include_router(document_router)

@app.get("/", status_code=status.HTTP_200_OK)
async def get_system_status():
    """Returns application metadata safely without exposing secret keys."""
    return {
        "status": "online",
        "environment": settings.ENVIRONMENT,
        "embedding_engine": settings.EMBEDDING_MODEL
    }