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
        self.vad = VoiceActivityDetector(aggressiveness=2, sample_rate=8000, frame_duration_ms=20)
        self.audio_buffer = bytearray()
        self.stream_sid = None
        self.call_sid = None
        self.is_processing = False
        self.websocket = None
        self.processing_lock = asyncio.Lock()  # Add lock to prevent race conditions
        
    async def handle_connection(self, websocket: WebSocket):
        """
        Main WebSocket connection handler.
        """
        await websocket.accept()
        
        # Store websocket for later use
        self.websocket = websocket
        
        try:
            async for message in websocket.iter_text():
                await self.process_message(websocket, message)
        
        except WebSocketDisconnect:
            pass
        except Exception as e:
            pass
    
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
            pass
    
    async def handle_start(self, data):
        """
        Handle stream start event.
        """
        self.stream_sid = data['streamSid']
        self.call_sid = data['start']['callSid']
        print(f"📡 Stream Started - CallSid: {self.call_sid}")
        
        # Reset state
        self.audio_buffer = bytearray()
        self.vad.reset()
        self.is_processing = False
        
        # Send welcome message after a brief delay to ensure stream is ready
        asyncio.create_task(self.send_welcome_message())
    
    async def handle_media(self, websocket: WebSocket, data):
        """
        Handle incoming audio media packets.
        """
        # Don't process audio while we're already processing a response
        if self.is_processing:
            # Clear buffer continuously to avoid accumulating audio during playback
            self.audio_buffer = bytearray()
            self.vad.reset()  # Reset VAD state too
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
            if vad_result['speech_ended'] and len(self.audio_buffer) > 6400:  # At least 0.4s of audio (moderate)
                # Use lock to prevent race condition where multiple speech_ended events spawn tasks
                async with self.processing_lock:
                    # Double-check flag inside lock
                    if self.is_processing:
                        return
                    
                    print(f"🎤 Speech ended - Buffer: {len(self.audio_buffer)} bytes")
                    
                    # Set processing flag immediately BEFORE spawning task
                    self.is_processing = True
                    
                    # Create a copy of the buffer and clear it
                    audio_to_process = bytes(self.audio_buffer)
                    self.audio_buffer = bytearray()
                    self.vad.reset()
                    
                    # Process in background
                    asyncio.create_task(self.process_audio(websocket, audio_to_process))
    
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
            stt_start = time.time()
            
            # Transcribe and fetch conversation in parallel
            user_text, conversation_history = await asyncio.gather(
                self.transcribe_pcm_audio(audio_bytes),
                get_conversation(self.call_sid),
                return_exceptions=True
            )
            
            if isinstance(user_text, Exception):
                user_text = ""
            if isinstance(conversation_history, Exception):
                conversation_history = []
            
            stt_time = time.time() - stt_start
            print(f"👤 User: '{user_text}' | STT: {stt_time:.2f}s\n ")
            
            if not user_text or not user_text.strip():
                # No transcription - send error message
                await self.send_audio_response(websocket, "मैंने आपकी आवाज़ नहीं सुनी, कृपया फिर से बोलिए।")
                return
            
            # Save user message
            asyncio.create_task(add_message(self.call_sid, "user", user_text))
            
            # Step 2: Stream LLM and generate TTS progressively
            llm_start = time.time()
            
            ai_reply = ""
            audio_count = 0
            
            llm_stream = stream_llm_response(user_text, conversation_history)
            
            async for audio_url, sentence_text in progressive_tts_generation(llm_stream):
                ai_reply += sentence_text + " "
                audio_count += 1
                
                # Send audio chunk through WebSocket
                await self.send_audio_url_to_stream(websocket, audio_url)
            
            llm_time = time.time() - llm_start
            ai_reply = ai_reply.strip()
            total_time = time.time() - start_time
            
            print(f"🤖 AI: '{ai_reply[:60]}...' | LLM+TTS: {llm_time:.2f}s | Total: {total_time:.2f}s")
            
            # Save assistant message
            asyncio.create_task(add_message(self.call_sid, "assistant", ai_reply))
            
            # Wait longer for audio to finish playing before accepting new input
            await asyncio.sleep(1.0)
        
        except Exception as e:
            await self.send_audio_response(websocket, "माफ़ कीजिये, अभी तकनीकी समस्या है।")
        
        finally:
            # Wait a bit before re-enabling to avoid immediate re-trigger
            await asyncio.sleep(0.3)
            
            # Re-enable audio processing and ensure buffer is clear
            self.audio_buffer = bytearray()
            self.vad.reset()
            self.is_processing = False
    
    async def transcribe_pcm_audio(self, pcm_bytes: bytes) -> str:
        """
        Transcribe PCM audio using Smallest AI STT.
        """
        try:
            # Check if we have enough audio (at least 0.3 second = 4800 bytes at 8kHz 16-bit)
            if len(pcm_bytes) < 4800:
                print(f"⚠️  Audio too short: {len(pcm_bytes)} bytes")
                return ""
            
            # Check audio energy (RMS) to filter out silence/noise
            import array
            audio_ints = array.array('h', pcm_bytes)  # 16-bit signed integers
            rms = (sum(s**2 for s in audio_ints) / len(audio_ints)) ** 0.5
            
            print(f"🔊 Audio RMS: {rms:.0f}, Length: {len(pcm_bytes)/16000:.2f}s")
            
            # If audio is too quiet, skip transcription (likely noise/silence)
            if rms < 50:  # Lower threshold to handle quieter audio
                print(f"⚠️  Audio too quiet (RMS {rms:.0f})")
                return ""
            
            # Convert PCM to WAV format for STT
            import wave
            import io
            
            # Try upsampling to 16kHz for better STT recognition
            try:
                upsampled_pcm = audioop.ratecv(pcm_bytes, 2, 1, 8000, 16000, None)[0]
                target_rate = 16000
                target_pcm = upsampled_pcm
                print(f"🔄 Upsampled to 16kHz")
            except Exception as e:
                print(f"⚠️  Upsampling failed: {e}")
                target_rate = 8000
                target_pcm = pcm_bytes
            
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(target_rate)
                wav_file.writeframes(target_pcm)
            
            wav_bytes = wav_buffer.getvalue()
            
            print(f"📤 Sending to STT: {len(wav_bytes)} bytes")
            
            # Use existing transcription service
            transcript = await transcribe_audio_bytes(wav_bytes)
            
            if transcript:
                print(f"✅ Transcribed: '{transcript}'")
            else:
                print(f"⚠️  STT returned empty")
            
            return transcript
        
        except Exception as e:
            return ""
    
    async def send_audio_url_to_stream(self, websocket: WebSocket, audio_url: str):
        """
        Fetch audio from URL and send through WebSocket to Twilio.
        """
        try:
            # Extract audio_id from URL and fetch directly from cache (more efficient)
            if '/audio-stream/' in audio_url:
                audio_id = audio_url.split('/audio-stream/')[-1]
                
                from services.audio_cache import get_audio
                audio_bytes = await get_audio(audio_id)
                
                if not audio_bytes:
                    return
            else:
                # Fallback: fetch via HTTP
                client = get_http_client()
                response = await client.get(audio_url)
                
                if response.status_code != 200:
                    return
                
                audio_bytes = response.content
            
            # Check if it's a valid WAV file
            if not audio_bytes.startswith(b'RIFF'):
                return
                
            # Properly parse WAV file
            import wave
            import io
            
            wav_buffer = io.BytesIO(audio_bytes)
            with wave.open(wav_buffer, 'rb') as wav_file:
                # Get WAV parameters
                channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                frame_rate = wav_file.getframerate()
                n_frames = wav_file.getnframes()
                
                # Read PCM data
                pcm_audio = wav_file.readframes(n_frames)
            
            # Convert to mono if stereo
            if channels == 2:
                pcm_audio = audioop.tomono(pcm_audio, sample_width, 0.5, 0.5)
            
            # Resample to 8kHz if needed (Twilio expects 8kHz μ-law)
            if frame_rate != 8000:
                pcm_audio, _ = audioop.ratecv(pcm_audio, sample_width, 1, frame_rate, 8000, None)
            
            # Ensure 16-bit samples
            if sample_width != 2:
                # Convert to 16-bit
                if sample_width == 1:
                    pcm_audio = audioop.bias(pcm_audio, 1, -128)  # unsigned to signed
                    pcm_audio = audioop.lin2lin(pcm_audio, 1, 2)  # 8-bit to 16-bit
            
            # Convert to μ-law (Twilio format)
            mulaw_audio = audioop.lin2ulaw(pcm_audio, 2)
            
            # Encode to base64
            encoded_audio = base64.b64encode(mulaw_audio).decode('utf-8')
            
            # Send through WebSocket in chunks (160 bytes = 20ms at 8kHz μ-law)
            chunk_size = 160
            for i in range(0, len(mulaw_audio), chunk_size):
                chunk = mulaw_audio[i:i + chunk_size]
                
                # Base64 encode the chunk
                chunk_encoded = base64.b64encode(chunk).decode('utf-8')
                
                message = json.dumps({
                    'event': 'media',
                    'streamSid': self.stream_sid,
                    'media': {
                        'payload': chunk_encoded
                    }
                })
                
                await websocket.send_text(message)
                await asyncio.sleep(0.02)  # 20ms delay between chunks
            
            # Send a mark event to track when audio finishes playing
            mark_message = json.dumps({
                'event': 'mark',
                'streamSid': self.stream_sid,
                'mark': {
                    'name': f'audio_complete_{int(time.time() * 1000)}'
                }
            })
            await websocket.send_text(mark_message)
        
        except Exception as e:
            pass
    
    async def send_welcome_message(self):
        """
        Send welcome message after a brief delay to ensure stream is ready.
        """
        try:
            # Wait a bit for stream to be fully established
            await asyncio.sleep(0.5)
            
            # Set processing flag to prevent speech detection during welcome
            async with self.processing_lock:
                self.is_processing = True
            
            await self.send_audio_response(
                self.websocket, 
                "नमस्ते, मैं आपका AI सहायक हूँ। कृपया कुछ बोलिए।"
            )
            
            # Wait longer after message, then allow speech detection
            await asyncio.sleep(1.0)
            self.is_processing = False
        except Exception as e:
            self.is_processing = False
    
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
            pass
