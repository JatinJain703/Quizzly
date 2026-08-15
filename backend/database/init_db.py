import asyncio
import os
# pyrefly: ignore [missing-import]
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def init_db():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment variables.")

    print(f"Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Create vector extension
        print("Creating vector extension if not exists...")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        print("Creating tables and indexes...")
        await conn.execute("""
            -- Drop the table if it exists so the new schema applies cleanly
            DROP TABLE IF EXISTS knowledge_base CASCADE;
            
            -- Create knowledge base table
            CREATE TABLE knowledge_base (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                content TEXT NOT NULL,
                -- We use 1024 here instead of 1536 because your HuggingFace model
                -- (BAAI/bge-large-en-v1.5) outputs 1024 dimensions.
                embedding vector(1024),
                metadata JSONB,
                source_type VARCHAR(20) CHECK (source_type IN ('textbook', 'question', 'diagram', 'exam_paper')),
                tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            -- Create vector similarity index
            CREATE INDEX knowledge_base_embedding_idx ON knowledge_base 
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);

            -- Create index on source_type for filtering
            CREATE INDEX knowledge_base_source_type_idx ON knowledge_base(source_type);

            -- Create index on created_at for sorting
            CREATE INDEX knowledge_base_created_at_idx ON knowledge_base(created_at DESC);
            
            -- Create GIN index for fast full-text search
            CREATE INDEX knowledge_base_tsv_idx ON knowledge_base USING GIN(tsv);

            -- Drop the topics table if it exists so the new schema applies cleanly
            DROP TABLE IF EXISTS public.topics CASCADE;

            -- Create topics table
            CREATE TABLE IF NOT EXISTS public.topics (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                source_filename VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            );

            -- Prevent duplicate topics per file
            CREATE UNIQUE INDEX IF NOT EXISTS topics_name_source_idx ON public.topics (name, source_filename);

            -- Index for fast lookup by source file
            CREATE INDEX IF NOT EXISTS topics_source_filename_idx ON public.topics (source_filename);
            
            -- Drop the style_profiles table if it exists
            DROP TABLE IF EXISTS style_profiles CASCADE;

            -- Create style_profiles table to cache extracted style analyses
            CREATE TABLE style_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_filename VARCHAR(255) NOT NULL,
                topic_keywords TEXT[],
                profile JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );

            -- Create index on source_filename for quick lookups
            CREATE INDEX style_profiles_source_filename_idx ON style_profiles(source_filename);

            -- Create index on topic_keywords for topic-based style retrieval
            CREATE INDEX style_profiles_topic_keywords_idx ON style_profiles USING GIN(topic_keywords);

            -- Add comments for documentation
            COMMENT ON COLUMN knowledge_base.tsv IS 'Text search vector for keyword-based retrieval (hybrid search)';
            COMMENT ON TABLE style_profiles IS 'Cached style profiles extracted from exam papers for psychometrician agent';
        """)
        print("Database initialization complete.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(init_db())
