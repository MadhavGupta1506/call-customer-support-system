"""
Twilio service for handling phone call operations.
"""
from twilio.rest import Client
from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER, VOICE_WEBHOOK

# Initialize Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def make_call(to_number: str = None, from_number: str = None) -> dict:
    """
    Initiate an outbound phone call using Twilio.
    
    Args:
        to_number: The phone number to call (defaults to configured number)
        from_number: The Twilio number to call from (defaults to configured number)
        
    Returns:
        Dictionary with call information
    """
    call = client.calls.create(
        url=VOICE_WEBHOOK,
        to=to_number or TWILIO_TO_NUMBER,
        from_=from_number or TWILIO_FROM_NUMBER,
    )
    
    return {
        "message": "Call initiated",
        "call_sid": call.sid
    }
