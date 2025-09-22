"""
Advanced Memory Curator with Evidence-Based Retrieval (EBR)

Addresses the critical flaw in current memory frameworks by implementing:
1. EBR with rich chunk metadata analysis
2. Memory deduplication using semantic similarity + metadata
3. Outdated information removal via vibelint judge
4. Quality assessment using orchestrator LLM

Uses internal network hosts to preserve CF quota.
"""
import json
import hashlib
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict

from local_config import get_local_config


@dataclass
class MemoryChunk:
    """Rich memory chunk with comprehensive metadata for EBR."""
    id: str
    content: str
    embedding: List[float]
    timestamp: datetime
    source_context: str
    engineering_pattern: str
    confidence_score: float
    relevance_tags: List[str]
    superseded_by: Optional[str] = None
    quality_score: Optional[float] = None
    evidence_strength: Optional[float] = None

    # EBR metadata
    outcome_success: Optional[bool] = None
    solution_effectiveness: Optional[str] = None
    dependencies: List[str] = None
    contradicts: List[str] = None
    validates: List[str] = None


@dataclass
class DeduplicationResult:
    """Result of memory deduplication analysis."""
    duplicates_found: int
    outdated_removed: int
    quality_improved: int
    evidence_consolidated: int


class AdvancedMemoryCurator:
    """
    Sophisticated memory management with EBR and post-processing.
    Addresses the memory framework flaws identified in Windsurf and similar tools.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config = get_local_config()
        self.qdrant_url = "http://localhost:6333"
        self.collection_name = "curated_memory"

        # Internal network endpoints
        self.judge_llm_url = self.config.get_tool_config('kaia_guardrails').get('judge_llm_base_url', 'http://100.94.250.88:8001')
        self.orchestrator_llm_url = self.config.get_tool_config('vibelint').get('llm_base_url', 'http://100.72.90.85:8001')
        self.embedding_url = self.config.get_tool_config('vibelint').get('embedding_base_url', 'http://100.72.90.85:8001')

        # EBR configuration
        self.similarity_threshold = 0.85  # High threshold for deduplication
        self.evidence_weight = 0.7  # How much to weight evidence vs. recency
        self.quality_threshold = 0.6  # Minimum quality to retain memory

    def curate_memory_collection(self) -> DeduplicationResult:
        """
        Comprehensive memory curation with EBR and post-processing.
        This is what current frameworks are missing!
        """
        print("[MEMORY-CURATOR] Starting advanced memory curation with EBR...")

        # Step 1: Load all memory chunks with metadata
        memory_chunks = self._load_memory_chunks()
        print(f"[MEMORY-CURATOR] Loaded {len(memory_chunks)} memory chunks")

        # Step 2: Perform semantic clustering for deduplication detection
        duplicate_clusters = self._find_semantic_duplicates(memory_chunks)
        print(f"[MEMORY-CURATOR] Found {len(duplicate_clusters)} potential duplicate clusters")

        # Step 3: Evidence-based deduplication using metadata
        deduplicated = self._evidence_based_deduplication(duplicate_clusters)
        print(f"[MEMORY-CURATOR] Deduplicated {deduplicated} chunks using EBR")

        # Step 4: Outdated information removal via judge
        outdated_removed = self._remove_outdated_information(memory_chunks)
        print(f"[MEMORY-CURATOR] Removed {outdated_removed} outdated chunks")

        # Step 5: Quality assessment and improvement
        quality_improved = self._assess_and_improve_quality(memory_chunks)
        print(f"[MEMORY-CURATOR] Improved quality of {quality_improved} chunks")

        # Step 6: Evidence consolidation
        evidence_consolidated = self._consolidate_evidence(memory_chunks)
        print(f"[MEMORY-CURATOR] Consolidated evidence for {evidence_consolidated} chunks")

        return DeduplicationResult(
            duplicates_found=len(duplicate_clusters),
            outdated_removed=outdated_removed,
            quality_improved=quality_improved,
            evidence_consolidated=evidence_consolidated
        )

    def _load_memory_chunks(self) -> List[MemoryChunk]:
        """Load memory chunks from Qdrant with rich metadata."""
        try:
            # Get all points from collection
            response = requests.post(
                f"{self.qdrant_url}/collections/{self.collection_name}/points/scroll",
                json={"limit": 1000, "with_payload": True, "with_vector": True},
                timeout=30
            )

            if response.status_code != 200:
                print(f"[MEMORY-CURATOR-ERROR] Failed to load chunks: {response.status_code}")
                return []

            points = response.json().get('result', {}).get('points', [])
            memory_chunks = []

            for point in points:
                payload = point.get('payload', {})
                chunk = MemoryChunk(
                    id=point.get('id', ''),
                    content=payload.get('content', ''),
                    embedding=point.get('vector', []),
                    timestamp=datetime.fromisoformat(payload.get('timestamp', datetime.now().isoformat())),
                    source_context=payload.get('source_context', ''),
                    engineering_pattern=payload.get('engineering_pattern', ''),
                    confidence_score=payload.get('confidence_score', 0.5),
                    relevance_tags=payload.get('relevance_tags', []),
                    superseded_by=payload.get('superseded_by'),
                    quality_score=payload.get('quality_score'),
                    evidence_strength=payload.get('evidence_strength'),
                    outcome_success=payload.get('outcome_success'),
                    solution_effectiveness=payload.get('solution_effectiveness'),
                    dependencies=payload.get('dependencies', []),
                    contradicts=payload.get('contradicts', []),
                    validates=payload.get('validates', [])
                )
                memory_chunks.append(chunk)

            return memory_chunks

        except Exception as e:
            print(f"[MEMORY-CURATOR-ERROR] Failed to load memory chunks: {e}")
            return []

    def _find_semantic_duplicates(self, chunks: List[MemoryChunk]) -> List[List[MemoryChunk]]:
        """
        Find semantic duplicates using embedding similarity + metadata correlation.
        This is where most frameworks fail - they only look at embeddings!
        """
        duplicate_clusters = []
        processed_ids = set()

        for i, chunk_a in enumerate(chunks):
            if chunk_a.id in processed_ids:
                continue

            cluster = [chunk_a]
            processed_ids.add(chunk_a.id)

            for j, chunk_b in enumerate(chunks[i+1:], i+1):
                if chunk_b.id in processed_ids:
                    continue

                # Calculate semantic similarity
                semantic_sim = self._cosine_similarity(chunk_a.embedding, chunk_b.embedding)

                # Calculate metadata correlation
                metadata_sim = self._metadata_similarity(chunk_a, chunk_b)

                # Combined similarity with metadata weighting
                combined_sim = (semantic_sim * 0.7) + (metadata_sim * 0.3)

                if combined_sim > self.similarity_threshold:
                    cluster.append(chunk_b)
                    processed_ids.add(chunk_b.id)

            if len(cluster) > 1:
                duplicate_clusters.append(cluster)

        return duplicate_clusters

    def _metadata_similarity(self, chunk_a: MemoryChunk, chunk_b: MemoryChunk) -> float:
        """Calculate metadata similarity for better duplicate detection."""
        score = 0.0
        total_weight = 0.0

        # Engineering pattern similarity
        if chunk_a.engineering_pattern == chunk_b.engineering_pattern:
            score += 0.3
        total_weight += 0.3

        # Source context similarity
        if chunk_a.source_context == chunk_b.source_context:
            score += 0.2
        total_weight += 0.2

        # Tag overlap
        tag_overlap = len(set(chunk_a.relevance_tags) & set(chunk_b.relevance_tags))
        max_tags = max(len(chunk_a.relevance_tags), len(chunk_b.relevance_tags))
        if max_tags > 0:
            score += (tag_overlap / max_tags) * 0.3
        total_weight += 0.3

        # Temporal proximity
        time_diff = abs((chunk_a.timestamp - chunk_b.timestamp).total_seconds())
        time_similarity = max(0, 1 - (time_diff / (7 * 24 * 3600)))  # 7 days window
        score += time_similarity * 0.2
        total_weight += 0.2

        return score / total_weight if total_weight > 0 else 0.0

    def _evidence_based_deduplication(self, duplicate_clusters: List[List[MemoryChunk]]) -> int:
        """
        Evidence-based deduplication - the missing piece in current frameworks!
        Uses outcome evidence and metadata to decide which memories to keep.
        """
        deduplicated_count = 0

        for cluster in duplicate_clusters:
            if len(cluster) <= 1:
                continue

            # Find the best chunk using evidence-based ranking
            best_chunk = self._rank_chunks_by_evidence(cluster)[0]

            # Mark others as superseded
            for chunk in cluster:
                if chunk.id != best_chunk.id:
                    chunk.superseded_by = best_chunk.id
                    self._update_chunk_in_qdrant(chunk)
                    deduplicated_count += 1

        return deduplicated_count

    def _rank_chunks_by_evidence(self, chunks: List[MemoryChunk]) -> List[MemoryChunk]:
        """Rank chunks by evidence strength and outcome quality."""
        def evidence_score(chunk: MemoryChunk) -> float:
            score = 0.0

            # Outcome success weight
            if chunk.outcome_success is not None:
                score += 0.4 if chunk.outcome_success else -0.2

            # Quality score
            if chunk.quality_score is not None:
                score += chunk.quality_score * 0.3

            # Evidence strength
            if chunk.evidence_strength is not None:
                score += chunk.evidence_strength * 0.2

            # Confidence
            score += chunk.confidence_score * 0.1

            return score

        return sorted(chunks, key=evidence_score, reverse=True)

    def _remove_outdated_information(self, chunks: List[MemoryChunk]) -> int:
        """
        Use vibelint judge to identify and remove outdated information.
        This requires LLM judgment - can't be done with simple rules.
        """
        removed_count = 0
        batch_size = 10  # Process in batches to avoid overwhelming the LLM

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            outdated_chunks = self._judge_outdated_batch(batch)

            for chunk_id in outdated_chunks:
                # Mark as outdated and remove from active memory
                chunk = next((c for c in batch if c.id == chunk_id), None)
                if chunk:
                    self._remove_chunk_from_qdrant(chunk.id)
                    removed_count += 1

        return removed_count

    def _judge_outdated_batch(self, chunks: List[MemoryChunk]) -> List[str]:
        """Use vibelint judge to determine which chunks are outdated."""
        try:
            # Prepare context for judge
            chunk_summaries = []
            for chunk in chunks:
                summary = {
                    'id': chunk.id,
                    'content_preview': chunk.content[:200],
                    'timestamp': chunk.timestamp.isoformat(),
                    'pattern': chunk.engineering_pattern,
                    'outcome': chunk.outcome_success
                }
                chunk_summaries.append(summary)

            prompt = f"""
