"""
Tools Module: Definitions and dispatcher for LLM tool calling.
Registers search_knowledge for RAG retrieval over Comfort Chairs catalog & FAQs.
"""

import json
from typing import Tuple, List, Dict
import knowledge_base

# Tool specifications provided to the Groq Chat model
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Searches the Comfort Chairs knowledge base for chair models, categories, prices, materials, dimensions, warranty, delivery speed, showroom timings, or store policies. Call this whenever the user asks any question about chairs or store information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query keywords, e.g. 'gaming chair price', 'ergonomic mesh chair for back pain', 'showroom opening hours'."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def execute_tool_call(name: str, arguments_json: str) -> Tuple[str, List[Dict]]:
    """
    Executes a tool call requested by the model.
    
    Returns:
        tuple of (result_json_string: str, retrieved_chunks_list: list)
    """
    try:
        args = json.loads(arguments_json) if isinstance(arguments_json, str) else arguments_json
    except Exception:
        args = {}

    if name == "search_knowledge":
        query = args.get("query", "")
        chunks = knowledge_base.search_knowledge(query=query, top_k=4)
        
        # Prepare a clean, concise text summary for the LLM context
        if not chunks:
            result_payload = {"status": "no_results_found", "message": "No matching chairs or policies found."}
        else:
            result_payload = {
                "status": "success",
                "results_count": len(chunks),
                "knowledge_items": [
                    {
                        "name": c["metadata"].get("name", "Unknown"),
                        "category": c["metadata"].get("category", ""),
                        "price_inr": c["metadata"].get("price", 0),
                        "details": c["content"]
                    }
                    for c in chunks
                ]
            }
        return json.dumps(result_payload, ensure_ascii=False), chunks

    return json.dumps({"error": f"Unknown tool: {name}"}), []
