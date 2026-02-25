"""
FastAPI application for Twilio AI voice assistant.

This is the main entry point of the application that sets up routes
and initializes the FastAPI server.
"""
import asyncio
from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.responses import Response
from routes.call_routes import handle_make_call, handle_voice, handle_voice_stream, handle_process
from services.audio_cache import get_audio
from services.conversation_manager import start_cleanup_task
from services.http_client import close_http_client
from services.media_stream import MediaStreamHandler

# Initialize FastAPI application
app = FastAPI(title="Twilio AI Voice Assistant", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    asyncio.create_task(start_cleanup_task())
    print("✅ Started conversation cleanup background task")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown."""
    await close_http_client()
    print("✅ Closed HTTP client connections")


@app.post("/call")
async def make_call():
    """
    Endpoint to initiate an outbound call.
    """
    return await handle_make_call()


@app.post("/voice")
async def voice(request: Request):
    """
    Webhook endpoint for incoming calls.
    Handles the initial call setup and welcome message.
    """
    return await handle_voice(request)


@app.post("/voice-stream")
async def voice_stream(request: Request):
    """
    Webhook endpoint for incoming calls using Media Streams (WebSocket).
    Ultra-low latency real-time audio processing.
    """
    return await handle_voice_stream(request)


@app.post("/process")
async def process(request: Request):
    """
    Webhook endpoint to process recorded audio.
    Transcribes speech, generates AI response, and plays it back.
    """
    return await handle_process(request)


@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams.
    Receives real-time audio, processes with VAD, and streams back responses.
    """
    handler = MediaStreamHandler()
    await handler.handle_connection(websocket)


@app.get("/audio-stream/{audio_id}")
async def serve_audio(audio_id: str):
    """
    Serve audio from in-memory cache (no file system access).
    """
    audio_data = await get_audio(audio_id)
    
    if audio_data is None:
        raise HTTPException(status_code=404, detail="Audio not found")
    
    return Response(
        content=audio_data,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-cache",
            "Content-Disposition": f"inline; filename={audio_id}.wav"
        }
    )
