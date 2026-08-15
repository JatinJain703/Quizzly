import os
import tempfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import asyncpg
from contextlib import asynccontextmanager

# Load env variables
load_dotenv()

# Import the services
from services.pdf_parser import PDFParser
from services.embedder import EmbeddingService
from services.vision import VisionService
from services.topic_extractor import TopicExtractor
from services.style_analyzer import StyleAnalyzer

db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL must be set in .env")
    
    print("Connecting to database...")
    db_pool = await asyncpg.create_pool(database_url)
    yield
    print("Closing database connection...")
    await db_pool.close()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Quizzly API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from typing import List
from models.schemas import IngestResponse, QuestionRequest, QuestionResponse, FilesResponse, TopicsListResponse, TopicItem
from services.rag_engine import MultiAgentRAGEngine

@app.post("/ingest", response_model=IngestResponse)
async def ingest_pdf(
    file: UploadFile = File(...),
    source_type: str = Form("textbook")
):
    """
    Ingest a PDF file: parse, extract images, generate embeddings, and store.
    
    Args:
        file: PDF file to ingest
        source_type: Type of content ('textbook', 'question', 'exam_paper', or 'diagram')
    
    Note: For 'exam_paper' source type, a style profile will be automatically extracted
    and cached for use in question generation.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    # Validate source_type
    valid_types = ['textbook', 'question', 'exam_paper', 'diagram']
    if source_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source_type. Must be one of: {valid_types}"
        )
    
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = tmp_file.name
    
    try:
        # Step 1: Parse PDF
        parser = PDFParser()
        parsed_data = await parser.parse_pdf(tmp_path)
        
        # Step 2: Process images with vision service (optional)
        images_processed = 0
        hf_token = os.getenv("HF_TOKEN")
        # Ensure we have images and HF token before trying to use VisionService
        if parsed_data['images'] and hf_token:
            try:
                # Assuming space_name is set in .env
                vision_service = VisionService()
                descriptions = await vision_service.batch_describe(
                    parsed_data['images'],
                    context=f"From {file.filename}"
                )
                
                for idx, desc in enumerate(descriptions):
                    parsed_data['chunks'].append({
                        'content': desc,
                        'metadata': {
                            'source': 'vision',
                            'image_index': idx,
                            'filename': file.filename
                        }
                    })
                images_processed = len([d for d in descriptions if d])
            except Exception as e:
                print(f"Vision processing skipped: {e}")
                pass
        
        # Step 3: Generate embeddings and store
        for chunk in parsed_data['chunks']:
            if 'metadata' not in chunk:
                chunk['metadata'] = {}
            chunk['metadata']['filename'] = file.filename
            
        embedder = EmbeddingService(db_pool)
        stats = await embedder.process_and_store(
            parsed_data['chunks'],
            source_type
        )
        
        # Step 4: If exam_paper, extract and cache style profile
        if source_type == 'exam_paper' and stats['chunks_stored'] > 0:
            try:
                style_analyzer = StyleAnalyzer(db_pool)
                await style_analyzer.analyze_exam_paper(file.filename)
            except Exception as e:
                print(f"Style analysis skipped: {e}")
        
        # Step 5: If textbook, extract and store topics
        topics_extracted = 0
        if source_type == 'textbook' and stats['chunks_stored'] > 0:
            try:
                topic_extractor = TopicExtractor(db_pool)
                extracted_topics = await topic_extractor.extract_and_store(file.filename)
                topics_extracted = len(extracted_topics)
                print(f"✓ Extracted {topics_extracted} topics from {file.filename}")
            except Exception as e:
                print(f"Topic extraction skipped: {e}")
        
        return IngestResponse(
            chunks_processed=stats['chunks_stored'],
            embeddings_created=stats['embeddings_generated'],
            images_processed=images_processed,
            topics_extracted=topics_extracted,
            message=f"Successfully ingested {file.filename} as {source_type}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

@app.get("/files", response_model=FilesResponse)
async def list_files():
    """
    Get list of uploaded files grouped by source type.
    Returns metadata about uploaded PDFs stored in the database.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT 
                    metadata->>'filename' as filename,
                    source_type,
                    COUNT(*) as chunk_count
                FROM knowledge_base
                WHERE metadata->>'filename' IS NOT NULL
                GROUP BY metadata->>'filename', source_type
                ORDER BY source_type, filename
                """
            )
            
            textbooks = []
            exam_papers = []
            
            for row in rows:
                file_info = {
                    "name": row['filename'],
                    "source_type": row['source_type'],
                    "chunks": row['chunk_count']
                }
                
                if row['source_type'] == 'textbook':
                    textbooks.append(file_info)
                elif row['source_type'] == 'exam_paper':
                    exam_papers.append(file_info)
            
            return FilesResponse(
                textbooks=textbooks,
                exam_papers=exam_papers
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve files: {str(e)}")


@app.get("/topics", response_model=TopicsListResponse)
async def list_topics():
    """
    Get all extracted topics from the database.
    Returns topics grouped across all ingested textbooks.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id::text, name, source_filename
                FROM topics
                ORDER BY source_filename, name
                """
            )
            topics = [
                TopicItem(
                    id=row["id"],
                    name=row["name"],
                    source_filename=row["source_filename"]
                )
                for row in rows
            ]
            return TopicsListResponse(topics=topics)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve topics: {str(e)}")


@app.post("/generate", response_model=List[QuestionResponse])
async def generate_questions(request: QuestionRequest):
    """
    Generate exam questions using the Multi-Agent RAG pipeline.
    
    This endpoint uses the three-agent architecture:
    1. Researcher: Extracts core facts from textbook
    2. Psychometrician: Drafts questions with style synthesis
    3. Critic: Quality gate with reflection and iteration
    
    Args:
        request: Question generation parameters
        
    Returns:
        List of generated questions
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        embedder = EmbeddingService(db_pool)
        rag_engine = MultiAgentRAGEngine(
            db_pool,
            embedder,
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
        )
        
        questions = await rag_engine.generate_questions(
            topics=request.topics,
            count=request.count,
            difficulty=request.difficulty
        )
        
        if not questions:
            raise HTTPException(
                status_code=404,
                detail=f"Could not generate questions for topic: {request.topic}"
            )
        
        # Return in original format (strip multi-agent metadata)
        return [QuestionResponse(**q) for q in questions]
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

