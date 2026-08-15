from typing import List, Optional, Literal, Dict
from typing_extensions import TypedDict
from pydantic import BaseModel, Field

class QuestionRequest(BaseModel):
    """Request model for generating quiz questions"""
    topics: List[str] = Field(
        ...,
        min_length=1,
        description="List of topics to generate questions about (at least one required)"
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(default="medium", description="Question difficulty level")
    count: int = Field(default=5, ge=1, le=50, description="Number of questions to generate")

    @property
    def topic(self) -> str:
        """Combine selected topics into a single string for the generation pipeline."""
        return "; ".join(t.strip() for t in self.topics if t.strip())

class QuestionResponse(BaseModel):
    """Response model for a single quiz question (original format)"""
    question: str = Field(..., description="The question text")
    options: Dict[str, str] = Field(..., description="Answer options (A, B, C, D)")
    answer: str = Field(..., description="The correct answer key (A, B, C, or D)")
    explanation: str = Field(..., description="Explanation of the correct answer")
    difficulty: str = Field(..., description="Question difficulty level")

class ResearchBrief(BaseModel):
    facts: List[str] = Field(default_factory=list, description="List of facts extracted from the database")

class AgentState(TypedDict):
    topic: str
    difficulty: str
    context: str
    drafted_question: Optional[QuestionResponse]
    feedback: Optional[str]
    iterations: int

class IngestRequest(BaseModel):
    """Request model for ingesting content"""
    source_type: Literal["textbook", "question", "exam_paper", "diagram"] = Field(
        ...,
        description="Type of content being ingested"
    )

class IngestResponse(BaseModel):
    """Response model for content ingestion"""
    chunks_processed: int
    embeddings_created: int
    images_processed: int = 0
    topics_extracted: int = 0
    message: str

class FileInfo(BaseModel):
    name: str
    source_type: str
    chunks: int

class FilesResponse(BaseModel):
    textbooks: List[FileInfo] = Field(default_factory=list)
    exam_papers: List[FileInfo] = Field(default_factory=list)

class TopicItem(BaseModel):
    """A single extracted topic"""
    id: str
    name: str
    source_filename: str

class TopicsListResponse(BaseModel):
    """Response model for listing all available topics"""
    topics: List[TopicItem] = Field(default_factory=list)
