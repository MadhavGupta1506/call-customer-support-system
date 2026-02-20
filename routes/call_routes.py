"""
Call-related API routes.
"""
from fastapi import Response, Request
from twilio.twiml.voice_response import VoiceResponse
from services.twilio_service import make_call
from services.sarvam_service import generate_sarvam_tts, transcribe_with_sarvam
from services.llm_service import get_llm_response
from services.conversation_manager import add_message, get_conversation
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

    # Record user's speech with balanced timeout for natural conversation
    response.record(
        action=PROCESS_WEBHOOK,
        method="POST",
        max_length=10,
        timeout=1.5,  # 1.5 seconds of silence gives user time to think
        transcribe=False,
        play_beep=False,
        trim="do-not-trim"
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
        call_sid = form_data.get("CallSid")

        print(f"📞 Recording URL: {recording_url}")
        print(f"📞 CallSid: {call_sid}")

        if not recording_url:
            ai_reply = "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।"
        else:
            # Transcribe using Sarvam STT (optimized - no local download)
            user_text = await transcribe_with_sarvam(recording_url)
            print(f"👤 User said: '{user_text}'")

            if not user_text or not user_text.strip():
                ai_reply = "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।"
            else:
                # Get conversation history for this call
                conversation_history = await get_conversation(call_sid)
                
                # Add user message to history
                await add_message(call_sid, "user", user_text)
                
                # Get LLM response with conversation context
                ai_reply = get_llm_response(user_text, conversation_history)
                print(f"🤖 AI reply: '{ai_reply}'")
                
                # Add assistant message to history
                await add_message(call_sid, "assistant", ai_reply)

        # Clean text
        ai_reply = ai_reply.strip().replace("\n", " ")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        ai_reply = "माफ़ कीजिये, अभी तकनीकी समस्या है।"

    # Generate TTS using Sarvam
    audio_url = await generate_sarvam_tts(ai_reply)
    
    if audio_url:
        response.play(audio_url)

    # Record next input with balanced timeout
    response.record(
        action=PROCESS_WEBHOOK,
        method="POST",
        max_length=10,
        timeout=1.0,  # 1.0 seconds of silence gives user time to think
        transcribe=False,
        play_beep=False,
        trim="do-not-trim"
    )

    return Response(content=str(response), media_type="application/xml")
