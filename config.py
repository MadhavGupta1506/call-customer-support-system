"""
Configuration module for managing environment variables and API settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = "+15822284439"
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER")

# Groq configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
# Smallest AI configuration (TTS and STT)
SMALLEST_API_KEY = os.getenv("SMALLEST_API_KEY")
SMALLEST_STT_URL = "https://waves-api.smallest.ai/api/v1/pulse/get_text"

# Webhook URLs (update with your ngrok URL)
BASE_URL = "https://retrorse-miracle-grenadierial.ngrok-free.dev"
VOICE_WEBHOOK = f"{BASE_URL}/voice-stream"
PROCESS_WEBHOOK = f"{BASE_URL}/process"
