"""
Real-time progressive TTS generation while streaming LLM response.
"""
import re
import asyncio
import uuid
import base64
from typing import AsyncGenerator, Tuple

# ---- Smallest AI (commented) ----
# from smallestai.waves import AsyncWavesClient
# from config import SMALLEST_API_KEY

from config import SARVAM_API_KEY, SARVAM_TTS_URL, BASE_URL
from services.audio_cache import store_audio
from services.response_cache import get_cached_tts, cache_tts
from services.http_client import get_http_client


async def progressive_tts_generation(
    llm_stream: AsyncGenerator[str, None]
) -> AsyncGenerator[str, None]:
    """
    Generate TTS progressively as LLM streams chunks.
    Yields audio URLs as soon as each sentence is complete.
    
    This enables true real-time response:
    1. LLM streams text chunks
    2. Accumulate until sentence boundary
    3. Generate TTS immediately for that sentence
    4. Yield audio URL (can be played while next generates)
    5. Continue with next sentence
    
    Args:
        llm_stream: Async generator yielding LLM text chunks
        
    Yields:
        Tuple of (audio_url, text) for each completed sentence
    """
    accumulated = ""
    sentence_boundary = re.compile(r'[।?!.]\s*')
    
    async for chunk in llm_stream:
        accumulated += chunk
        
        # Check if we have a sentence boundary
        match = sentence_boundary.search(accumulated)
        
        if match:
            # Extract complete sentence
            sentence = accumulated[:match.end()].strip()
            accumulated = accumulated[match.end():]
            
            if sentence:
                print(f"🎯 Complete sentence: '{sentence}'")
                
                # Generate TTS immediately (don't wait)
                audio_url = await generate_single_tts(sentence)
                
                if audio_url:
                    yield (audio_url, sentence)
    
    # Handle remaining text (incomplete sentence)
    if accumulated.strip():
        print(f"🎯 Final fragment: '{accumulated.strip()}'")
        audio_url = await generate_single_tts(accumulated.strip())
        if audio_url:
            yield (audio_url, accumulated.strip())


async def generate_single_tts(text: str) -> str:
    """
    Generate TTS for a single text segment using Sarvam AI.
    Ultra-optimized for speed with caching.
    
    Args:
        text: Text to convert
        
    Returns:
        Audio URL or None
    """
    import time
    tts_start = time.time()
    
    try:
        # Validate input
        if not text or not text.strip():
            print("⚠️  Empty text provided to TTS, skipping")
            return None
        
        # Check cache first for instant response
        cached_url = await get_cached_tts(text)
        if cached_url:
            cache_time = time.time() - tts_start
            print(f"  ⚡ Cache hit! ({cache_time:.3f}s)")
            return cached_url
        
        # -------------------------------
        # Smallest AI (commented)
        # -------------------------------
        # client = AsyncWavesClient(
        #     api_key=SMALLEST_API_KEY,
        #     model="lightning-v2",
        #     voice_id="shivangi",
        #     language="hi",
        #     sample_rate=8000,
        #     speed=1.3,
        #     output_format="wav"
        # )
        # async with client as tts:
        #     audio_bytes = await tts.synthesize(text)
        
        # -------------------------------
        # Sarvam TTS
        # -------------------------------
        client = get_http_client()
        response = await client.post(
            SARVAM_TTS_URL,
            headers={
                "API-Subscription-Key": SARVAM_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "inputs": [text],
                "target_language_code": "hi-IN",
                "speaker": "ishita",
                "speech_sample_rate": 8000,
                "pace": 1.0,
                "model": "bulbul:v3"
            }
        )
        
        if response.status_code != 200:
            error_text = response.text[:500] if hasattr(response, 'text') else 'No error details'
            print(f"❌ Sarvam TTS error {response.status_code}: {error_text}")
            return None
        
        result = response.json()
        if "audios" not in result or not result["audios"]:
            return None
        
        audio_base64 = result["audios"][0]
        audio_bytes = base64.b64decode(audio_base64)
        
        if audio_bytes:
            # Store with short TTL (only need it for current call)
            audio_id = str(uuid.uuid4())
            await store_audio(audio_id, audio_bytes, ttl_seconds=300)
            audio_url = f"{BASE_URL}/audio-stream/{audio_id}"
            
            # Cache for future use
            cache_tts(text, audio_url)
            
            return audio_url
        
        return None
        
    except Exception as e:
        return None
