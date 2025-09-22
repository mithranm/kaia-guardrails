#!/Users/briyamanick/miniconda3/envs/mcp-unified/bin/python
"""
Qdrant Chat Ingestion Hook

Ingests every chat turn into Qdrant vector database for enhanced context analysis.
Provides programmatic access to conversation history for the process guard system.
"""

import os
import sys
import json
import glob
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

def get_current_process() -> str:
    """Get current process focus."""
    try:
        project_root = get_project_root()
        process_file = project_root / '.claude' / 'current-process.txt'

        if process_file.exists():
            return process_file.read_text().strip()
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"

def get_project_root() -> Path:
    """Find the project root."""
    current = Path.cwd()
    while current.parent != current:
        if (current / '.git').exists():
            return current
        current = current.parent
    return Path.cwd()

def find_current_chat_session() -> Optional[Path]:
    """Find the most recent chat session JSONL file."""
    project_root = get_project_root()
    # Look for chat sessions in user's .claude directory
    claude_projects_pattern = f"/Users/{os.getenv('USER', 'briyamanick')}/.claude/projects/*-{project_root.name}/*.jsonl"

    session_files = glob.glob(claude_projects_pattern)
    if not session_files:
        return None

    # Return most recently modified
    return Path(max(session_files, key=os.path.getmtime))

def find_todays_chat_sessions() -> List[Path]:
    """Find all chat session files modified today from ALL Claude projects."""
    # Search ALL Claude project directories, not just current project
    claude_projects_pattern = f"/Users/{os.getenv('USER', 'briyamanick')}/.claude/projects/*/*.jsonl"

    session_files = glob.glob(claude_projects_pattern)
    today = datetime.now().date()

    todays_sessions = []
    for file_path in session_files:
        file_date = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
        if file_date == today:
            todays_sessions.append(Path(file_path))

    return sorted(todays_sessions, key=os.path.getmtime)

