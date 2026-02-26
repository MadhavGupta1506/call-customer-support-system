"""
AI service for Text-to-Speech and Speech-to-Text operations.
Now using Sarvam (Smallest AI kept as comments for fallback).
"""
import uuid
import base64
import time
import httpx

# ---- Smallest AI (commented) ----
# from smallestai.waves import AsyncWavesClient
# from config import SMALLEST_API_KEY, SMALLEST_STT_URL

from config import (
    SARVAM_API_KEY,
    SARVAM_TTS_URL,
    SARVAM_STT_URL,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    BASE_URL
)

from services.audio_cache import store_audio
from services.http_client import get_http_client
from services.response_cache import get_cached_tts, cache_tts, should_cache_response


# =========================================================
# TTS
# =========================================================
async def generate_sarvam_tts(text: str) -> str:
    """
    Generate TTS audio using Sarvam.
    (Smallest AI version kept as comments)
    """
    try:
        # Validate input
        if not text or not text.strip():
            print("⚠️  Empty text provided to TTS, skipping")
            return None
        
        cached_url = await get_cached_tts(text)
        if cached_url:
            return cached_url

        client = get_http_client()

        # -------------------------------
        # Smallest AI (commented)
        # -------------------------------
        # client = AsyncWavesClient(
        #     api_key=SMALLEST_API_KEY,
        #     model="lightning-v2",
        #     voice_id="shivangi",
        #     language="hi",
        #     sample_rate=8000,
        #     speed=1.0,
        #     output_format="wav"
        # )
        # async with client as tts:
        #     audio_bytes = await tts.synthesize(text)

        # -------------------------------
        # Sarvam TTS
        # -------------------------------
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
            print("❌ No audio in Sarvam response")
            return None

        audio_base64 = result["audios"][0]
        audio_bytes = base64.b64decode(audio_base64)
        
        print(f"✅ Sarvam TTS: {len(audio_bytes)} bytes, starts with: {audio_bytes[:4]}")

        # Store in memory
        audio_id = str(uuid.uuid4())
        await store_audio(audio_id, audio_bytes, ttl_seconds=900)

        audio_url = f"{BASE_URL}/audio-stream/{audio_id}"

        if should_cache_response(text):
            cache_tts(text, audio_url)

        return audio_url

    except Exception as e:
        print(f"❌ TTS Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


# =========================================================
# STT
# =========================================================
async def transcribe_with_sarvam(audio_bytes: bytes) -> str:
    """
    Transcribe audio using Sarvam STT.
    (Smallest AI version kept as comments)
    """
    try:
        client = get_http_client()

        # -------------------------------
        # Smallest AI (commented)
        # -------------------------------
        # response = await client.post(
        #     SMALLEST_STT_URL,
        #     headers={
        #         "Authorization": f"Bearer {SMALLEST_API_KEY}",
        #         "Content-Type": "application/json"
        #     },
        #     json={
        #         "audio_data": base64.b64encode(audio_bytes).decode("utf-8"),
        #         "language": "hi",
        #         "sample_rate": 16000
        #     }
        # )
        # if response.status_code != 200:
        #     return ""
        # result = response.json()
        # return result.get("transcription", "")

        # -------------------------------
        # Sarvam STT
        # -------------------------------
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav")
        }
        params = {
            "model": "saaras:v2",
            "language_code": "hi-IN"
        }
        response = await client.post(
            SARVAM_STT_URL,
            headers={
                "API-Subscription-Key": SARVAM_API_KEY
            },
            files=files,
            params=params
        )

        if response.status_code != 200:
            error_text = response.text[:500] if hasattr(response, 'text') else 'No error details'
            print(f"❌ Sarvam STT error {response.status_code}: {error_text}")
            return ""

        result = response.json()
        transcription = result.get("transcript", "")
        print(f"🎤 Sarvam STT result: '{transcription}'")
        return transcription

    except Exception as e:
        print(f"❌ STT Exception: {e}")
        import traceback
        traceback.print_exc()
        return ""


async def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """
    Wrapper function for transcribing audio bytes.
    Handles WAV format and calls Sarvam STT.
    """
    try:
        if not audio_bytes or len(audio_bytes) < 44:
            return ""

        # Sarvam STT expects complete WAV file with headers for file upload
        # DO NOT strip headers - keep the complete WAV file
        if audio_bytes[:4] != b'RIFF':
            print("⚠️  Audio is not a valid WAV file")
            return ""

        # Call Sarvam STT with complete WAV file
        transcription = await transcribe_with_sarvam(audio_bytes)

        return transcription

    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return ""
