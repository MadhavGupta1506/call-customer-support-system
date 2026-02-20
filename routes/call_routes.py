"""
Call-related API routes.
"""
from fastapi import Response, Request
from twilio.twiml.voice_response import VoiceResponse
from services.twilio_service import make_call
from services.sarvam_service import generate_sarvam_tts, transcribe_with_sarvam
from services.llm_service import get_llm_response
from config import PROCESS_WEBHOOK


async def handle_make_call():
    """
    Endpoint to initiate an outbound call.
    """
    return make_call()


async def handle_voice(request: Request):
    """
    Webhook handler for incoming call - plays welcome message and starts recording.
    """
    response = VoiceResponse()

    # Generate welcome message using Sarvam TTS
    welcome_text = "नमस्ते, मैं आपका AI सहायक हूँ। कृपया कुछ बोलिए।"
    audio_url = await generate_sarvam_tts(welcome_text)
    
    if audio_url:
        response.play(audio_url)
    else:
        # Fallback to Twilio TTS
        response.say(welcome_text, voice="Polly.Aditi", language="hi-IN")

    # Record user's speech
    response.record(
        action=PROCESS_WEBHOOK,
        method="POST",
        max_length=10,
        timeout=3,
        transcribe=False,
        play_beep=False
    )

    return Response(content=str(response), media_type="application/xml")


async def handle_process(request: Request):
    """
    Webhook handler to process recorded audio, transcribe, get AI response, and play it back.
    """
    response = VoiceResponse()

    try:
        form_data = await request.form()
        recording_url = form_data.get("RecordingUrl")

        print("Recording URL:", recording_url)

        if not recording_url:
            ai_reply = "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।"
        else:
            # Transcribe using Sarvam STT
            user_text = await transcribe_with_sarvam(recording_url)
            print("User said:", user_text)

            if not user_text:
                ai_reply = "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।"
            else:
                ai_reply = get_llm_response(user_text)
                print("AI reply:", ai_reply)

        # Clean text
        ai_reply = ai_reply.strip().replace("\n", " ")
        ai_reply = ai_reply[:250]

    except Exception as e:
        print("Error:", str(e))
        ai_reply = "माफ़ कीजिये, अभी तकनीकी समस्या है।"

    # Generate TTS using Sarvam
    audio_url = await generate_sarvam_tts(ai_reply)
    
    if audio_url:
        response.play(audio_url)
    else:
        # Fallback to Twilio TTS
        response.say(ai_reply, voice="Polly.Aditi", language="hi-IN")

    # Record next input
    response.record(
        action=PROCESS_WEBHOOK,
        method="POST",
        max_length=10,
        timeout=3,
        transcribe=False,
        play_beep=False
    )

    return Response(content=str(response), media_type="application/xml")
