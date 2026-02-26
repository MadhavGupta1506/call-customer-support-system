"""
Smallest AI service for Text-to-Speech and Speech-to-Text operations.
"""
import uuid
import time
from smallestai.waves import AsyncWavesClient
from config import SMALLEST_API_KEY, SMALLEST_STT_URL, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, BASE_URL
from services.audio_cache import store_audio
from services.http_client import get_http_client
from services.response_cache import get_cached_tts, cache_tts, should_cache_response


async def generate_sarvam_tts(text: str) -> str:
    """
    Generate TTS audio using Smallest AI API.
    
    Args:
        text: The text to convert to speech
        
    Returns:
        Audio URL if successful, None otherwise
    """
    try:
        # Check cache first for instant response (validates audio still exists)
        cached_url = await get_cached_tts(text)
        if cached_url:
            return cached_url
        
        # print(f"🔊 Generating TTS for: '{text[:50]}...'")
        
        api_start = time.time()
        
        # Use Smallest AI async client for TTS
        # lightning-v2: General multilingual model (doesn't use voice_id)
        # Set voice_id=None to disable voice cloning
        client = AsyncWavesClient(
            api_key=SMALLEST_API_KEY,
            model="lightning-v2",
            voice_id="shivangi",  # Disable voice cloning for multilingual model
            language="hi",  # Auto-detect language (supports Hindi)
            sample_rate=8000,
            speed=1.0,
            output_format="wav"
        )
        async with client as tts:
            audio_bytes = await tts.synthesize(text)
        
        if audio_bytes:
            # Validate it's a proper WAV file
            if not audio_bytes.startswith(b'RIFF'):
                return None
            
            # Generate unique ID and store in memory cache
            audio_id = str(uuid.uuid4())
            await store_audio(audio_id, audio_bytes, ttl_seconds=900)  # 15 minutes
            
            # Return URL pointing to memory-served endpoint
            audio_url = f"{BASE_URL}/audio-stream/{audio_id}"
            
            # Cache common responses for faster future access
            if should_cache_response(text):
                cache_tts(text, audio_url)
            
            return audio_url
        else:
            return None
    except Exception as e:
        return None


async def transcribe_with_sarvam(recording_url: str) -> str:
    """
    Transcribe audio using Smallest AI STT API - streams directly without local storage.
    
    Args:
        recording_url: The URL of the Twilio recording
        
    Returns:
        Transcribed text if successful, empty string otherwise
    """
    try:
        client = get_http_client()
        
        # Stream audio from Twilio
        download_url = recording_url + ".wav"
        print(f"🎤 Streaming from: {download_url}")
        
        # Download audio from Twilio
        async with client.stream(
            'GET',
            download_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        ) as audio_stream:
            
            if audio_stream.status_code != 200:
                return ""
            
            # Collect audio chunks in memory
            audio_chunks = []
            async for chunk in audio_stream.aiter_bytes():
                audio_chunks.append(chunk)
            
            audio_data = b''.join(audio_chunks)
        
        # Send to Smallest AI STT
        stt_start = time.time()
        stt_response = await client.post(
            SMALLEST_STT_URL,
            params={
                "model": "pulse",
                "language": "hi"  # Hindi language code
            },
            headers={
                "Authorization": f"Bearer {SMALLEST_API_KEY}",
                "Content-Type": "audio/wav"
            },
            content=audio_data
        )
        if stt_response.status_code == 200:
            result = stt_response.json()
            transcript = result.get("transcription", "")
            return transcript
        else:
            return ""
    except Exception as e:
        return ""


async def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """
    Transcribe audio bytes directly using Smallest AI STT API.
    Used for WebSocket media streams with in-memory audio.
    
    Args:
        audio_bytes: Raw audio bytes (WAV format)
        
    Returns:
        Transcribed text if successful, empty string otherwise
    """
    try:
        client = get_http_client()
        
        # Send to Smallest AI STT
        stt_start = time.time()
        
        # Try with auto language detection first
        stt_response = await client.post(
            SMALLEST_STT_URL,
            params={
                "model": "pulse",
                "language": "hi"              },
            headers={
                "Authorization": f"Bearer {SMALLEST_API_KEY}",
                "Content-Type": "audio/wav"
            },
            content=audio_bytes
        )
        
        print(f"📡 STT Response: {stt_response.status_code}")
        
        if stt_response.status_code == 200:
            result = stt_response.json()
            print(f"📝 STT Result: {result}")
            transcript = result.get("transcription", "")
            
            # Check if transcription is in a different field
            if not transcript:
                transcript = result.get("text", result.get("transcript", ""))
            
            return transcript
        else:
            print(f"❌ STT failed: {stt_response.text[:200]}")
            return ""
    except Exception as e:
        print(f"❌ STT Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return ""
