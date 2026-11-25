"""
Session Store: In-memory store for per-call state (keyed by session_id).
Designed with a thread-safe minimal interface so it can be swapped for Redis later.
"""

import threading
from typing import List, Dict

# Module-level session storage and thread lock
_lock = threading.Lock()
_sessions: Dict[str, List[Dict[str, str]]] = {}

def create_or_get_session(session_id: str) -> List[Dict[str, str]]:
    """
    Retrieves the message history for a session_id, or initializes an empty list.
    Thread-safe: acquired with a lock to protect concurrent multi-tab calls.
    """
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = []
        return _sessions[session_id]

def append_message(session_id: str, role: str, content: str) -> None:
    """
    Appends a new message (role: 'user' or 'assistant') to the session history.
    """
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = []
        _sessions[session_id].append({"role": role, "content": content})

def get_messages(session_id: str) -> List[Dict[str, str]]:
    """
    Returns a copy of the list of messages for the given session_id.
    """
    with _lock:
        if session_id not in _sessions:
            return []
        # Return a shallow copy of the message list to avoid mutation outside the lock
        return list(_sessions[session_id])

def clear_session(session_id: str) -> None:
    """
    Clears the history for a given session_id (e.g., when a call ends).
    """
    with _lock:
        if session_id in _sessions:
            _sessions[session_id] = []
