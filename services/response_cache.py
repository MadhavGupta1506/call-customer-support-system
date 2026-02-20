"""
Response cache for common phrases to reduce latency.
"""
from typing import Dict, Optional
import hashlib

# Pre-generated TTS audio URLs for common responses
_tts_cache: Dict[str, str] = {}

# Common responses that can be cached
COMMON_RESPONSES = {
    "no_audio_hindi": "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।",
    "technical_error_hindi": "माफ़ कीजिये, अभी तकनीकी समस्या है।",
    "greeting_hindi": "नमस्ते, मैं आपका AI सहायक हूँ। कृपया कुछ बोलिए।",
}


def get_response_hash(text: str) -> str:
    """Generate hash for response text."""
    return hashlib.md5(text.encode()).hexdigest()


def get_cached_tts(text: str) -> Optional[str]:
    """
    Get cached TTS audio URL for common phrases.
    
    Args:
        text: The text to check for cached audio
        
    Returns:
        Cached audio URL if found, None otherwise
    """
    text_hash = get_response_hash(text.strip().lower())
    return _tts_cache.get(text_hash)


def cache_tts(text: str, audio_url: str):
    """
    Cache TTS audio URL for reuse.
    
    Args:
        text: The response text
        audio_url: The generated audio URL
    """
    text_hash = get_response_hash(text.strip().lower())
    _tts_cache[text_hash] = audio_url
    print(f"💾 Cached TTS for: '{text[:30]}...'")


def should_cache_response(text: str) -> bool:
    """
    Determine if a response should be cached.
    Common phrases or error messages should be cached.
    """
    text_lower = text.strip().lower()
    
    # Check if it's a common response
    for common_text in COMMON_RESPONSES.values():
        if text_lower == common_text.lower():
            return True
    
    # Cache error messages and short responses
    if any(keyword in text_lower for keyword in ["माफ़", "सुनी नहीं", "नमस्ते", "धन्यवाद"]):
        return True
    
    return False


def get_cache_size() -> int:
    """Get number of cached responses."""
    return len(_tts_cache)
