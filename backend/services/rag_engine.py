"""
Multi-Agent RAG Engine for High-Quality Question Generation.

This module implements the complete multi-agent pipeline:
1. Researcher: Extracts core facts from textbook content
2. Psychometrician: Drafts questions matching exam style
3. Critic: Quality gate with reflection and iteration

The pipeline ensures questions are:
- Factual accurate (checked by Researcher and Critic)
- Style-consistent (guided by StyleAnalyzer and Psychometrician)
- High-quality (critiqued and iterated by Critic)
"""
import os
from typing import List, Dict, Any, Optional
import asyncpg

from .hybrid_retriever import HybridRetriever
from .style_analyzer import StyleAnalyzer
from .agents import ResearcherAgent, PsychometricianAgent, CriticAgent
from .agents.researcher import ResearchBrief
from .agents.psychometrician import DraftedQuestion
from .agents.critic import CritiqueReview


class MultiAgentRAGEngine:
    """
    Complete multi-agent RAG pipeline for high-quality question generation.
    
    Architecture:
    - HybridRetriever: Combines vector + keyword search for context retrieval
    - StyleAnalyzer: Extracts style profiles from past papers
    - Researcher Agent: Extracts core facts from textbook content
    - Psychometrician Agent: Drafts questions with style synthesis
    - Critic Agent: Quality gate with reflection and iteration
    """
    
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        embedding_service,
        similarity_threshold: float = 0.85,
        max_critic_iterations: int = 2,
        min_critic_score: int = 7
    ):
        """
        Initialize the multi-agent RAG engine.
        
        Args:
            db_pool: Database connection pool
            embedding_service: EmbeddingService instance
            similarity_threshold: Cosine similarity threshold for deduplication
            max_critic_iterations: Maximum revision loops with Critic
            min_critic_score: Minimum score required for Critic approval
        """
        self.db_pool = db_pool
        self.embedding_service = embedding_service
        self.similarity_threshold = similarity_threshold
        self.max_critic_iterations = max_critic_iterations
        self.min_critic_score = min_critic_score
        
        # Initialize components
        self.retriever = HybridRetriever(db_pool, embedding_service)
        self.style_analyzer = StyleAnalyzer(db_pool)
        
        # Initialize agents
        self.researcher = ResearcherAgent(self.retriever)
        self.psychometrician = PsychometricianAgent()
        self.critic = CriticAgent()
    
    async def is_duplicate(
        self,
        question_text: str,
        source_type: str = 'question'
    ) -> bool:
        """
        Check if a similar question already exists.
        
        Args:
            question_text: Question to check
            source_type: Type filter for comparison
            
        Returns:
            True if duplicate found, False otherwise
        """
        # Generate embedding for new question
        question_embedding = await self.embedding_service.generate_embedding(question_text)
        
        import json
        embedding_str = json.dumps(question_embedding)
        
        async with self.db_pool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT 1 - (embedding <=> $1::vector) as similarity
                FROM knowledge_base
                WHERE source_type = $2
                ORDER BY embedding <=> $1::vector
                LIMIT 1
                """,
                embedding_str,
                source_type
            )
            
            if result and result['similarity'] >= self.similarity_threshold:
                return True
            
            return False
    
    async def generate_questions(
        self,
        topic: str = "",
        topics: Optional[List[str]] = None,
        count: int = 5,
        difficulty: str = "medium",
        max_total_attempts: int = 15,
        progress_callback: Optional[Any] = None,
        question_callback: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple high-quality questions across one or more topics.

        When multiple topics are provided, questions are distributed across them
        in round-robin order so each topic gets roughly equal representation.

        Args:
            topic: Single topic string (legacy, for backward compat)
            topics: List of topic strings (preferred over `topic`)
            count: Number of questions to generate
            difficulty: Question difficulty (easy, medium, hard)
            max_total_attempts: Max total attempts (including retries)
            progress_callback: Async callback function(stage, message) for progress updates
            question_callback: Async callback function(question_dict) for streaming results

        Returns:
            List of generated questions with full metadata
        """
        # Resolve the final topics list
        if topics and len(topics) > 0:
            topic_list = [t.strip() for t in topics if t.strip()]
        elif topic:
            # Legacy: split on "; " in case the joined string was passed
            topic_list = [t.strip() for t in topic.split(";") if t.strip()]
        else:
            topic_list = ["General Knowledge"]

        if not topic_list:
            topic_list = ["General Knowledge"]

        display_topic = "; ".join(topic_list)
        print(f"\n{'='*60}")
        print(f"GENERATING {count} {difficulty.upper()} QUESTIONS ACROSS {len(topic_list)} TOPIC(S): {display_topic}")
        print(f"{'='*60}")

        # Phase 1: Shared Style Ingestion (topic-agnostic)
        print("\n📚 Phase 1: Style Ingestion")
        print("-" * 40)
        print(f"  • Style Analyzer: Extracting style profile...")
        # Use first topic for style lookup (style is typically topic-agnostic in practice)
        style_profile = await self.style_analyzer.get_style_profile(topic_list[0])
        if style_profile:
            print(f"    ✓ Style profile extracted")
        else:
            print(f"    ⚠ No style profile found (no exam papers ingested)")

        style_examples = await self.retriever.fetch_style_examples(topic_list[0], limit=3)
        print(f"    ✓ Found {len(style_examples)} style examples")

        # Cache research briefs per topic to avoid re-fetching on retries
        research_cache: Dict[str, Any] = {}
        
        # Phase 2: Multi-Agent Generation Loop
        print(f"\n🤖 Phase 2: Multi-Agent Generation Loop")
        print("-" * 40)

        questions = []
        attempts = 0

        # Calculate how many multiple selection questions we need (20%)
        num_multi_questions = int(count * 0.2)
        generated_multi_count = 0

        while len(questions) < count and attempts < max_total_attempts:
            attempts += 1
            q_num = len(questions) + 1

            # Round-robin topic assignment so each topic gets equal coverage
            current_topic = topic_list[(q_num - 1) % len(topic_list)]
            print(f"\n  Question {q_num}/{count} — topic: '{current_topic}' (attempt {attempts})...")

            # Fetch (or reuse cached) research brief for this topic
            if current_topic not in research_cache:
                print(f"    • Researcher: Extracting facts for '{current_topic}'...")
                try:
                    brief = await self.researcher.research(current_topic, difficulty)
                    research_cache[current_topic] = brief
                    print(f"      ✓ Found {len(brief.core_facts)} facts, {len(brief.key_definitions)} definitions")
                except Exception as e:
                    print(f"      ✗ Research failed for '{current_topic}': {e}")
                    continue

            research_brief = research_cache[current_topic]
            
            # Determine forced type for this question
            # If we still need multi-select questions, and the current slot suggests it's time, or if we are running out of slots
            remaining_slots = count - len(questions)
            remaining_multi_needed = num_multi_questions - generated_multi_count
            
            forced_type = "single_select"
            # Force multi-select if we still need them and:
            # 1. We're at a 5th interval (20% -> 1 in 5)
            # 2. Or we're running out of slots and must fill the quota
            if remaining_multi_needed > 0:
                if (q_num % 5 == 0) or (remaining_slots <= remaining_multi_needed):
                    forced_type = "multiple_selection"
            
            try:
                # Agent 2: Psychometrician drafts the question
                print(f"    • Psychometrician: Drafting question ({forced_type})...")
                draft = await self.psychometrician.draft_question(
                    research_brief=research_brief,
                    style_profile=style_profile,
                    style_examples=style_examples,
                    difficulty=difficulty,
                    forced_question_type=forced_type
                )
                print(f"      ✓ Draft created")
                print(f"        - Cognitive level: {draft.cognitive_level}")
                print(f"        - Distractor reasoning: {len(draft.distractor_reasoning)} distractors")
                
                # Agent 3: Critic reviews and iterates
                print(f"    • Critic: Reviewing question...")
                review = await self.critic.review(
                    question=draft,
                    research_brief=research_brief,
                    min_score=self.min_critic_score
                )
                
                # Revision loop
                current_draft = draft
                for iteration in range(self.max_critic_iterations):
                    if review.approved:
                        break
                    
                    print(f"      ⚠ Not approved (score: {review.score}/10)")
                    print(f"      • Psychometrician: Revising based on feedback...")
                    
                    current_draft = await self.psychometrician.revise_question(
                        current_draft=current_draft,
                        feedback=review.suggestions,
                        research_brief=research_brief
                    )
                    
                    # Re-review
                    review = await self.critic.review(
                        question=current_draft,
                        research_brief=research_brief,
                        min_score=self.min_critic_score
                    )
                
                if review.approved:
                    print(f"      ✓ Approved (score: {review.score}/10)")
                else:
                    print(f"      ⚠ Not approved after {self.max_critic_iterations} revisions")
                    continue
                
                # Check for duplicates
                if await self.is_duplicate(current_draft.question):
                    print(f"    ⚠ Skipped (duplicate)")
                    continue
                
                # Convert to response format
                question_dict = self._draft_to_response(current_draft, review)
                questions.append(question_dict)
                
                if question_dict.get('question_type') == 'multiple_selection':
                    generated_multi_count += 1
                
                print(f"    ✓ Question added")
                
            except Exception as e:
                print(f"    ✗ Failed: {str(e)}")
                continue
        
        # Summary
        print(f"\n{'='*60}")
        print(f"GENERATION COMPLETE")
        print(f"{'='*60}")
        print(f"  Requested: {count}")
        print(f"  Generated: {len(questions)}")
        print(f"  Total attempts: {attempts}")
        print(f"  Success rate: {len(questions)/attempts*100:.1f}%")
        
        if not questions:
            print(f"\n⚠ WARNING: No questions generated!")
            print(f"   Tips:")
            print(f"   - Ensure textbook content is ingested for topic: {topic}")
            print(f"   - Ingest exam papers for better style matching")
            print(f"   - Try a broader topic or lower difficulty")
        
        return questions
    
    def _draft_to_response(
        self,
        draft: DraftedQuestion,
        review: CritiqueReview
    ) -> Dict[str, Any]:
        """
        Convert a DraftedQuestion to the response format.
        
        Args:
            draft: The drafted question
            review: The critic review
            
        Returns:
            Question dict in response format
        """
        return {
            "question": draft.question,
            "question_type": draft.question_type,
            "options": draft.options,
            "answer": draft.answer,
            "explanation": draft.explanation,
            "difficulty": draft.difficulty,
            "distractor_reasoning": draft.distractor_reasoning,
            "topic": draft.topic,
            "cognitive_level": draft.cognitive_level,
            "quality_score": review.score,
            "quality_checks": review.checks,
            "source_references": []  # Could be populated from research brief
        }



# CLI test
if __name__ == "__main__":
    print("=" * 60)
    print("MULTI-AGENT RAG ENGINE - ARCHITECTURE OVERVIEW")
    print("=" * 60)
    print("\n🤖 THREE-AGENT ARCHITECTURE:")
    print("  1. RESEARCHER → Extracts core facts from textbook")
    print("  2. PSYCHOMETRICIAN → Drafts questions with style synthesis")
    print("  3. CRITIC → Quality gate with reflection & iteration")
    print("\n🔍 HYBRID RETRIEVAL:")
    print("  • Vector Search (conceptual similarity)")
    print("  • Keyword Search (exact term matching)")
    print("  • RRF merging for optimal results")
    print("\n📊 STYLE ANALYSIS:")
    print("  • Extracts question stems, sentence length")
    print("  • Identifies distractor patterns")
    print("  • Caches profiles for reuse")
    print("\n✅ QUALITY GUARANTEES:")
    print("  • Factual accuracy (checked by Researcher + Critic)")
    print("  • Style consistency (guided by StyleAnalyzer)")
    print("  • Iterative refinement (Critic → Psychometrician loop)")
    print("\n" + "=" * 60)
    print("To test: Use POST /generate endpoint (after ingesting PDFs)")
    print("=" * 60)
