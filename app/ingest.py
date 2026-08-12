import openai
from openai import AsyncOpenAI
from fastapi import HTTPException
from app.config import settings

# Initialize the asynchronous OpenAI client
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class IngestionService:
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
        """
        Splits a larger text string into smaller, overlapping semantic blocks.
        """
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size - chunk_overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            chunks.append(chunk_text)
            
            # Stop if we've reached the end of the text
            if i + chunk_size >= len(words):
                break
                
        return chunks

    @staticmethod
    async def generate_embeddings(chunks: list[str]) -> list[list[float]]:
        """
        Sends chunks to OpenAI to generate 1536-dimensional vectors.
        """
        try:
            response = await openai_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=chunks
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            raise Exception(f"Failed to generate embeddings from OpenAI: {str(e)}")


async def generate_query_embedding(query_text: str) -> list[float]:
    """
    Generates a single vector embedding for a user's search query.
    """
    try:
        response = await openai_client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=query_text
        )
        return response.data[0].embedding
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OpenAI embedding search failure: {str(e)}"
        )