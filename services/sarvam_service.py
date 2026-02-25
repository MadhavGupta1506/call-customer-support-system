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
            print(f"⚡ Using cached TTS for: '{text[:50]}...'")
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
        
        api_time = time.time() - api_start
        print(f"  ↪ API Call Time: {api_time:.2f}s")
        
        if audio_bytes:
            # Generate unique ID and store in memory cache
            audio_id = str(uuid.uuid4())
            await store_audio(audio_id, audio_bytes, ttl_seconds=900)  # 15 minutes
            
            # Return URL pointing to memory-served endpoint
            audio_url = f"{BASE_URL}/audio-stream/{audio_id}"
            # print(f"✅ TTS Generated (in-memory): {audio_url}")
            
            # Cache common responses for faster future access
            if should_cache_response(text):
                cache_tts(text, audio_url)
            
            return audio_url
        else:
            print(f"❌ TTS Error: No audio generated")
            return None
    except Exception as e:
        print(f"❌ TTS Exception: {str(e)}")
        import traceback
        traceback.print_exc()
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
        download_start = time.time()
        async with client.stream(
            'GET',
            download_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        ) as audio_stream:
            
            if audio_stream.status_code != 200:
                print(f"❌ Failed to access recording: {audio_stream.status_code}")
                return ""
            
            # Collect audio chunks in memory
            audio_chunks = []
            async for chunk in audio_stream.aiter_bytes():
                audio_chunks.append(chunk)
            
            audio_data = b''.join(audio_chunks)
        
        download_time = time.time() - download_start
        print(f"  ↪ Download Time: {download_time:.2f}s ({len(audio_data)} bytes)")
        
        # Send to Smallest AI STT
        # print(f"🔊 Forwarding to Smallest AI STT...")
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
        stt_time = time.time() - stt_start
        print(f"  ↪ API Call Time: {stt_time:.2f}s")
        
        if stt_response.status_code == 200:
            result = stt_response.json()
            transcript = result.get("transcription", "")
            # print(f"✅ STT Transcript: '{transcript}'")
            return transcript
        else:
            print(f"❌ STT Error: {stt_response.status_code} - {stt_response.text}")
            return ""
    except Exception as e:
        print(f"❌ STT Exception: {str(e)}")
        import traceback
        traceback.print_exc()
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
            content=audio_bytes
        )
        stt_time = time.time() - stt_start
        print(f"  ↪ STT API Time: {stt_time:.2f}s")
        
        if stt_response.status_code == 200:
            result = stt_response.json()
            transcript = result.get("transcription", "")
            return transcript
        else:
            print(f"❌ STT Error: {stt_response.status_code} - {stt_response.text}")
            return ""
    except Exception as e:
        print(f"❌ STT Exception: {str(e)}")
        return ""