Analyze these memory chunks for outdated information:

{json.dumps(chunk_summaries, indent=2)}

Identify chunks that are:
1. Superseded by newer information
2. No longer relevant to current engineering practices
3. Failed approaches that shouldn't be recommended

Return ONLY a JSON array of chunk IDs to remove: ["id1", "id2", ...]
"""

            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 300,
                "temperature": 0.1
            }

            response = requests.post(
                f"{self.judge_llm_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=20
            )

            if response.status_code == 200:
                data = response.json()
                judge_response = data.get('choices', [{}])[0].get('message', {}).get('content', '[]')
                return json.loads(judge_response)

        except Exception as e:
            print(f"[MEMORY-CURATOR-ERROR] Failed to judge outdated chunks: {e}")

        return []

    def _assess_and_improve_quality(self, chunks: List[MemoryChunk]) -> int:
        """Use orchestrator LLM to assess and improve memory quality."""
        improved_count = 0

        for chunk in chunks:
            if chunk.quality_score is None or chunk.quality_score < self.quality_threshold:
                quality_assessment = self._assess_chunk_quality(chunk)

                if quality_assessment['improved']:
                    chunk.quality_score = quality_assessment['score']
                    chunk.content = quality_assessment.get('improved_content', chunk.content)
                    chunk.relevance_tags = quality_assessment.get('improved_tags', chunk.relevance_tags)

                    self._update_chunk_in_qdrant(chunk)
                    improved_count += 1

        return improved_count

    def _assess_chunk_quality(self, chunk: MemoryChunk) -> Dict[str, Any]:
        """Assess and potentially improve chunk quality using orchestrator LLM."""
        try:
            prompt = f"""
