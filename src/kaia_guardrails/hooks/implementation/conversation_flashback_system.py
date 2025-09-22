"""
RAG-Powered Conversation Flashback System

Detects when current engineering threads are similar to past conversations
and provides contextual flashbacks using semantic similarity search in Qdrant.

Uses internal network model hosts to preserve CF quota.
"""
import json
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from kaia_guardrails.hooks.base import HookBase
from kaia_guardrails.local_config import get_local_config


@dataclass
class FlashbackResult:
    """Result of a flashback search."""
    similarity_score: float
    conversation_snippet: str
    timestamp: str
    focus_context: str
    engineering_pattern: str
    relevance_summary: str


class ConversationFlashbackSystem(HookBase):
    """RAG-powered flashback system for detecting similar engineering threads."""

    def __init__(self):
        super().__init__(name="conversation_flashback", priority=50)
        self.config = get_local_config()
        self.qdrant_url = "http://localhost:6333"  # Local Qdrant
        self.collection_name = "conversation_history"
        self.similarity_threshold = 0.75  # Trigger flashbacks above this threshold

        # Use internal network hosts for LLM operations
        self.judge_llm_url = self.config.get_tool_config('kaia_guardrails').get('judge_llm_base_url', 'http://100.94.250.88:8001')
        self.embedding_url = self.config.get_tool_config('vibelint').get('embedding_base_url', 'http://100.72.90.85:8001')

    def run(self, context: Dict[str, Any]) -> Any:
        """Analyze current focus process for potential flashbacks."""
        hook_type = context.get('hook_type')

        # Only run on focus process changes or significant tool operations
        if hook_type not in ['PreToolUse', 'UserPromptSubmit']:
            return None

        try:
            current_focus = self._extract_current_focus_context(context)
            if not current_focus:
                return None

            # Check for similar past conversations
            flashbacks = self._search_similar_conversations(current_focus)

            if flashbacks:
                return self._format_flashback_response(flashbacks, current_focus)

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to process flashback: {e}")

        return None

    def _extract_current_focus_context(self, context: Dict[str, Any]) -> Optional[str]:
        """Extract the current engineering context for similarity analysis."""
        try:
            # Get current focus process description
            focus_manager = self._get_focus_manager(context)
            if not focus_manager:
                return None

            focus_info = focus_manager.get_current_focus_info()
            current_focus = focus_info.get('description', '')

            # Enhance with current tool operation context
            tool_name = context.get('tool_name', '')
            tool_input = context.get('tool_input', {})

            # Build rich context for similarity matching
            context_parts = [current_focus]

            if tool_name == 'Edit' and 'file_path' in tool_input:
                context_parts.append(f"Editing file: {tool_input['file_path']}")
            elif tool_name == 'Write' and 'file_path' in tool_input:
                context_parts.append(f"Creating file: {tool_input['file_path']}")
            elif tool_name == 'Bash':
                command = tool_input.get('command', '')[:100]  # First 100 chars
                context_parts.append(f"Running command: {command}")

            return " | ".join(filter(None, context_parts))

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to extract focus context: {e}")
            return None

    def _search_similar_conversations(self, current_context: str) -> List[FlashbackResult]:
        """Search Qdrant for similar conversation threads using internal network embeddings."""
        try:
            # Generate embedding for current context using internal network
            embedding = self._generate_embedding(current_context)
            if not embedding:
                return []

            # Search Qdrant for similar conversations
            search_payload = {
                "vector": embedding,
                "limit": 5,
                "score_threshold": self.similarity_threshold,
                "with_payload": True
            }

            response = requests.post(
                f"{self.qdrant_url}/collections/{self.collection_name}/points/search",
                json=search_payload,
                timeout=10
            )

            if response.status_code != 200:
                print(f"[FLASHBACK-ERROR] Qdrant search failed: {response.status_code}")
                return []

            results = response.json().get('result', [])
            flashbacks = []

            for result in results:
                payload = result.get('payload', {})
                flashback = FlashbackResult(
                    similarity_score=result.get('score', 0.0),
                    conversation_snippet=payload.get('content', ''),
                    timestamp=payload.get('timestamp', ''),
                    focus_context=payload.get('focus_context', ''),
                    engineering_pattern=payload.get('engineering_pattern', ''),
                    relevance_summary=self._generate_relevance_summary(current_context, payload.get('content', ''))
                )
                flashbacks.append(flashback)

            return flashbacks

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to search similar conversations: {e}")
            return []

    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding using internal network hosts."""
        try:
            # Use embedding endpoint from internal network
            payload = {
                "input": text,
                "model": "text-embedding-3-small"  # Or whatever embedding model is available
            }

            response = requests.post(
                f"{self.embedding_url}/v1/embeddings",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('data', [{}])[0].get('embedding', [])
            else:
                print(f"[FLASHBACK-ERROR] Embedding generation failed: {response.status_code}")
                return None

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to generate embedding: {e}")
            return None

    def _generate_relevance_summary(self, current_context: str, past_content: str) -> str:
        """Generate a relevance summary using internal network LLM."""
        try:
            prompt = f"""
