"""
Redis caching layer with in-memory fallback when Redis is unavailable.
"""
from config import REDIS_URL, CATALOG_CACHE_TTL, BOOK_LOCK_TTL
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import time

# In-memory fallback storage with async support
class MemoryCache:
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}

    async def get(self, key):
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._data[key]
            del self._expiry[key]
            return None
        return self._data.get(key)

    async def setex(self, key, ttl, value):
        self._data[key] = value
        self._expiry[key] = time.time() + ttl

    async def setnx(self, key, value):
        if key in self._expiry and time.time() > self._expiry[key]:
            del self._data[key]
            del self._expiry[key]
        if key not in self._data:
            self._data[key] = value
            return True
        return False

    async def expire(self, key, ttl):
        if key in self._data:
            self._expiry[key] = time.time() + ttl
        return True

    async def delete(self, key):
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    async def zincrby(self, key, increment, member):
        if key not in self._data:
            self._data[key] = {}
        if member not in self._data[key]:
            self._data[key][member] = 0
        self._data[key][member] += increment

    async def zrevrange(self, key, start, stop, withscores=False):
        if key not in self._data:
            return []
        sorted_items = sorted(self._data[key].items(), key=lambda x: x[1], reverse=True)
        if stop >= 0:
            items = sorted_items[start:stop+1]
        else:
            items = sorted_items[start:]
        if withscores:
            return [(m, s) for m, s in items]
        return [m for m, s in items]


memory_cache = MemoryCache()

# Global Redis client
redis_client = None


async def get_redis():
    """Get Redis connection or MemoryCache fallback."""
    global redis_client
    
    # If we already have a client, test it
    if redis_client is not None:
        try:
            await redis_client.ping()
            return redis_client
        except Exception:
            redis_client = None
    
    # Try to connect to Redis
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        return redis_client
    except Exception:
        return memory_cache


async def close_redis():
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
        except Exception:
            pass
        redis_client = None


# --- Catalog Cache ---

async def get_cached_catalog() -> Optional[List[Dict[str, Any]]]:
    r = await get_redis()
    data = await r.get("catalog:books")
    if data:
        if isinstance(data, str):
            return json.loads(data)
        return data
    return None


async def set_cached_catalog(books: List[Dict[str, Any]]):
    r = await get_redis()
    serialized = json.dumps(books, ensure_ascii=False)
    await r.setex("catalog:books", CATALOG_CACHE_TTL, serialized)


async def invalidate_catalog_cache():
    r = await get_redis()
    await r.delete("catalog:books")


# --- Book Locking ---

async def acquire_book_lock(book_id: int, user: str) -> bool:
    r = await get_redis()
    locked = await r.setnx(f"book_lock:{book_id}", user)
    if locked:
        await r.expire(f"book_lock:{book_id}", BOOK_LOCK_TTL)
    return locked


async def release_book_lock(book_id: int):
    r = await get_redis()
    await r.delete(f"book_lock:{book_id}")


# --- Temporary Reservations ---

async def create_temp_reservation(book_id: int, user: str, quantity: int):
    r = await get_redis()
    key = f"temp_reservation:{book_id}:{user}"
    data = {"book_id": book_id, "user": user, "quantity": quantity}
    await r.setex(key, BOOK_LOCK_TTL, json.dumps(data))


async def delete_temp_reservation(book_id: int, user: str):
    r = await get_redis()
    key = f"temp_reservation:{book_id}:{user}"
    await r.delete(key)


# --- View Counter (Popular Books) ---

async def increment_view(book_id: int):
    r = await get_redis()
    today_key = f"views:daily:{datetime.now().strftime('%Y-%m-%d')}"
    await r.zincrby(today_key, 1, str(book_id))
    await r.expire(today_key, 86400 * 7)


async def get_top_books(limit: int = 10) -> List[Dict]:
    r = await get_redis()
    today_key = f"views:daily:{datetime.now().strftime('%Y-%m-%d')}"
    results = await r.zrevrange(today_key, 0, limit - 1, withscores=True)
    books = []
    for book_id_str, score in results:
        books.append({"book_id": int(book_id_str), "views": int(score)})
    return books


# --- Admin Sessions ---

async def create_admin_session(session_id: str):
    r = await get_redis()
    await r.setex(f"admin_session:{session_id}", 3600, "active")


async def check_admin_session(session_id: str) -> bool:
    r = await get_redis()
    result = await r.get(f"admin_session:{session_id}")
    if result:
        await r.expire(f"admin_session:{session_id}", 3600)
        return True
    return False


async def delete_admin_session(session_id: str):
    r = await get_redis()
    await r.delete(f"admin_session:{session_id}")