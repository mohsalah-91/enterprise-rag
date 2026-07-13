import re
from typing import List, Dict, Any
from openai import AsyncOpenAI
from app.config import settings

# Initialize the asynchronous OpenAI client using our validated config settings
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

class IngestionService:
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
        """
        Splits raw document string data into clean semantic chunks with an explicit overlap threshold.
        Ensures contextual continuity across chunk boundaries.
        """
        # Clean up excessive whitespace characters
        clean_text = re.sub(r'\s+', ' ', text).strip()
        words = clean_text.split(' ')
        
        chunks = []
        import_index = 0
        
        while import_index < len(words):
            # Take a slice of words based on the chunk size
            word_slice = words[import_index : import_index + chunk_size]
            chunk_content = " ".join(word_slice)
            chunks.append(chunk_content)
            
            # Slide the window forward by chunk_size minus the overlap
            import_index += (chunk_size - chunk_overlap)
            
            # Fail-safe break to prevent infinite loops if misconfigured
            if chunk_size <= chunk_overlap:
                break
                
        return chunks

    @staticmethod
    async def generate_embeddings(text_chunks: List[str]) -> List[List[float]]:
        """
        Dispatches text chunks to the OpenAI API concurrently to generate high-dimensional vector embeddings.
        """
        # Safeguard against empty payloads
        if not text_chunks:
            return []
            
        response = await openai_client.embeddings.create(
            input=text_chunks,
            model=settings.EMBEDDING_MODEL
        )
        
        # Extract the float arrays from the response payload sorted by original index
        return [data.embedding for data in response.data]