Analyze the similarity between current and past engineering context:

CURRENT: {current_context}
PAST: {past_content[:500]}...

Provide a 1-sentence summary of why this past conversation is relevant to the current engineering thread.
Focus on: similar patterns, shared challenges, or applicable solutions.
"""

            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 100,
                "temperature": 0.3
            }

            response = requests.post(
                f"{self.judge_llm_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('choices', [{}])[0].get('message', {}).get('content', 'Related pattern detected')
            else:
                return "Similar engineering pattern detected"

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to generate relevance summary: {e}")
            return "Related engineering thread found"

    def _format_flashback_response(self, flashbacks: List[FlashbackResult], current_context: str) -> str:
        """Format flashback results for presentation."""
        if not flashbacks:
            return None

        response = f"🔍 **FLASHBACK DETECTED** - Similar engineering thread found!\n\n"
        response += f"**Current Context:** {current_context}\n\n"

        for i, flashback in enumerate(flashbacks[:2], 1):  # Show top 2 results
            response += f"**💡 Flashback #{i}** (Similarity: {flashback.similarity_score:.2f})\n"
            response += f"**When:** {flashback.timestamp}\n"
            response += f"**Context:** {flashback.focus_context}\n"
            response += f"**Relevance:** {flashback.relevance_summary}\n"
            response += f"**Snippet:** {flashback.conversation_snippet[:200]}...\n\n"

        response += "💭 *Consider: What did we learn from this previous thread that applies here?*"

        return response

    def _get_focus_manager(self, context: Dict[str, Any]):
        """Get focus process manager instance."""
        try:
            from .focus_process_manager import FocusProcessManager
            project_root = Path(context.get('cwd', os.getcwd()))
            return FocusProcessManager(project_root=project_root)
        except Exception:
            return None

    def ingest_conversation_to_qdrant(self, conversation_content: str, metadata: Dict[str, Any]) -> bool:
        """
        Ingest conversation content to Qdrant using sliding window chunking.
        Based on the RAG research for optimal chunking strategies.
        """
        try:
            # Apply sliding window chunking (proven best for conversation continuity)
            chunks = self._sliding_window_chunk(conversation_content, window_size=300, step_size=150)

            for i, chunk in enumerate(chunks):
                # Generate embedding using internal network
                embedding = self._generate_embedding(chunk)
                if not embedding:
                    continue

                # Create point for Qdrant
                point_id = hashlib.md5(f"{metadata.get('timestamp', '')}{i}{chunk}".encode()).hexdigest()

                point = {
                    "id": point_id,
                    "vector": embedding,
                    "payload": {
                        "content": chunk,
                        "timestamp": metadata.get('timestamp', ''),
                        "focus_context": metadata.get('focus_context', ''),
                        "engineering_pattern": metadata.get('engineering_pattern', ''),
                        "chunk_index": i,
                        "source": "conversation_history"
                    }
                }

                # Insert into Qdrant
                response = requests.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}/points",
                    json={"points": [point]},
                    timeout=10
                )

                if response.status_code not in [200, 201]:
                    print(f"[FLASHBACK-ERROR] Failed to insert chunk {i}: {response.status_code}")

            return True

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to ingest conversation: {e}")
            return False

    def _sliding_window_chunk(self, text: str, window_size: int = 300, step_size: int = 150) -> List[str]:
        """
        Sliding window chunking optimized for conversation continuity.
        Based on proven strategies from RAG research.
        """
        words = text.split()
        chunks = []

        for i in range(0, len(words), step_size):
            chunk = ' '.join(words[i:i+window_size])
            if len(chunk.split()) >= 50:  # Minimum meaningful chunk size
                chunks.append(chunk)
            if i + window_size >= len(words):
                break

        return chunks

    def ensure_qdrant_collection(self) -> bool:
        """Ensure Qdrant collection exists for conversation history."""
        try:
            # Check if collection exists
            response = requests.get(
                f"{self.qdrant_url}/collections/{self.collection_name}",
                timeout=5
            )

            if response.status_code == 404:
                # Create collection
                create_payload = {
                    "vectors": {
                        "size": 1536,  # Standard embedding dimension
                        "distance": "Cosine"
                    }
                }

                response = requests.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}",
                    json=create_payload,
                    timeout=10
                )

                if response.status_code in [200, 201]:
                    print(f"[FLASHBACK-INIT] Created Qdrant collection: {self.collection_name}")
                    return True
                else:
                    print(f"[FLASHBACK-ERROR] Failed to create collection: {response.status_code}")
                    return False

            return True

        except Exception as e:
            print(f"[FLASHBACK-ERROR] Failed to ensure Qdrant collection: {e}")
            return False