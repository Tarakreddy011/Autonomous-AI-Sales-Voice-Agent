"""
Knowledge Base Module: Multilingual Vector Retrieval using ChromaDB.
Model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
Singleton pattern: The Chroma client and embedding model load once and are reused across all caller sessions.
"""

import os
from typing import List, Dict
import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "comfort_chairs_kb"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# 1. Singleton initialization: loaded ONCE at module load
_client = None
_collection = None

def _get_collection():
    global _client, _collection
    if _collection is None:
        emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL_NAME
        )
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = _client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=emb_fn
        )
    return _collection

def search_knowledge(query: str, top_k: int = 4) -> List[Dict]:
    """
    Searches the Comfort Chairs catalog and FAQs for matching chunks.
    Works seamlessly for both English and Hindi queries.
    
    Returns:
        List of dicts: [{"id": str, "content": str, "metadata": dict, "score": float}]
    """
    if not query or not query.strip():
        return []

    collection = _get_collection()
    
    results = collection.query(
        query_texts=[query],
        n_results=top_k
    )

    chunks = []
    if results and "documents" in results and results["documents"]:
        docs = results["documents"][0]
        metas = results["metadatas"][0] if "metadatas" in results else [{}] * len(docs)
        dists = results["distances"][0] if "distances" in results else [0.0] * len(docs)
        ids = results["ids"][0] if "ids" in results else [""] * len(docs)

        for doc_id, text, meta, dist in zip(ids, docs, metas, dists):
            # Chroma returns cosine distance; similarity = 1 - distance
            similarity = round(max(0.0, 1.0 - dist), 3)
            chunks.append({
                "id": doc_id,
                "content": text,
                "metadata": meta,
                "score": similarity
            })

    return chunks
