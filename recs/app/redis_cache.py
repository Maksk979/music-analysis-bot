import redis.asyncio as redis
import json
import os
from typing import Optional, Any

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class RedisCache:
    def __init__(self):
        self.client = None
    
    async def init(self):
        self.client = await redis.from_url(REDIS_URL, decode_responses=True)
    
    async def get(self, key: str) -> Optional[Any]:
        if not self.client:
            return None
        data = await self.client.get(key)
        return json.loads(data) if data else None
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        if not self.client:
            return
        await self.client.setex(key, ttl, json.dumps(value))
    
    async def close(self):
        if self.client:
            await self.client.close()

cache = RedisCache()