"""In-memory conversation store, keyed by a per-browser session id.

Keeps the last N turns so follow-up questions ("and for last quarter?") have
context. This is process-local; for a multi-instance deployment, swap this for
Redis with the same get/append/clear interface.
"""
import threading
import time


class ConversationMemory:
    def __init__(self, max_turns: int = 8, ttl_seconds: int = 3600):
        self._store = {}
        self._lock = threading.Lock()
        self.max_turns = max_turns
        self.ttl = ttl_seconds

    def _expired(self, entry) -> bool:
        return (time.time() - entry["updated"]) > self.ttl

    def get(self, conversation_id: str):
        """Return a list of {role, content} dicts ready to pass to the LLM."""
        with self._lock:
            entry = self._store.get(conversation_id)
            if not entry:
                return []
            if self._expired(entry):
                self._store.pop(conversation_id, None)
                return []
            return list(entry["turns"])

    def append(self, conversation_id: str, role: str, content: str):
        with self._lock:
            entry = self._store.setdefault(
                conversation_id, {"turns": [], "updated": time.time()}
            )
            entry["turns"].append({"role": role, "content": content})
            # Keep the last max_turns exchanges (user + assistant = 2 each).
            entry["turns"] = entry["turns"][-(self.max_turns * 2):]
            entry["updated"] = time.time()

    def clear(self, conversation_id: str):
        with self._lock:
            self._store.pop(conversation_id, None)

    # --- last successful data query (for resolving follow-ups) -----------
    def set_last_query(self, conversation_id: str, question: str, sql: str,
                       columns: list, rows: list = None, viz: dict = None,
                       row_count: int = None):
        with self._lock:
            entry = self._store.setdefault(
                conversation_id,
                {"turns": [], "updated": time.time(), "last_query": None},
            )
            entry["last_query"] = {
                "question": question,
                "sql": sql,
                "columns": list(columns),
                "rows": list(rows) if rows is not None else [],
                "viz": dict(viz) if viz else {},
                "row_count": row_count if row_count is not None else (
                    len(rows) if rows is not None else 0
                ),
            }
            entry["updated"] = time.time()

    def get_last_query(self, conversation_id: str):
        with self._lock:
            entry = self._store.get(conversation_id)
            if not entry or self._expired(entry):
                return None
            return entry.get("last_query")
