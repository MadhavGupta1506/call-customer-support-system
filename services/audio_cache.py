"""
In-memory audio cache to avoid file system operations.
"""
from typing import Dict, Optional
import asyncio

# In-memory cache for audio files
_audio_cache: Dict[str, bytes] = {}

# Lock for thread-safe operations
_cache_lock = asyncio.Lock()


async def store_audio(audio_id: str, audio_data: bytes, ttl_seconds: int = 900):
    """
    Store audio data in memory cache.
    
    Args:
        audio_id: Unique identifier for the audio
        audio_data: Raw audio bytes
        ttl_seconds: Time to live in seconds (default 15 minutes)
    """
    async with _cache_lock:
        _audio_cache[audio_id] = audio_data
    
    # Schedule cleanup after TTL
    asyncio.create_task(_cleanup_after_ttl(audio_id, ttl_seconds))


async def get_audio(audio_id: str) -> Optional[bytes]:
    """
    Retrieve audio data from memory cache.
    
    Args:
        audio_id: Unique identifier for the audio
        
    Returns:
        Audio bytes if found, None otherwise
    """
    async with _cache_lock:
        return _audio_cache.get(audio_id)


async def delete_audio(audio_id: str):
    """
    Delete audio data from memory cache.
    
    Args:
        audio_id: Unique identifier for the audio
    """
    async with _cache_lock:
        _audio_cache.pop(audio_id, None)


async def _cleanup_after_ttl(audio_id: str, ttl_seconds: int):
    """
    Internal function to cleanup audio after TTL expires.
    """
    await asyncio.sleep(ttl_seconds)
    await delete_audio(audio_id)


def get_cache_size() -> int:
    """Get current number of cached audio files."""
    return len(_audio_cache)
