from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import redis
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Cache Service", version="1.0.0")

# Connecting to Redis
REDIS_URL = os.getenv("REDIS_URL", "")
redis_client = redis.from_url(REDIS_URL, decode_responses=False)

class CacheSetRequest(BaseModel):
    key: str
    value: Any
    ttl: int = 3600  # Life time in seconds (consort 1 hour)

class CacheGetResponse(BaseModel):
    cached: bool
    value: Optional[Any] = None

@app.post("/cache/set")
async def set_cache(request: CacheSetRequest):
    'Cache setting'
    try:
        # Serialize the value in JSON
        value_json = json.dumps(request.value, ensure_ascii=False)
        
        # Save at Redis
        redis_client.setex(
            request.key,
            request.ttl,
            value_json.encode('utf-8')
        )
        
        return {
            "status": "success",
            "key": request.key,
            "ttl": request.ttl
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cache/get")
async def get_cache(key: str):
    'Capture value from cache'
    try:
        value_bytes = redis_client.get(key)
        
        if value_bytes is None:
            return {
                "cached": False,
                "value": None
            }
        
        # Desery from JSON
        value_json = value_bytes.decode('utf-8')
        value = json.loads(value_json)
        
        return {
            "cached": True,
            "value": value
        }
    except json.JSONDecodeError:
        # If we can't unpack, we'll return as we are.
        return {
            "cached": True,
            "value": value_bytes.decode('utf-8') if value_bytes else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/cache/delete/{key}")
async def delete_cache(key: str):
    'Remove value from cache'
    try:
        deleted = redis_client.delete(key)
        return {
            "status": "success",
            "deleted": bool(deleted)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cache/clear")
async def clear_cache():
    'Cleaning All Cash'
    try:
        redis_client.flushdb()
        return {
            "status": "success",
            "message": "Cache cleared"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    'Service health check'
    try:
        redis_client.ping()
        return {"status": "healthy", "service": "cache_service"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
