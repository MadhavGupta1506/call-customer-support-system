"""
Sarvam AI service for Text-to-Speech and Speech-to-Text operations.
"""
import base64
import uuid
from config import SARVAM_API_KEY, SARVAM_TTS_URL, SARVAM_STT_URL, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, BASE_URL
from services.audio_cache import store_audio
from services.http_client import get_http_client
from services.response_cache import get_cached_tts, cache_tts, should_cache_response


async def generate_sarvam_tts(text: str) -> str:
    """
    Generate speech from text using Sarvam TTS API (no file operations).
    Uses cache for common responses.
    
    Args:
        text: The text to convert to speech
        
    Returns:
        Audio URL if successful, None otherwise
    """
    try:
        # Check cache first for instant response
        cached_url = get_cached_tts(text)
        if cached_url:
            print(f"⚡ Using cached TTS for: '{text[:50]}...'")
            return cached_url
        
        print(f"🔊 Generating TTS for: '{text[:50]}...'")
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
                "speaker": "simran",
                "pace": 1.05,
                "speech_sample_rate": 8000,
                "enable_preprocessing": False,
                "model": "bulbul:v3"
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            if "audios" in result and len(result["audios"]) > 0:
                audio_base64 = result["audios"][0]
                
                # Decode base64 audio (keep in memory only)
                audio_bytes = base64.b64decode(audio_base64)
                
                # Generate unique ID and store in memory cache
                audio_id = str(uuid.uuid4())
                await store_audio(audio_id, audio_bytes, ttl_seconds=300)
                
                # Return URL pointing to memory-served endpoint
                audio_url = f"{BASE_URL}/audio-stream/{audio_id}"
                print(f"✅ TTS Generated (in-memory): {audio_url}")
                
                # Cache common responses for faster future access
                if should_cache_response(text):
                    cache_tts(text, audio_url)
                
                return audio_url
        else:
            print(f"❌ TTS Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ TTS Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


async def transcribe_with_sarvam(recording_url: str) -> str:
    """
    Transcribe audio using Sarvam STT API - streams directly without local storage.
    
    Args:
        recording_url: The URL of the Twilio recording
        
    Returns:
        Transcribed text if successful, empty string otherwise
    """
    try:
        client = get_http_client()
        
        # Stream audio from Twilio directly to Sarvam STT without downloading
        download_url = recording_url + ".wav"
        print(f"🎤 Streaming from: {download_url}")
        
        # Stream the audio and forward directly to Sarvam
        async with client.stream(
            'GET',
            download_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        ) as audio_stream:
            
            if audio_stream.status_code != 200:
                print(f"❌ Failed to access recording: {audio_stream.status_code}")
                return ""
            
            # Collect audio chunks in memory (not disk)
            audio_chunks = []
            async for chunk in audio_stream.aiter_bytes():
                audio_chunks.append(chunk)
            
            audio_data = b''.join(audio_chunks)
            print(f"✅ Streamed {len(audio_data)} bytes")
        
        # Send to Sarvam STT using multipart/form-data (in memory only)
        files = {
            'file': ('audio.wav', audio_data, 'audio/wav')
        }
        data = {
            'language_code': 'hi-IN',
            'model': 'saaras:v3'
        }
        
        print(f"🔊 Forwarding to Sarvam STT...")
        stt_response = await client.post(
            SARVAM_STT_URL,
            headers={
                "API-Subscription-Key": SARVAM_API_KEY
            },
            files=files,
            data=data
        )
        
        if stt_response.status_code == 200:
            result = stt_response.json()
            transcript = result.get("transcript", "")
            print(f"✅ STT Transcript: '{transcript}'")
            return transcript
        else:
            print(f"❌ STT Error: {stt_response.status_code} - {stt_response.text}")
            return ""
    except Exception as e:
        print(f"❌ STT Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return ""
