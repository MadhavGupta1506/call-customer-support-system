"""
FastAPI application for Twilio AI voice assistant.

This is the main entry point of the application that sets up routes
and initializes the FastAPI server.
"""
from fastapi import FastAPI, Request
from routes.call_routes import handle_make_call, handle_voice, handle_process

# Initialize FastAPI application
app = FastAPI(title="Twilio AI Voice Assistant", version="1.0.0")


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


@app.post("/process")
async def process(request: Request):
    """
    Webhook endpoint to process recorded audio.
    Transcribes speech, generates AI response, and plays it back.
    """
    return await handle_process(request)
