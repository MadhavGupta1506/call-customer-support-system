"""
Call-related API routes.
"""
import time
import asyncio
from fastapi import Response, Request
from twilio.twiml.voice_response import VoiceResponse
from services.twilio_service import make_call
from services.sarvam_service import generate_sarvam_tts, transcribe_with_sarvam
from services.llm_service import stream_llm_response
from services.realtime_tts import progressive_tts_generation
from services.conversation_manager import add_message, get_conversation
from config import PROCESS_WEBHOOK, BASE_URL


async def handle_make_call():
    """
    Endpoint to initiate an outbound call.
    """
    return make_call()


async def handle_voice_stream(request: Request):
    """
    Webhook handler for incoming call - WebSocket-based streaming (ULTRA-LOW LATENCY).
    Uses Twilio Media Streams for bidirectional real-time audio.
    """
    response = VoiceResponse()
    
    # Start bidirectional media streaming first
    connect = response.connect()
    connect.stream(
        url=f"wss://{BASE_URL.replace('https://', '').replace('http://', '')}/media-stream"
    )
    
    # Keep the call alive for 60 seconds (adjust as needed)
    response.pause(length=60)
    

    return Response(content=str(response), media_type="application/xml")


async def handle_voice(request: Request):
    """
    Webhook handler for incoming call - plays welcome message and starts recording.
    """
    start_time = time.time()
    response = VoiceResponse()

    # Generate welcome message using Smallest AI TTS
    welcome_text = "नमस्ते, मैं आपका AI सहायक हूँ। कृपया कुछ बोलिए।"
    audio_url = await generate_sarvam_tts(welcome_text)
    
    if audio_url:
        response.play(audio_url)

    # Record user's speech with aggressive timeout for immediate processing
    response.record(
        action=PROCESS_WEBHOOK,
        method="POST",
        max_length=10,
        timeout=1,  # Stop recording 1 sec after user stops speaking
        transcribe=False,
        play_beep=False,
        trim="do-not-trim"
    )

    total_time = time.time() - start_time
    print(f"⏱️  Initial Greeting Time: {total_time:.2f}s")
    print("─" * 50)

    return Response(content=str(response), media_type="application/xml")


async def handle_process(request: Request):
    """
    Webhook handler to process recorded audio, transcribe, get AI response, and play it back.
    """
    webhook_received_time = time.time()
    print(f"\n🔴 Recording stopped - Webhook received at: {time.strftime('%H:%M:%S', time.localtime(webhook_received_time))}.{int((webhook_received_time % 1) * 1000):03d}")
    
    start_time = time.time()
    response = VoiceResponse()

    try:
        form_data = await request.form()
        recording_url = form_data.get("RecordingUrl")
        call_sid = form_data.get("CallSid")

        print(f"📞 Recording URL: {recording_url}")
        print(f"📞 CallSid: {call_sid}")

        ai_audio_urls = None  # Initialize
        
        if not recording_url:
            ai_reply = "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।"
        else:
            # PARALLEL PROCESSING: Start STT and fetch conversation history simultaneously
            stt_start = time.time()
            print(f"⚡ Starting parallel STT + conversation fetch...")
            user_text, conversation_history = await asyncio.gather(
                transcribe_with_sarvam(recording_url),
                get_conversation(call_sid),
                return_exceptions=True
            )
            
            # Handle any exceptions from parallel tasks
            if isinstance(user_text, Exception):
                print(f"❌ STT Error: {user_text}")
                user_text = ""
            if isinstance(conversation_history, Exception):
                print(f"❌ Conversation fetch error: {conversation_history}")
                conversation_history = []
            
            stt_time = time.time() - stt_start
            print(f"👤 User said: '{user_text}'")
            print(f"⏱️  STT + Context Fetch (parallel): {stt_time:.2f}s")

            if not user_text or not user_text.strip():
                ai_reply = "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।"
                ai_audio_urls = None
            else:
                # REAL-TIME PROGRESSIVE STREAMING
                # LLM streams → Generate TTS per sentence → Play ASAP
                llm_start = time.time()
                print(f"🚀 Starting real-time progressive streaming...")
                
                # Save user message (fire and forget)
                asyncio.create_task(add_message(call_sid, "user", user_text))
                
                # Progressive TTS generation as LLM streams
                ai_audio_urls = []
                ai_reply = ""
                
                llm_stream = stream_llm_response(user_text, conversation_history)
                
                async for audio_url, sentence_text in progressive_tts_generation(llm_stream):
                    ai_reply += sentence_text + " "
                    ai_audio_urls.append(audio_url)
                    print(f"🎵 Audio ready ({len(ai_audio_urls)}): '{sentence_text[:40]}...'")
                
                llm_time = time.time() - llm_start
                ai_reply = ai_reply.strip()
                print(f"🤖 Complete reply: '{ai_reply}'")
                print(f"⏱️  Total Stream+TTS Time: {llm_time:.2f}s")
                print(f"🎵 Generated {len(ai_audio_urls)} audio segments")
                
                # Save assistant message (fire and forget)
                asyncio.create_task(add_message(call_sid, "assistant", ai_reply))

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        ai_reply = "माफ़ कीजिये, अभी तकनीकी समस्या है।"
        ai_audio_urls = None

    # PLAY AUDIO CHUNKS (or fallback to single TTS)
    if ai_audio_urls and len(ai_audio_urls) > 0:
        # Play all chunks sequentially
        for audio_url in ai_audio_urls:
            response.play(audio_url)
    else:
        # Fallback: generate single TTS synchronously
        tts_start = time.time()
        ai_reply = ai_reply.strip().replace("\n", " ")
        audio_url = await generate_sarvam_tts(ai_reply)
        
        tts_time = time.time() - tts_start
        print(f"⏱️  Fallback TTS Time: {tts_time:.2f}s")
        
        if audio_url:
            response.play(audio_url)

    # Record next input with aggressive timeout for real-time feel
    response.record(
        action=PROCESS_WEBHOOK,
        method="POST",
        max_length=10,
        timeout=1.2,  # Stop recording 1 sec after user stops speaking
        transcribe=False,
        play_beep=False,
        trim="do-not-trim"
    )

    total_time = time.time() - start_time
    print(f"⏱️  Total Processing Time: {total_time:.2f}s")
    print("─" * 50)

    return Response(content=str(response), media_type="application/xml")
