"""
Embedding generation service using Hugging Face API with text chunking.
"""
import os
import asyncio
import json
from typing import List, Dict, Any, Optional
# pyrefly: ignore [missing-import]
import asyncpg
# pyrefly: ignore [missing-import]
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from dotenv import load_dotenv
import tiktoken

load_dotenv()

class EmbeddingService:
    """Generate and store embeddings for text chunks"""
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        model_name: str = "BAAI/bge-large-en-v1.5",
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        """
        Initialize the embedding service.
        
        Args:
            db_pool: Database connection pool
            model_name: Hugging Face Embedding model name
            chunk_size: Maximum tokens per chunk
            chunk_overlap: Overlap tokens between chunks
        """
        self.db_pool = db_pool
        self.model_name = model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize Hugging Face client via Langchain
        hf_token = os.getenv("HF_TOKEN")
        if not hf_token:
            raise ValueError("HF_TOKEN is not set in environment variables.")
            
        self.embeddings = HuggingFaceEndpointEmbeddings(
            model=model_name,
            huggingfacehub_api_token=hf_token
        )
        
        # Initialize tokenizer for chunking
        # Since tiktoken is extremely fast and robust, we use cl100k_base 
        # as a general-purpose token estimator even for non-OpenAI models.
        self.encoding = tiktoken.get_encoding("cl100k_base")
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks based on token count.
        
        Args:
            text: Input text to chunk
            
        Returns:
            List of text chunks
        """
        tokens = self.encoding.encode(text)
        chunks = []
        
        start = 0
        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)
            
            # Check if we've reached the end before updating start
            if end >= len(tokens):
                break
            
            # Move to next chunk with overlap
            start = end - self.chunk_overlap
        
        return chunks
    
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Input text
            
        Returns:
            Embedding vector
        """
        try:
            # Langchain's embed_query is synchronous, so we run it in an executor
            # to avoid blocking the async event loop (like FastAPI)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self.embeddings.embed_query, 
                text
            )
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to generate embedding: {str(e)}")
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of embedding vectors
        """
        try:
            # Run the synchronous batch embedding in the background thread
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self.embeddings.embed_documents, 
                texts
            )
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to generate batch embeddings: {str(e)}")
    
    async def store_chunk(
        self,
        content: str,
        embedding: List[float],
        source_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a chunk with its embedding in the database.
        
        Args:
            content: Text content
            embedding: Embedding vector
            source_type: Type of source ('textbook', 'question', 'diagram')
            metadata: Additional metadata as JSON
            
        Returns:
            UUID of the inserted record
        """
        # Convert embedding list to a JSON string for PostgreSQL vector format
        embedding_str = json.dumps(embedding)
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO knowledge_base (content, embedding, source_type, metadata)
                VALUES ($1, $2::vector, $3, $4::jsonb)
                RETURNING id
                """,
                content,
                embedding_str,
                source_type,
                json.dumps(metadata or {})
            )
            return str(row['id'])
    
    async def process_and_store(
        self,
        chunks: List[Dict[str, Any]],
        source_type: str
    ) -> Dict[str, int]:
        """
        Process chunks: generate embeddings and store in database.
        
        Args:
            chunks: List of chunk dicts from PDF parser
            source_type: Type of source ('textbook', 'question', 'diagram')
            
        Returns:
            Dict with processing statistics
        """
        stored_count = 0
        embedding_count = 0
        
        # Process in batches of 100 to avoid API limits and memory spikes
        batch_size = 100
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            # Extract text content from the PDF chunks
            texts = [chunk['content'] for chunk in batch]
            
            # Further chunk the text to ensure it fits the embedding model's limits
            all_chunk_texts = []
            chunk_metadata = []
            
            for idx, text in enumerate(texts):
                sub_chunks = self.chunk_text(text)
                for sub_chunk in sub_chunks:
                    all_chunk_texts.append(sub_chunk)
                    # Merge original PDF metadata with our new indexing info
                    meta = batch[idx].get('metadata', {}).copy()
                    meta['original_index'] = i + idx
                    chunk_metadata.append(meta)
            
            print(f"  [embedder] Processing batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size} ({len(all_chunk_texts)} sub-chunks)...")
            # Generate embeddings in batch (much faster than one by one)
            try:
                embeddings = await self.generate_embeddings_batch(all_chunk_texts)
                embedding_count += len(embeddings)
                
                # Store all chunks into PostgreSQL
                for text, embedding, metadata in zip(all_chunk_texts, embeddings, chunk_metadata):
                    await self.store_chunk(text, embedding, source_type, metadata)
                    stored_count += 1
                print(f"  [embedder] Batch {i//batch_size + 1} completed and stored.")
            except Exception as e:
                print(f"  [embedder] Batch {i//batch_size + 1} FAILED: {e}")
        
        return {
            'chunks_stored': stored_count,
            'embeddings_generated': embedding_count
        }


# CLI interface for testing
if __name__ == "__main__":
    import sys
    import json
    import os
    import asyncpg
    from dotenv import load_dotenv
    
    if len(sys.argv) < 2:
        print("Usage: python embedder.py <path_to_parsed_chunks_json>")
        sys.exit(1)
        
    async def main():
        load_dotenv()
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("ERROR: DATABASE_URL not set in .env")
            sys.exit(1)
            
        print(f"1. Loading chunks from {sys.argv[1]}...")
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            chunks = json.load(f)
            
        print("2. Connecting to DB...")
        db_pool = await asyncpg.create_pool(database_url)
        try:
            embedder = EmbeddingService(db_pool)
            
            print("3. Generating embeddings and storing in DB (This may take a moment)...")
            # Using 'textbook' as a default test source_type
            stats = await embedder.process_and_store(chunks, 'textbook')
            
            print("\n" + "=" * 50)
            print("SUCCESS! EMBEDDINGS STORED")
            print("=" * 50)
            print(json.dumps(stats, indent=2))
        finally:
            await db_pool.close()
            
    import asyncio
    asyncio.run(main())
