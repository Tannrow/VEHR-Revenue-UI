from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0
    expirations: int = 0


@dataclass(frozen=True)
class _CacheEntry(Generic[T]):
    value: T
    inserted_at: float
    expires_at: float


class TtlLruCache(Generic[T]):
    """
    Small in-memory TTL + LRU cache.

    Notes:
    - Per-process only (safe for multi-tenant, but not shared across instances).
    - Intended to smooth bursts for read endpoints and external API calls.
    """

    def __init__(self, *, ttl_seconds: float, maxsize: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        self._default_ttl_seconds = float(ttl_seconds)
        self._maxsize = int(maxsize)
        self._lock = Lock()
        self._entries: OrderedDict[str, _CacheEntry[T]] = OrderedDict()
        self._stats = CacheStats()

    @property
    def stats(self) -> CacheStats:
        # Return a snapshot (do not expose internal counters by reference).
        with self._lock:
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                sets=self._stats.sets,
                evictions=self._stats.evictions,
                expirations=self._stats.expirations,
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _now(self) -> float:
        return time.monotonic()

    def _purge_expired_locked(self, *, now: float) -> None:
        # OrderedDict iteration order is LRU; expired entries are not necessarily first,
        # but purging here keeps memory bounded with minimal overhead.
        expired_keys: list[str] = []
        for key, entry in self._entries.items():
            if entry.expires_at <= now:
                expired_keys.append(key)

        for key in expired_keys:
            self._entries.pop(key, None)
        if expired_keys:
            self._stats.expirations += len(expired_keys)

    def get(self, key: str) -> tuple[T | None, bool]:
        now = self._now()
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                self._stats.misses += 1
                return None, False
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                self._stats.misses += 1
                self._stats.expirations += 1
                return None, False

            # LRU touch.
            self._entries.move_to_end(key)
            self._stats.hits += 1
            return entry.value, True

    def set(self, key: str, value: T, *, ttl_seconds: float | None = None) -> None:
        now = self._now()
        ttl = self._default_ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            return
        expires_at = now + ttl

        with self._lock:
            self._purge_expired_locked(now=now)
            self._entries[key] = _CacheEntry(value=value, inserted_at=now, expires_at=expires_at)
            self._entries.move_to_end(key)
            self._stats.sets += 1

            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
                self._stats.evictions += 1

