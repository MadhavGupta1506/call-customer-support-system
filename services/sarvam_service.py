"""
Sarvam AI service for Text-to-Speech and Speech-to-Text operations.
"""
import httpx
import base64
from config import SARVAM_API_KEY, SARVAM_TTS_URL, SARVAM_STT_URL, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN


async def generate_sarvam_tts(text: str) -> str:
    """
    Generate speech from text using Sarvam TTS API.
    
    Args:
        text: The text to convert to speech
        
    Returns:
        Audio URL if successful, None otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                SARVAM_TTS_URL,
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "inputs": [text],
                    "target_language_code": "hi-IN",
                    "speaker": "anushka",
                    "pitch": 0,
                    "pace": 1.0,
                    "loudness": 1.5,
                    "speech_sample_rate": 8000,
                    "enable_preprocessing": True,
                    "model": "bulbul:v1"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                if "audios" in result and len(result["audios"]) > 0:
                    audio_base64 = result["audios"][0]
                    print("TTS Generated successfully")
                    return None  # Will use fallback for now
            else:
                print(f"TTS Error: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        print(f"TTS Exception: {str(e)}")
        return None


async def transcribe_with_sarvam(recording_url: str) -> str:
    """
    Transcribe audio using Sarvam STT API.
    
    Args:
        recording_url: The URL of the Twilio recording
        
    Returns:
        Transcribed text if successful, empty string otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Download the recording from Twilio
            audio_response = await client.get(
                recording_url + ".mp3",
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            )
            
            if audio_response.status_code != 200:
                print(f"Failed to download recording: {audio_response.status_code}")
                return ""
            
            audio_data = audio_response.content
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Send to Sarvam STT
            stt_response = await client.post(
                SARVAM_STT_URL,
                headers={
                    "API-Subscription-Key": SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "audio": audio_base64,
                    "language_code": "hi-IN",
                    "model": "saaras:v1"
                }
            )
            
            if stt_response.status_code == 200:
                result = stt_response.json()
                transcript = result.get("transcript", "")
                print(f"STT Transcript: {transcript}")
                return transcript
            else:
                print(f"STT Error: {stt_response.status_code} - {stt_response.text}")
                return ""
    except Exception as e:
        print(f"STT Exception: {str(e)}")
        return ""
