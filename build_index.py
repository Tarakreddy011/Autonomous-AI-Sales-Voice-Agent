"""
Build Index Script: Indexes Comfort Chairs catalog and FAQs into a persistent ChromaDB.
Uses sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 for English and Hindi semantic search.
"""

import os
import json
import chromadb
from chromadb.utils import embedding_functions

# Path constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "knowledge.json")
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "comfort_chairs_kb"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

def build_index():
    print(f"Loading knowledge base from {DATA_FILE}...")
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Initialize Chroma persistent client and embedding function
    print(f"Initializing multilingual embedding model: {EMBEDDING_MODEL_NAME}...")
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL_NAME
    )
    
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    
    # Delete collection if it exists to allow fresh re-indexing
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Reset existing collection '{COLLECTION_NAME}'.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"}
    )

    documents = []
    metadatas = []
    ids = []

    # 1. Chunk Products
    print("Formatting product chunks...")
    for item in data.get("products", []):
        doc_text = (
            f"Product: {item['name']}\n"
            f"Category: {item['category']} chair\n"
            f"Price: {item['price_inr']} rupees (INR {item['price_inr']})\n"
            f"Features: {item['key_features']}\n"
            f"Materials: {item['materials']}\n"
            f"Available Colours: {item['colours']}\n"
            f"Warranty: {item['warranty']}\n"
            f"Delivery Time: {item['delivery_time']}"
        )
        documents.append(doc_text)
        metadatas.append({
            "type": "product",
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "price": item["price_inr"]
        })
        ids.append(item["id"])

    # 2. Chunk FAQs
    print("Formatting FAQ chunks...")
    for faq in data.get("faqs", []):
        doc_text = (
            f"FAQ Topic: {faq['topic']}\n"
            f"Question: {faq['question']}\n"
            f"Answer: {faq['answer']}"
        )
        documents.append(doc_text)
        metadatas.append({
            "type": "faq",
            "id": faq["id"],
            "topic": faq["topic"],
            "name": faq["topic"],
            "category": "faq",
            "price": 0
        })
        ids.append(faq["id"])

    print(f"Embedding and adding {len(documents)} chunks to ChromaDB...")
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"SUCCESS! Index built with {collection.count()} chunks in '{CHROMA_DIR}'.")

if __name__ == "__main__":
    build_index()
