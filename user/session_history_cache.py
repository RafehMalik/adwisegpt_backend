"""
session_history_cache.py
========================
A lightweight, thread-safe, in-memory LRU cache for chat session histories.

Why this exists
---------------
Previously every view (ChatView, ChatAdsView, SessionDetailView, RefreshAdsView, …)
independently queried the DB for the same session's message history.  This module
centralises history ownership:

  • First access → load from DB, store in cache.
  • New message arrives → append to the in-memory list, no re-fetch needed.
  • All views read from the same object → zero duplicate DB queries per request.

Architecture
------------
                        ┌──────────────────────────────┐
  ChatView ─────────────►                              │
  ChatAdsView ──────────►   SessionHistoryCache        │◄──► DB (only on miss)
  SessionDetailView ────►   (module-level singleton)   │
  RefreshAdsView ───────►                              │
                        └──────────────────────────────┘

Thread / async safety
---------------------
Django can run views in threads (sync) or coroutines (async). The cache uses
a threading.Lock for sync callers and an asyncio.Lock for async callers.
Both locks are per-session so contention is minimal.

Limits
------
MAX_SESSIONS  – how many sessions to keep in RAM at once (LRU eviction).
MAX_CHARS     – per-session character budget (≈ 70 k tokens × 4 chars/token).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Tunables                                                            #
# ------------------------------------------------------------------ #

MAX_SESSIONS: int   = 500          # LRU capacity (sessions in RAM)
MAX_CHARS:    int   = 280_000      # 70 k tokens × 4 chars — per session
CHARS_PER_TOKEN: int = 4


# ------------------------------------------------------------------ #
#  Internal data structures                                            #
# ------------------------------------------------------------------ #

class _SessionHistory:
    """Holds the message list for a single session plus per-session locks."""

    __slots__ = ("messages", "sync_lock", "async_lock", "total_chars")

    def __init__(self, messages: List[Dict[str, str]]) -> None:
        self.messages: List[Dict[str, str]] = messages
        self.total_chars: int = sum(len(m["content"]) for m in messages)
        self.sync_lock  = threading.Lock()
        self.async_lock = asyncio.Lock()

    # ---------------------------------------------------------------- #
    #  Append                                                           #
    # ---------------------------------------------------------------- #

    def _append_raw(self, role: str, content: str) -> None:
        """Append one message and evict old ones if over budget."""
        self.messages.append({"role": role, "content": content})
        self.total_chars += len(content)

        # Evict from the front until we're within budget
        while self.total_chars > MAX_CHARS and len(self.messages) > 1:
            evicted = self.messages.pop(0)
            self.total_chars -= len(evicted["content"])

    def append(self, role: str, content: str) -> None:
        """Thread-safe append (for sync views)."""
        with self.sync_lock:
            self._append_raw(role, content)

    async def async_append(self, role: str, content: str) -> None:
        """Coroutine-safe append (for async views)."""
        async with self.async_lock:
            self._append_raw(role, content)

    # ---------------------------------------------------------------- #
    #  Snapshot                                                         #
    # ---------------------------------------------------------------- #

    def snapshot(self) -> List[Dict[str, str]]:
        """Return a shallow copy of the current message list."""
        return list(self.messages)


# ------------------------------------------------------------------ #
#  The cache                                                           #
# ------------------------------------------------------------------ #

class _SessionHistoryCache:
    """
    Module-level LRU cache mapping session_id → _SessionHistory.

    Public API
    ----------
    get_history(session_id)           → List[dict]   (sync)
    get_history_async(session_id)     → List[dict]   (async)
    append(session_id, role, content)               (sync)
    async_append(session_id, role, content)         (async)
    invalidate(session_id)                           (sync/async — just removes key)
    warm(session_id, messages)                       (pre-populate, no DB call)
    """

    def __init__(self, capacity: int = MAX_SESSIONS) -> None:
        self._capacity  = capacity
        self._store: OrderedDict[str, _SessionHistory] = OrderedDict()
        self._lock       = threading.Lock()          # guards _store itself
        self._async_lock = asyncio.Lock()            # async equivalent

    # ---------------------------------------------------------------- #
    #  Internal helpers                                                  #
    # ---------------------------------------------------------------- #

    def _load_from_db(self, session_id: str) -> _SessionHistory:
        """
        Synchronous DB load.  Called only on a cache miss.
        Import here to avoid circular imports at module load time.
        """
        from .models import ChatMessage  # adjust app label if needed

        rows = list(
            ChatMessage.objects
            .filter(session__session_id=session_id)
            .order_by("timestamp")
            .values("message_type", "content")
        )

        messages = [{"role": r["message_type"], "content": r["content"]} for r in rows]
        # Trim to budget from the *start* (keep newest)
        total = sum(len(m["content"]) for m in messages)
        while total > MAX_CHARS and messages:
            removed = messages.pop(0)
            total  -= len(removed["content"])

        logger.debug(
            "SessionHistoryCache: loaded %d messages for session %s from DB",
            len(messages), session_id,
        )
        return _SessionHistory(messages)

    def _evict_if_full(self) -> None:
        """Evict the least-recently-used entry if at capacity."""
        while len(self._store) >= self._capacity:
            evicted_key, _ = self._store.popitem(last=False)
            logger.debug("SessionHistoryCache: evicted session %s (LRU)", evicted_key)

    def _touch(self, session_id: str) -> None:
        """Move an existing entry to the MRU end."""
        self._store.move_to_end(session_id)

    # ---------------------------------------------------------------- #
    #  Sync public API                                                   #
    # ---------------------------------------------------------------- #

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        Return the message list for *session_id*.
        Loads from DB on the first call; subsequent calls are in-memory only.
        """
        with self._lock:
            if session_id in self._store:
                self._touch(session_id)
                return self._store[session_id].snapshot()

            # Cache miss → load from DB (still inside the lock to prevent
            # a thundering herd for the same session_id)
            sh = self._load_from_db(session_id)
            self._evict_if_full()
            self._store[session_id] = sh
            return sh.snapshot()

    def append(self, session_id: str, role: str, content: str) -> None:
        """
        Append a new message to the in-memory history.
        If the session isn't cached yet it is loaded first.
        """
        with self._lock:
            if session_id not in self._store:
                sh = self._load_from_db(session_id)
                self._evict_if_full()
                self._store[session_id] = sh
            else:
                self._touch(session_id)
            sh = self._store[session_id]

        # Append outside the global lock (per-session lock inside)
        sh.append(role, content)

    def warm(self, session_id: str, messages: List[Dict[str, str]]) -> None:
        """
        Pre-populate the cache without a DB call.
        Useful right after creating a brand-new session (no rows yet).
        """
        with self._lock:
            self._evict_if_full()
            self._store[session_id] = _SessionHistory(messages)

    def invalidate(self, session_id: str) -> None:
        """Remove a session from the cache (next access will reload from DB)."""
        with self._lock:
            self._store.pop(session_id, None)

    # ---------------------------------------------------------------- #
    #  Async public API                                                  #
    # ---------------------------------------------------------------- #

    async def get_history_async(self, session_id: str) -> List[Dict[str, str]]:
        async with self._async_lock:
            if session_id in self._store:
                self._touch(session_id)
                return self._store[session_id].snapshot()

        # Cache miss — do the DB IO in a thread so we don't block the event loop
        from asgiref.sync import sync_to_async
        sh = await sync_to_async(self._load_from_db)(session_id)

        async with self._async_lock:
            # Double-check: another coroutine may have populated it while we
            # were awaiting the DB call
            if session_id not in self._store:
                self._evict_if_full()
                self._store[session_id] = sh
            self._touch(session_id)
            return self._store[session_id].snapshot()

    async def async_append(self, session_id: str, role: str, content: str) -> None:
        async with self._async_lock:
            if session_id not in self._store:
                from asgiref.sync import sync_to_async
                sh = await sync_to_async(self._load_from_db)(session_id)
                self._evict_if_full()
                self._store[session_id] = sh
            else:
                self._touch(session_id)
            sh = self._store[session_id]

        await sh.async_append(role, content)

    async def async_warm(self, session_id: str, messages: List[Dict[str, str]]) -> None:
        async with self._async_lock:
            self._evict_if_full()
            self._store[session_id] = _SessionHistory(messages)

    async def async_invalidate(self, session_id: str) -> None:
        async with self._async_lock:
            self._store.pop(session_id, None)


# ------------------------------------------------------------------ #
#  Module-level singleton — import this everywhere                     #
# ------------------------------------------------------------------ #

history_cache = _SessionHistoryCache()