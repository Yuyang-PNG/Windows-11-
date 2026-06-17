import threading
import time
from typing import Dict, Tuple, Any, Optional


class TTLCache:
    """线程安全的TTL缓存"""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                return None
            data, timestamp = self._cache[key]
            if self._is_expired(timestamp):
                del self._cache[key]
                return None
            return data

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = (value, self._get_timestamp())

    def invalidate(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def _is_expired(self, timestamp: float) -> bool:
        return self._get_timestamp() - timestamp > self._ttl

    @staticmethod
    def _get_timestamp() -> float:
        return time.time()

    def clear(self) -> None:
        """清空所有缓存"""
        self.invalidate()