def find_all_chat_sessions() -> List[Path]:
    """Find all chat session files for comprehensive memory ingestion from ALL Claude projects."""
    # Search ALL Claude project directories, not just current project
    claude_projects_pattern = f"/Users/{os.getenv('USER', 'briyamanick')}/.claude/projects/*/*.jsonl"

    session_files = glob.glob(claude_projects_pattern)
    return sorted([Path(f) for f in session_files], key=os.path.getmtime)

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    """Split text into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)

        # If this is the last chunk, break
        if end >= len(text):
            break

        # Move start position with overlap
        start = end - overlap

    return chunks

def extract_unique_messages_with_graph_metadata(session_file: Path, num_messages: int = 5) -> List[Dict]:
    """Extract unique messages with graph structure metadata (UUID deduplication)."""
    seen_uuids = set()
    messages = []
    all_raw_messages = []

    try:
        with open(session_file, 'r') as f:
            lines = f.readlines()

            # Parse ALL messages first to understand graph structure
            for line in lines:
                try:
                    msg = json.loads(line.strip())
                    if msg.get('type') in ['human', 'assistant']:
                        all_raw_messages.append(msg)
                except json.JSONDecodeError:
                    continue

            # Get last N lines for processing (but use all for graph context)
            target_messages = all_raw_messages[-num_messages:] if num_messages else all_raw_messages

            for msg in target_messages:
                uuid = msg.get('uuid', '')

                # Skip if we've already processed this UUID (deduplication)
                if uuid in seen_uuids:
                    continue

                # Extract text content from various content types
                content_text = ""

                # Handle both new message format and legacy format
                if 'message' in msg and isinstance(msg['message'], dict):
                    # New format: content is in message.content
                    content = msg['message'].get('content', [])
                else:
                    # Legacy format: content is direct
                    content = msg.get('content', [])

                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get('type') == 'text':
                                content_text += item.get('text', '')
                            elif item.get('type') == 'tool_use':
                                content_text += f"[TOOL: {item.get('name', 'unknown')}]"
                            elif item.get('type') == 'tool_result':
                                content_text += f"[TOOL_RESULT]"

                # Skip messages with no content
                if not content_text.strip():
                    continue

                # Mark this UUID as seen
                seen_uuids.add(uuid)

                # Parse timestamp to ensure ANSI format
                timestamp = msg.get('timestamp')
                if timestamp and not timestamp.endswith('Z'):
                    # Ensure ISO format with Z suffix
                    timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%S.%fZ')

                # Chunk the content properly instead of just truncating
                chunks = chunk_text(content_text, chunk_size=800, overlap=200)

                # Graph metadata analysis
                parent_uuid = msg.get('parentUuid')
                is_sidechain = msg.get('isSidechain', False)

                # Check if this message is referenced by others (has children)
                has_children = any(m.get('parentUuid') == uuid for m in all_raw_messages)

                # Create separate message for each chunk
                for i, chunk_content in enumerate(chunks):
                    chunk_uuid = f"{uuid}_chunk_{i}" if len(chunks) > 1 else uuid
                    messages.append({
                        'uuid': chunk_uuid,
                        'original_uuid': uuid,  # Keep original UUID for graph traversal
                        'type': msg['type'],
                        'content': chunk_content,
                        'timestamp': timestamp,
                        'session_id': msg.get('sessionId', ''),
                        'cwd': msg.get('cwd', ''),
                        'git_branch': msg.get('gitBranch', ''),
                        'process_context': get_current_process(),
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        # Graph structure metadata
                        'parent_uuid': parent_uuid,
                        'is_sidechain': is_sidechain,
                        'has_children': has_children,
                        'graph_depth': calculate_graph_depth(msg, all_raw_messages) if parent_uuid else 0
                    })

    except Exception as e:
        print(f"Error reading chat session: {e}")

    print(f"📊 Processed {len(messages)} unique message chunks from {len(seen_uuids)} unique messages")
    return messages

def calculate_graph_depth(message: Dict, all_messages: List[Dict]) -> int:
    """Calculate depth in conversation graph."""
    depth = 0
    current_uuid = message.get('parentUuid')

    # Traverse up the parent chain
    while current_uuid:
        depth += 1
        parent_msg = next((m for m in all_messages if m.get('uuid') == current_uuid), None)
        if parent_msg:
            current_uuid = parent_msg.get('parentUuid')
        else:
            break

    return depth

def extract_code_blocks(text: str) -> List[str]:
    """Extract code blocks from markdown text."""
    import re

    # Match markdown code blocks (```language\ncode\n```)
    code_pattern = r'```[\w]*\n(.*?)\n```'
    code_blocks = re.findall(code_pattern, text, re.DOTALL)

    # Also match inline code (`code`)
    inline_pattern = r'`([^`\n]+)`'
    inline_code = re.findall(inline_pattern, text)

    return code_blocks + inline_code

def get_code_embedding(code_text: str) -> List[float]:
    """Get code embeddings from VanguardOne GraphCodeBERT service."""
    try:
        import requests

        # Use VanguardOne for code
        api_url = "https://vanguardone-embedding-auth-worker.mithran-mohanraj.workers.dev"

        response = requests.post(
            f"{api_url}/v1/embeddings",
            json={
                "input": code_text[:500],  # GraphCodeBERT has ~512 token limit
                "model": "graphcodebert-base"
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result['data'][0]['embedding']
        else:
            print(f"Code embedding API error: {response.status_code}")
            return None

    except Exception as e:
        print(f"Code embedding generation error: {e}")
        return None

def get_natural_language_embedding(text: str) -> List[float]:
    """Get natural language embeddings from VanguardTwo BGE-M3 service."""
    try:
        import requests

        # Use VanguardTwo for natural language
        api_url = "https://vanguardtwo-embedding-auth-worker.mithran-mohanraj.workers.dev"

        response = requests.post(
            f"{api_url}/v1/embeddings",
            json={
                "input": text[:8000],  # BGE-M3 supports ~8192 tokens, leave margin
                "model": "bge-m3"
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result['data'][0]['embedding']
        else:
            print(f"NL embedding API error: {response.status_code}")
            return None

    except Exception as e:
        print(f"NL embedding generation error: {e}")
        return None

def get_embedding_config():
    """Get embedding configuration from vibelint config."""
    try:
        # Try to load vibelint config
        import sys
        sys.path.insert(0, str(get_project_root() / 'tools' / 'vibelint' / 'src'))
        from vibelint.config import load_config

        config = load_config(get_project_root())
        embeddings_config = config.settings.get('embeddings', {})

        # STRICT CONFIG MODE: All required fields must be present
        if 'natural_api_url' not in embeddings_config:
            raise ValueError("REQUIRED CONFIG MISSING: 'natural_api_url' not found in embeddings config")
        if 'code_api_url' not in embeddings_config:
            raise ValueError("REQUIRED CONFIG MISSING: 'code_api_url' not found in embeddings config")

        return {
            'natural_api_url': embeddings_config['natural_api_url'],
            'natural_model': embeddings_config.get('natural_model', 'bge-m3'),
            'natural_dimensions': embeddings_config.get('natural_dimensions', 1024),
            'code_api_url': embeddings_config['code_api_url'],
            'code_model': embeddings_config.get('code_model', 'graphcodebert-base'),
            'code_dimensions': embeddings_config.get('code_dimensions', 768)
        }
    except Exception as e:
        print(f"[QDRANT-INGESTER-FATAL] Configuration error: {e}", file=sys.stderr)
        raise  # Fail loudly, no defaults
        # Fallback configuration
        return {
            'natural_api_url': 'https://vanguardtwo-embedding-auth-worker.mithran-mohanraj.workers.dev',
            'natural_model': 'bge-m3',
            'natural_dimensions': 1024,
            'code_api_url': 'https://vanguardone-embedding-auth-worker.mithran-mohanraj.workers.dev',
            'code_model': 'graphcodebert-base',
            'code_dimensions': 768
        }

def get_batch_natural_language_embeddings(texts: List[str]) -> List[List[float]]:
    """Get batch natural language embeddings using vibelint configuration."""
    try:
        import requests

        config = get_embedding_config()
        api_url = config['natural_api_url']
        model = config['natural_model']

        # Truncate texts to BGE-M3 token limit
        truncated_texts = [text[:8000] for text in texts]

        response = requests.post(
            f"{api_url}/v1/embeddings/batch",
            json={
                "inputs": truncated_texts,
                "model": model
            },
            timeout=120  # Longer timeout for batch processing
        )

        if response.status_code == 200:
            result = response.json()
            # Sort by index to maintain order
            sorted_data = sorted(result['data'], key=lambda x: x['index'])
            return [item['embedding'] for item in sorted_data]
        else:
            print(f"Batch NL embedding API error: {response.status_code}")
            return None

    except Exception as e:
        print(f"Batch NL embedding generation error: {e}")
        return None

def ingest_to_qdrant(messages: List[Dict]) -> bool:
    """Ingest messages into Qdrant vector database with real embeddings."""
    try:
        # Check if Qdrant is available
        import requests

        # Try to connect to local Qdrant instance
        qdrant_url = "http://localhost:6333"

        # Check if Qdrant is running
        try:
            response = requests.get(f"{qdrant_url}/collections")
            if response.status_code != 200:
                print(f"Qdrant not available: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("Qdrant not running - skipping ingestion")
            return False

        # Create collection if it doesn't exist
        collection_name = "chat_history"

        collections_response = requests.get(f"{qdrant_url}/collections")
        existing_collections = [c['name'] for c in collections_response.json().get('result', {}).get('collections', [])]

        if collection_name not in existing_collections:
            config = get_embedding_config()
            create_collection = {
                "name": collection_name,
                "vectors": {
                    "size": config['natural_dimensions'],  # Use configured embedding size
                    "distance": "Cosine"
                }
            }

            response = requests.put(f"{qdrant_url}/collections/{collection_name}", json=create_collection)
            if response.status_code not in [200, 409]:  # 409 = already exists
                print(f"Failed to create collection: {response.status_code}")
                return False

        # Generate embeddings and ingest messages
        for msg in messages:
            # Create a unique ID for this message
            message_id = hashlib.md5(f"{msg['uuid']}{msg['timestamp']}".encode()).hexdigest()

            # Extract code blocks for analysis
            code_blocks = extract_code_blocks(msg['content'])

            # Prepare text for embedding (use full content, BGE-M3 can handle ~8192 tokens)
            text_for_embedding = f"{msg['type']}: {msg['content']}"

            # Get real embedding from VanguardTwo BGE-M3 (handles both code and natural language)
            real_embedding = get_natural_language_embedding(text_for_embedding)
            if real_embedding is None:
                print(f"Failed to get embedding for message {message_id}, skipping")
                continue

            # Schema: 1. ANSI timestamp ingested, 2. Friendly process name, 3. Unstructured metadata

            # 1. ANSI timestamp ingested (post-hoc, use original timestamp as substitute if available)
            ingested_timestamp = msg.get('timestamp') or datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')

            # 2. Friendly name for process (semantically rich for meta embeddings)
            # Include the actual project being worked on (from cwd)
            project_name = "Unknown project"
            if msg.get('cwd'):
                try:
                    # Extract project name from the working directory path
                    cwd_path = Path(msg['cwd'])
                    project_name = cwd_path.name
                    # If it's a nested project (like tools/vibelint), include more context
                    if len(cwd_path.parts) > 1:
                        parent_dir = cwd_path.parent.name
                        if parent_dir in ['tools', 'src', 'packages']:
                            project_name = f"{parent_dir}/{project_name}"
                except Exception:
                    project_name = str(msg['cwd']).split('/')[-1] if msg['cwd'] else "Unknown project"

            # Create rich, descriptive sentence for semantic embeddings
            git_context = f"on branch {msg.get('git_branch', 'unknown')}" if msg.get('git_branch') else "with unknown git state"

            if msg['type'] == 'human':
                friendly_process_name = f"User interaction while working on {project_name} project {git_context}, asking questions or giving instructions to Claude Code"
            else:  # assistant
                friendly_process_name = f"Claude Code assistant response while working on {project_name} project {git_context}, providing solutions and executing tasks"

            if msg.get('process_context') and msg['process_context'] != 'UNKNOWN':
                friendly_process_name = f"Development work on '{msg['process_context']}' process in {project_name} project {git_context}, involving {'user instruction' if msg['type'] == 'human' else 'AI assistant response'}"

            # 3. Unstructured metadata for NoSQL queries
            unstructured_metadata = {
                "content_length": len(msg['content']),
                "has_tool_calls": "[TOOL:" in msg['content'],
                "has_code_blocks": "```" in msg['content'],
                "is_question": "?" in msg['content'],
                "is_command": msg['content'].startswith('/') if msg['content'] else False,
                "word_count": len(msg['content'].split()) if msg['content'] else 0,
                "session_id": msg['session_id'],
                "cwd": msg['cwd'],
                "git_branch": msg['git_branch'],
                "original_uuid": msg['uuid']
            }

            # 4. Code-specific metadata for hierarchical search
            code_metadata = {
                "code_block_count": len(code_blocks),
                "total_code_chars": sum(len(block) for block in code_blocks),
                "code_languages": [],  # TODO: detect languages from code blocks
                "has_python": any("def " in block or "import " in block for block in code_blocks),
                "has_javascript": any("function " in block or "const " in block for block in code_blocks),
                "has_shell": any("#!/bin/" in block or "curl " in block for block in code_blocks),
                "has_json": any('{"' in block and '"}' in block for block in code_blocks),
                "code_patterns": [],  # TODO: extract function names, imports, etc.
                "file_references": [],  # TODO: extract file paths mentioned
            }

            # Extract file paths from content
            import re
            file_pattern = r'[a-zA-Z0-9_\-/.]+\.(py|js|ts|json|md|toml|yml|yaml|sh|txt)'
            file_refs = re.findall(file_pattern, msg['content'])
            code_metadata["file_references"] = list(set(file_refs))

            point = {
                "id": message_id,
                "vector": real_embedding,
                "payload": {
                    "content": msg['content'],
                    "ansi_timestamp_ingested": ingested_timestamp,  # 1. ANSI timestamp
                    "friendly_process_name": friendly_process_name,  # 2. Semantic process description
                    "unstructured_metadata": unstructured_metadata,  # 3. NoSQL queryable data
                    "code_metadata": code_metadata  # 4. Code-specific hierarchical search metadata
                }
            }

            # Upsert the point
            response = requests.put(
                f"{qdrant_url}/collections/{collection_name}/points",
                json={
                    "points": [point]
                }
            )

            if response.status_code not in [200, 202]:
                print(f"Failed to ingest message {message_id}: {response.status_code}")
                continue

        print(f"✅ Ingested {len(messages)} messages into Qdrant")
        return True

    except ImportError:
        print("requests library not available - skipping Qdrant ingestion")
        return False
    except Exception as e:
        print(f"Error ingesting to Qdrant: {e}")
        return False

def ingest_to_qdrant_batch(messages: List[Dict]) -> bool:
    """Ingest messages into Qdrant using batch embeddings for better performance."""
    try:
        import requests
        import hashlib
        import re

        if not messages:
            return True

        # Check if Qdrant is available
        qdrant_url = "http://localhost:6333"
        try:
            response = requests.get(f"{qdrant_url}/collections")
            if response.status_code != 200:
                print(f"Qdrant not available: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("Qdrant not running - skipping ingestion")
            return False

        # Create collection if it doesn't exist
        collection_name = "chat_history"
        collections_response = requests.get(f"{qdrant_url}/collections")
        existing_collections = [c['name'] for c in collections_response.json().get('result', {}).get('collections', [])]

        if collection_name not in existing_collections:
            config = get_embedding_config()
            create_collection = {
                "name": collection_name,
                "vectors": {
                    "size": config['natural_dimensions'],  # Use configured embedding size
                    "distance": "Cosine"
                }
            }
            response = requests.put(f"{qdrant_url}/collections/{collection_name}", json=create_collection)
            if response.status_code not in [200, 409]:
                print(f"Failed to create collection: {response.status_code}")
                return False

        # Step 1: Prepare all texts for batch embedding
        texts_for_embedding = []
        message_metadata = []

        for msg in messages:
            # Prepare text for embedding (same as individual version)
            text_for_embedding = f"{msg['type']}: {msg['content']}"
            texts_for_embedding.append(text_for_embedding)

            # Pre-compute all metadata
            code_blocks = extract_code_blocks(msg['content'])
            message_id = hashlib.md5(f"{msg['uuid']}{msg['timestamp']}".encode()).hexdigest()
            ingested_timestamp = msg.get('timestamp') or datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')

            # Rich project context
            project_name = "Unknown project"
            if msg.get('cwd'):
                try:
                    cwd_path = Path(msg['cwd'])
                    project_name = cwd_path.name
                    if len(cwd_path.parts) > 1:
                        parent_dir = cwd_path.parent.name
                        if parent_dir in ['tools', 'src', 'packages']:
                            project_name = f"{parent_dir}/{project_name}"
                except Exception:
                    project_name = str(msg['cwd']).split('/')[-1] if msg['cwd'] else "Unknown project"

            git_context = f"on branch {msg.get('git_branch', 'unknown')}" if msg.get('git_branch') else "with unknown git state"

            if msg['type'] == 'human':
                friendly_process_name = f"User interaction while working on {project_name} project {git_context}, asking questions or giving instructions to Claude Code"
            else:
                friendly_process_name = f"Claude Code assistant response while working on {project_name} project {git_context}, providing solutions and executing tasks"

            if msg.get('process_context') and msg['process_context'] != 'UNKNOWN':
                friendly_process_name = f"Development work on '{msg['process_context']}' process in {project_name} project {git_context}, involving {'user instruction' if msg['type'] == 'human' else 'AI assistant response'}"

            # Store metadata for later use
            file_pattern = r'[a-zA-Z0-9_\-/.]+\.(py|js|ts|json|md|toml|yml|yaml|sh|txt)'
            file_refs = re.findall(file_pattern, msg['content'])

            message_metadata.append({
                'message_id': message_id,
                'friendly_process_name': friendly_process_name,
                'ingested_timestamp': ingested_timestamp,
                'code_blocks': code_blocks,
                'file_refs': list(set(file_refs)),
                'original_msg': msg
            })

        # Step 2: Get batch embeddings
        print(f"🚀 Getting batch embeddings for {len(texts_for_embedding)} messages...")
        batch_embeddings = get_batch_natural_language_embeddings(texts_for_embedding)

        if batch_embeddings is None:
            print("❌ Batch embedding failed, falling back to individual embeddings")
            return ingest_to_qdrant(messages)  # Fallback to individual

        if len(batch_embeddings) != len(messages):
            print(f"❌ Embedding count mismatch: {len(batch_embeddings)} vs {len(messages)}")
            return False

        # Step 3: Build all Qdrant points
        points = []
        for i, (embedding, metadata) in enumerate(zip(batch_embeddings, message_metadata)):
            msg = metadata['original_msg']
            code_blocks = metadata['code_blocks']

            unstructured_metadata = {
                "content_length": len(msg['content']),
                "has_tool_calls": "[TOOL:" in msg['content'],
                "has_code_blocks": "```" in msg['content'],
                "is_question": "?" in msg['content'],
                "is_command": msg['content'].startswith('/') if msg['content'] else False,
                "word_count": len(msg['content'].split()) if msg['content'] else 0,
                "session_id": msg['session_id'],
                "cwd": msg['cwd'],
                "git_branch": msg['git_branch'],
                "original_uuid": msg['uuid']
            }

            code_metadata = {
                "code_block_count": len(code_blocks),
                "total_code_chars": sum(len(block) for block in code_blocks),
                "code_languages": [],
                "has_python": any("def " in block or "import " in block for block in code_blocks),
                "has_javascript": any("function " in block or "const " in block for block in code_blocks),
                "has_shell": any("#!/bin/" in block or "curl " in block for block in code_blocks),
                "has_json": any('{"' in block and '"}' in block for block in code_blocks),
                "code_patterns": [],
                "file_references": metadata['file_refs'],
            }

            point = {
                "id": metadata['message_id'],
                "vector": embedding,
                "payload": {
                    "content": msg['content'],
                    "ansi_timestamp_ingested": metadata['ingested_timestamp'],
                    "friendly_process_name": metadata['friendly_process_name'],
                    "unstructured_metadata": unstructured_metadata,
                    "code_metadata": code_metadata
                }
            }
            points.append(point)

        # Step 4: Bulk upsert to Qdrant
        print(f"📊 Bulk upserting {len(points)} points to Qdrant...")
        response = requests.put(
            f"{qdrant_url}/collections/{collection_name}/points",
            json={"points": points}
        )

        if response.status_code in [200, 202]:
            print(f"✅ Batch ingested {len(points)} messages into Qdrant")
            return True
        else:
            print(f"❌ Bulk upsert failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"Batch ingestion error: {e}")
        return False

def bulk_ingest_todays_chats(batch_size=None):
    """Ingest all chat sessions from today with optional batch size limit."""
    try:
        todays_sessions = find_todays_chat_sessions()
        if not todays_sessions:
            print("No chat sessions found for today")
            return

        total_messages = 0
        messages_processed = 0

        for session_file in todays_sessions:
            print(f"Processing {session_file.name}...")
            # Extract messages from this session
            num_to_extract = batch_size - messages_processed if batch_size else 1000
            if num_to_extract <= 0:
                break

            messages = extract_unique_messages_with_graph_metadata(session_file, num_messages=num_to_extract)
            if messages:
                success = ingest_to_qdrant_batch(messages)
                if success:
                    total_messages += len(messages)
                    messages_processed += len(messages)
                    print(f"  ✅ Ingested {len(messages)} messages")

                    if batch_size and messages_processed >= batch_size:
                        print(f"🎯 Batch limit reached: {messages_processed} messages processed")
                        break
                else:
                    print(f"  ❌ Failed to ingest {session_file.name}")

        print(f"🎯 Bulk ingestion complete: {total_messages} total messages from {len(todays_sessions)} sessions")

    except Exception as e:
        print(f"Bulk ingestion error: {e}")

def bulk_ingest_all_chats():
    """Ingest all chat sessions for comprehensive memory."""
    try:
        all_sessions = find_all_chat_sessions()
        if not all_sessions:
            print("No chat sessions found")
            return

        total_messages = 0
        for session_file in all_sessions:
            print(f"Processing {session_file.name}...")
            # Extract all messages from this session
            messages = extract_unique_messages_with_graph_metadata(session_file, num_messages=5000)  # Large number to get all
            if messages:
                success = ingest_to_qdrant_batch(messages)
                if success:
                    total_messages += len(messages)
                    print(f"  ✅ Ingested {len(messages)} messages")
                else:
                    print(f"  ❌ Failed to ingest {session_file.name}")

        print(f"🧠 Comprehensive memory ingestion complete: {total_messages} total messages from {len(all_sessions)} sessions")

    except Exception as e:
        print(f"Comprehensive ingestion error: {e}")

def main():
    """Main hook entry point."""
    try:
        # Check command line arguments
        if len(sys.argv) > 1:
            if sys.argv[1] == "--bulk-today":
                batch_size = None
                if len(sys.argv) > 2 and sys.argv[2].isdigit():
                    batch_size = int(sys.argv[2])
                    print(f"🎯 Using batch size: {batch_size}")
                bulk_ingest_todays_chats(batch_size)
                return
            elif sys.argv[1] == "--bulk-all":
                bulk_ingest_all_chats()
                return

        # Find current session and extract recent messages
        session_file = find_current_chat_session()
        if not session_file:
            print("No chat session found - skipping ingestion")
            return

        # Extract recent messages
        messages = extract_unique_messages_with_graph_metadata(session_file, num_messages=10)
        if not messages:
            print("No messages found - skipping ingestion")
            return

        # Ingest into Qdrant
        success = ingest_to_qdrant(messages)

        if success:
            print(f"📊 Chat ingestion complete: {len(messages)} messages")
        else:
            print("⚠️  Chat ingestion failed")

    except Exception as e:
        print(f"Chat ingestion error: {e}")

if __name__ == '__main__':
    main()