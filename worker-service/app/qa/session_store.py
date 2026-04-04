"""Simple in-memory session store for conversation state.

This module provides a thread-safe in-memory key-value store for session data.
In production, this should be replaced with Redis or another distributed cache.
"""
import threading
from typing import Any, Optional


class SessionStore:
    """Thread-safe in-memory session store.
    
    Stores session data as nested dictionaries: session_id -> key -> value.
    """
    
    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def get(self, session_id: str, key: str) -> Optional[Any]:
        """Get a value from the session store.
        
        Args:
            session_id: The session identifier
            key: The key within the session
            
        Returns:
            The stored value, or None if not found
        """
        with self._lock:
            session = self._store.get(session_id, {})
            return session.get(key)
    
    def set(self, session_id: str, key: str, value: Any) -> None:
        """Set a value in the session store.
        
        Args:
            session_id: The session identifier
            key: The key within the session
            value: The value to store
        """
        with self._lock:
            if session_id not in self._store:
                self._store[session_id] = {}
            self._store[session_id][key] = value
    
    def delete(self, session_id: str, key: Optional[str] = None) -> None:
        """Delete a key or entire session from the store.
        
        Args:
            session_id: The session identifier
            key: The key to delete, or None to delete the entire session
        """
        with self._lock:
            if key is None:
                # Delete entire session
                self._store.pop(session_id, None)
            else:
                # Delete specific key
                session = self._store.get(session_id)
                if session:
                    session.pop(key, None)
    
    def clear(self) -> None:
        """Clear all sessions from the store."""
        with self._lock:
            self._store.clear()


# Global session store instance
_session_store = SessionStore()


def get_session_store() -> SessionStore:
    """Get the global session store instance."""
    return _session_store
