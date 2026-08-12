from typing import Dict, List, Any
from datetime import datetime, timezone
import openai
from openai import AsyncOpenAI
from fastapi import HTTPException
import tiktoken
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.config import settings

# Initialize the asynchronous OpenAI client
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class HierarchicalIngestionPipeline:
    """
    Production-grade text splitter utilizing a two-pass strategy:
    1. Splits on Markdown structural headings (# H1, ## H2, ### H3).
    2. Uses a token-aware recursive splitter fallback for sections exceeding target size.
    3. Prepends structural breadcrumbs to chunk embeddings to retain context.
    """
    def __init__(
        self,
        target_chunk_size: int = 512,
        chunk_overlap: int = 64,
        encoding_name: str = "cl100k_base"
    ):
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.get_encoding(encoding_name)

        # Pass 1: Structural Header Splitter
        self.headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
            ("####", "Header 4"),
        ]
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
            strip_headers=False
        )

        # Pass 2: Token-aware recursive text splitter fallback
        self.recursive_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=encoding_name,
            chunk_size=self.target_chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", " ", ""]
        )

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))

    def _build_breadcrumb(self, headers: Dict[str, str]) -> str:
        """Constructs breadcrumb path from extracted headers."""
        breadcrumbs = [val for key, val in headers.items() if val]
        if not breadcrumbs:
            return ""
        return " > ".join(breadcrumbs) + "\n\n"

    def process_document(
        self,
        raw_text: str,
        doc_id: str,
        source_path: str
    ) -> List[Dict[str, Any]]:
        """
        Parses document text into contextual chunks.
        Returns a list of dict payloads ready for embedding and storage.
        """
        processed_chunks: List[Dict[str, Any]] = []

        # Step 1: Structural Split based on Headers
        header_splits = self.markdown_splitter.split_text(raw_text)
        chunk_counter = 0

        # Step 2: Fallback split if a section exceeds the target token limit
        for split in header_splits:
            headers = split.metadata
            content = split.page_content

            if self.count_tokens(content) > self.target_chunk_size:
                sub_docs = self.recursive_splitter.create_documents(
                    texts=[content],
                    metadatas=[headers]
                )
            else:
                sub_docs = [split]

            # Step 3: Enrich chunks with metadata and breadcrumbs
            for sub_doc in sub_docs:
                chunk_text = sub_doc.page_content
                breadcrumb_prefix = self._build_breadcrumb(headers)

                # Context Prepending: Prepends header hierarchy for vector quality
                enriched_text = f"Context: {breadcrumb_prefix}{chunk_text}"
                token_len = self.count_tokens(chunk_text)

                chunk_payload = {
                    "chunk_id": f"{doc_id}_chunk_{chunk_counter}",
                    "content": chunk_text,                # Original text (for LLM context)
                    "enriched_content": enriched_text,    # Header-prepended text (for vector generation)
                    "doc_id": doc_id,
                    "source_path": source_path,
                    "chunk_index": chunk_counter,
                    "headers": headers,
                    "token_count": token_len,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }

                processed_chunks.append(chunk_payload)
                chunk_counter += 1

        return processed_chunks


class IngestionService:
    pipeline = HierarchicalIngestionPipeline()

    @classmethod
    def chunk_text(cls, text: str, doc_id: str = "doc", source_path: str = "raw_input") -> List[Dict[str, Any]]:
        """
        Splits text using the HierarchicalIngestionPipeline.
        """
        return cls.pipeline.process_document(raw_text=text, doc_id=doc_id, source_path=source_path)

    @staticmethod
    async def generate_embeddings(chunks: List[str]) -> List[List[float]]:
        """
        Sends enriched chunk strings to OpenAI to generate vector embeddings.
        """
        try:
            response = await openai_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=chunks
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            raise Exception(f"Failed to generate embeddings from OpenAI: {str(e)}")


async def generate_query_embedding(query_text: str) -> List[float]:
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