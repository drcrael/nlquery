"""Small per-client caches with monotonic expiration and explicit invalidation."""

from time import monotonic
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float, max_entries: int = 128) -> None:
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._entries: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        item = self._entries.get(key)
        if item is None:
            return None
        if monotonic() >= item[0]:
            del self._entries[key]
            return None
        return item[1]

    def put(self, key: str, value: T) -> None:
        if len(self._entries) >= self.max_entries:
            del self._entries[next(iter(self._entries))]
        self._entries[key] = (monotonic() + self.ttl, value)

    def invalidate(self) -> None:
        self._entries.clear()