Assess and improve this memory chunk quality:

Content: {chunk.content}
Pattern: {chunk.engineering_pattern}
Context: {chunk.source_context}
Current Tags: {chunk.relevance_tags}

Provide quality assessment and improvements:
1. Quality score (0.0-1.0)
2. Improved content (if needed)
3. Better relevance tags
4. Evidence strength assessment

Return JSON:
{{
    "score": 0.0-1.0,
    "improved": true/false,
    "improved_content": "...",
    "improved_tags": [...],
    "evidence_strength": 0.0-1.0,
    "assessment": "..."
}}
"""

            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 500,
                "temperature": 0.2
            }

            response = requests.post(
                f"{self.orchestrator_llm_url}/v1/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=25
            )

            if response.status_code == 200:
                data = response.json()
                assessment = data.get('choices', [{}])[0].get('message', {}).get('content', '{}')
                return json.loads(assessment)

        except Exception as e:
            print(f"[MEMORY-CURATOR-ERROR] Failed to assess chunk quality: {e}")

        return {'improved': False, 'score': chunk.quality_score or 0.5}

    def _consolidate_evidence(self, chunks: List[MemoryChunk]) -> int:
        """Consolidate evidence across related chunks."""
        consolidated_count = 0
        pattern_groups = defaultdict(list)

        # Group by engineering pattern
        for chunk in chunks:
            pattern_groups[chunk.engineering_pattern].append(chunk)

        # Consolidate evidence within each pattern group
        for pattern, pattern_chunks in pattern_groups.items():
            if len(pattern_chunks) > 1:
                consolidated_count += self._consolidate_pattern_evidence(pattern_chunks)

        return consolidated_count

    def _consolidate_pattern_evidence(self, chunks: List[MemoryChunk]) -> int:
        """Consolidate evidence for chunks with the same engineering pattern."""
        # Find validation and contradiction relationships
        for chunk_a in chunks:
            for chunk_b in chunks:
                if chunk_a.id != chunk_b.id:
                    relationship = self._analyze_chunk_relationship(chunk_a, chunk_b)

                    if relationship == 'validates':
                        if chunk_b.id not in chunk_a.validates:
                            chunk_a.validates.append(chunk_b.id)
                            self._update_chunk_in_qdrant(chunk_a)
                    elif relationship == 'contradicts':
                        if chunk_b.id not in chunk_a.contradicts:
                            chunk_a.contradicts.append(chunk_b.id)
                            self._update_chunk_in_qdrant(chunk_a)

        return len(chunks)

    def _analyze_chunk_relationship(self, chunk_a: MemoryChunk, chunk_b: MemoryChunk) -> str:
        """Analyze relationship between two chunks (validates/contradicts/neutral)."""
        # This could be enhanced with LLM analysis, but for now use simple heuristics
        if (chunk_a.outcome_success and chunk_b.outcome_success and
            chunk_a.engineering_pattern == chunk_b.engineering_pattern):
            return 'validates'
        elif (chunk_a.outcome_success and not chunk_b.outcome_success and
              chunk_a.engineering_pattern == chunk_b.engineering_pattern):
            return 'contradicts'
        else:
            return 'neutral'

    def _cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        import math

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = math.sqrt(sum(a * a for a in vec_a))
        magnitude_b = math.sqrt(sum(b * b for b in vec_b))

        if magnitude_a == 0.0 or magnitude_b == 0.0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def _update_chunk_in_qdrant(self, chunk: MemoryChunk):
        """Update chunk in Qdrant with new metadata."""
        try:
            payload_data = {
                'content': chunk.content,
                'timestamp': chunk.timestamp.isoformat(),
                'source_context': chunk.source_context,
                'engineering_pattern': chunk.engineering_pattern,
                'confidence_score': chunk.confidence_score,
                'relevance_tags': chunk.relevance_tags,
                'superseded_by': chunk.superseded_by,
                'quality_score': chunk.quality_score,
                'evidence_strength': chunk.evidence_strength,
                'outcome_success': chunk.outcome_success,
                'solution_effectiveness': chunk.solution_effectiveness,
                'dependencies': chunk.dependencies or [],
                'contradicts': chunk.contradicts or [],
                'validates': chunk.validates or []
            }

            point = {
                "id": chunk.id,
                "vector": chunk.embedding,
                "payload": payload_data
            }

            response = requests.put(
                f"{self.qdrant_url}/collections/{self.collection_name}/points",
                json={"points": [point]},
                timeout=10
            )

            if response.status_code not in [200, 201]:
                print(f"[MEMORY-CURATOR-ERROR] Failed to update chunk {chunk.id}: {response.status_code}")

        except Exception as e:
            print(f"[MEMORY-CURATOR-ERROR] Failed to update chunk: {e}")

    def _remove_chunk_from_qdrant(self, chunk_id: str):
        """Remove chunk from Qdrant."""
        try:
            response = requests.post(
                f"{self.qdrant_url}/collections/{self.collection_name}/points/delete",
                json={"points": [chunk_id]},
                timeout=10
            )

            if response.status_code not in [200, 201]:
                print(f"[MEMORY-CURATOR-ERROR] Failed to remove chunk {chunk_id}: {response.status_code}")

        except Exception as e:
            print(f"[MEMORY-CURATOR-ERROR] Failed to remove chunk: {e}")


def main():
    """Run memory curation for the project."""
    import argparse

    parser = argparse.ArgumentParser(description='Advanced Memory Curator with EBR')
    parser.add_argument('--project-root', type=str, help='Project root directory')
    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    curator = AdvancedMemoryCurator(project_root)
    result = curator.curate_memory_collection()

    print(f"""
[MEMORY-CURATOR] Curation Complete!

Results:
- Duplicate clusters found: {result.duplicates_found}
- Outdated chunks removed: {result.outdated_removed}
- Quality improvements: {result.quality_improved}
- Evidence consolidations: {result.evidence_consolidated}

Memory collection is now optimized with EBR!
""")


if __name__ == "__main__":
    main()