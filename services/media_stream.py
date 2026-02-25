"""
WebSocket handler for Twilio Media Streams.
Real-time bidirectional audio streaming.
"""
import json
import base64
import asyncio
import time
import audioop
from fastapi import WebSocket, WebSocketDisconnect
from services.vad_service import VoiceActivityDetector
from services.sarvam_service import transcribe_audio_bytes
from services.llm_service import stream_llm_response
from services.realtime_tts import progressive_tts_generation
from services.conversation_manager import add_message, get_conversation
from services.http_client import get_http_client


class MediaStreamHandler:
    """
    Handles Twilio Media Stream WebSocket connections.
    Receives audio in real-time, detects speech end, processes, and sends back audio.
    """
    
    def __init__(self):
        self.vad = VoiceActivityDetector(aggressiveness=3, sample_rate=8000, frame_duration_ms=20)
        self.audio_buffer = bytearray()
        self.stream_sid = None
        self.call_sid = None
        self.is_processing = False
        
    async def handle_connection(self, websocket: WebSocket):
        """
        Main WebSocket connection handler.
        """
        await websocket.accept()
        print("🔌 WebSocket Connected")
        
        try:
            async for message in websocket.iter_text():
                await self.process_message(websocket, message)
        
        except WebSocketDisconnect:
            print("🔌 WebSocket Disconnected")
        except Exception as e:
            print(f"❌ WebSocket Error: {e}")
            import traceback
            traceback.print_exc()
    
    async def process_message(self, websocket: WebSocket, message: str):
        """
        Process incoming WebSocket message from Twilio.
        """
        try:
            data = json.loads(message)
            event_type = data.get('event')
            
            if event_type == 'start':
                await self.handle_start(data)
            
            elif event_type == 'media':
                await self.handle_media(websocket, data)
            
            elif event_type == 'stop':
                await self.handle_stop()
        
        except Exception as e:
            print(f"❌ Message processing error: {e}")
    
    async def handle_start(self, data):
        """
        Handle stream start event.
        """
        self.stream_sid = data['streamSid']
        self.call_sid = data['start']['callSid']
        print(f"📡 Stream Started - CallSid: {self.call_sid}")
        print(f"📡 StreamSid: {self.stream_sid}")
        
        # Reset state
        self.audio_buffer = bytearray()
        self.vad.reset()
        self.is_processing = False
    
    async def handle_media(self, websocket: WebSocket, data):
        """
        Handle incoming audio media packets.
        """
        # Don't process audio while we're already processing a response
        if self.is_processing:
            return
        
        # Extract audio payload (base64 encoded μ-law)
        payload = data['media']['payload']
        audio_chunk = base64.b64decode(payload)
        
        # Convert μ-law to linear PCM (16-bit)
        pcm_audio = audioop.ulaw2lin(audio_chunk, 2)
        
        # Add to buffer
        self.audio_buffer.extend(pcm_audio)
        
        # Process with VAD (20ms frames = 320 bytes at 8kHz 16-bit)
        frame_size = 320
        if len(pcm_audio) >= frame_size:
            frame = pcm_audio[:frame_size]
            vad_result = self.vad.process_frame(frame)
            
            # If speech just ended, process the accumulated audio
            if vad_result['speech_ended'] and len(self.audio_buffer) > 8000:  # At least 0.5s of audio
                print(f"🎤 Speech detected - Processing {len(self.audio_buffer)} bytes")
                asyncio.create_task(self.process_audio(websocket, bytes(self.audio_buffer)))
                
                # Clear buffer and mark as processing
                self.audio_buffer = bytearray()
                self.is_processing = True
                self.vad.reset()
    
    async def handle_stop(self):
        """
        Handle stream stop event.
        """
        print(f"📡 Stream Stopped - CallSid: {self.call_sid}")
    
    async def process_audio(self, websocket: WebSocket, audio_bytes: bytes):
        """
        Process complete user audio: STT → LLM → TTS → Send back.
        """
        start_time = time.time()
        
        try:
            # Step 1: Transcribe audio
            print(f"⚡ Starting STT (audio size: {len(audio_bytes)} bytes)...")
            stt_start = time.time()
            
            # Transcribe and fetch conversation in parallel
            user_text, conversation_history = await asyncio.gather(
                self.transcribe_pcm_audio(audio_bytes),
                get_conversation(self.call_sid),
                return_exceptions=True
            )
            
            if isinstance(user_text, Exception):
                print(f"❌ STT Error: {user_text}")
                user_text = ""
            if isinstance(conversation_history, Exception):
                print(f"❌ Conversation error: {conversation_history}")
                conversation_history = []
            
            stt_time = time.time() - stt_start
            print(f"👤 User said: '{user_text}' (STT: {stt_time:.2f}s)")
            
            if not user_text or not user_text.strip():
                # No transcription - send error message
                await self.send_audio_response(websocket, "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।")
                return
            
            # Save user message
            asyncio.create_task(add_message(self.call_sid, "user", user_text))
            
            # Step 2: Stream LLM and generate TTS progressively
            llm_start = time.time()
            print(f"🚀 Starting LLM streaming...")
            
            ai_reply = ""
            audio_count = 0
            
            llm_stream = stream_llm_response(user_text, conversation_history)
            
            async for audio_url, sentence_text in progressive_tts_generation(llm_stream):
                ai_reply += sentence_text + " "
                audio_count += 1
                
                # Send audio chunk through WebSocket
                await self.send_audio_url_to_stream(websocket, audio_url)
                print(f"🎵 Sent audio chunk {audio_count}: '{sentence_text[:40]}...'")
            
            llm_time = time.time() - llm_start
            ai_reply = ai_reply.strip()
            
            print(f"🤖 Complete reply: '{ai_reply}'")
            print(f"⏱️  LLM+TTS Streaming: {llm_time:.2f}s")
            print(f"⏱️  Total Processing: {time.time() - start_time:.2f}s")
            
            # Save assistant message
            asyncio.create_task(add_message(self.call_sid, "assistant", ai_reply))
        
        except Exception as e:
            print(f"❌ Processing error: {e}")
            import traceback
            traceback.print_exc()
            await self.send_audio_response(websocket, "माफ़ कीजिये, अभी तकनीकी समस्या है।")
        
        finally:
            # Re-enable audio processing
            self.is_processing = False
            print("✅ Ready for next input")
            print("─" * 50)
    
    async def transcribe_pcm_audio(self, pcm_bytes: bytes) -> str:
        """
        Transcribe PCM audio using Smallest AI STT.
        """
        try:
            # Convert PCM to WAV format for STT
            import wave
            import io
            
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(8000)  # 8kHz
                wav_file.writeframes(pcm_bytes)
            
            wav_bytes = wav_buffer.getvalue()
            
            # Use existing transcription service
            return await transcribe_audio_bytes(wav_bytes)
        
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            return ""
    
    async def send_audio_url_to_stream(self, websocket: WebSocket, audio_url: str):
        """
        Fetch audio from URL and send through WebSocket to Twilio.
        """
        try:
            # Fetch audio file
            async with get_http_client() as client:
                response = await client.get(audio_url)
                audio_bytes = response.content
            
            # Convert WAV to μ-law for Twilio
            # Skip WAV header (44 bytes)
            pcm_audio = audio_bytes[44:] if len(audio_bytes) > 44 else audio_bytes
            
            # Convert to μ-law
            mulaw_audio = audioop.lin2ulaw(pcm_audio, 2)
            
            # Encode to base64
            encoded_audio = base64.b64encode(mulaw_audio).decode('utf-8')
            
            # Send through WebSocket in chunks
            chunk_size = 160  # 20ms chunks
            for i in range(0, len(encoded_audio), chunk_size):
                chunk = encoded_audio[i:i + chunk_size]
                
                message = json.dumps({
                    'event': 'media',
                    'streamSid': self.stream_sid,
                    'media': {
                        'payload': chunk
                    }
                })
                
                await websocket.send_text(message)
                await asyncio.sleep(0.02)  # 20ms delay between chunks
        
        except Exception as e:
            print(f"❌ Audio send error: {e}")
    
    async def send_audio_response(self, websocket: WebSocket, text: str):
        """
        Generate TTS for text and send through WebSocket.
        """
        try:
            from services.sarvam_service import generate_sarvam_tts
            
            audio_url = await generate_sarvam_tts(text)
            if audio_url:
                await self.send_audio_url_to_stream(websocket, audio_url)
        
        except Exception as e:
            print(f"❌ Error sending audio response: {e}")
