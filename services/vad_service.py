"""
Voice Activity Detection service for real-time audio streaming.
"""
import webrtcvad
import collections
import time


class VoiceActivityDetector:
    """
    Detects when user starts and stops speaking in real-time.
    Uses WebRTC VAD for accurate speech detection.
    """
    
    def __init__(self, aggressiveness=3, sample_rate=8000, frame_duration_ms=20):
        """
        Initialize VAD.
        
        Args:
            aggressiveness: VAD aggressiveness (0-3, higher = more aggressive filtering)
            sample_rate: Audio sample rate (8000, 16000, 32000, or 48000)
            frame_duration_ms: Frame duration (10, 20, or 30 ms)
        """
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        
        # Sliding window for smoothing
        self.ring_buffer = collections.deque(maxlen=30)  # 600ms buffer
        
        # Speech detection thresholds
        self.speech_frames_threshold = 6  # Frames needed to trigger speech start (120ms - moderate)
        self.silence_frames_threshold = 18  # Frames needed to trigger speech end (360ms - moderate)
        
        # State tracking
        self.is_speaking = False
        self.consecutive_silence_frames = 0
        self.consecutive_speech_frames = 0
        
    def process_frame(self, frame_bytes: bytes) -> dict:
        """
        Process a single audio frame and detect speech activity.
        
        Args:
            frame_bytes: Raw audio frame (must be correct size for sample rate)
            
        Returns:
            Dict with: {
                'is_speech': bool,
                'speech_started': bool,
                'speech_ended': bool,
                'confidence': float
            }
        """
        # Ensure frame is correct size
        if len(frame_bytes) != self.frame_size * 2:  # 2 bytes per sample (16-bit)
            # Pad or truncate
            if len(frame_bytes) < self.frame_size * 2:
                frame_bytes = frame_bytes + b'\x00' * (self.frame_size * 2 - len(frame_bytes))
            else:
                frame_bytes = frame_bytes[:self.frame_size * 2]
        
        # Run VAD
        try:
            is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
        except Exception as e:
            is_speech = False
        
        # Add to ring buffer for smoothing
        self.ring_buffer.append(1 if is_speech else 0)
        
        # Calculate confidence (percentage of recent frames with speech)
        confidence = sum(self.ring_buffer) / len(self.ring_buffer) if self.ring_buffer else 0
        
        # Track consecutive frames
        if is_speech:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
        else:
            self.consecutive_silence_frames += 1
            self.consecutive_speech_frames = 0
        
        # Detect speech start/end transitions
        speech_started = False
        speech_ended = False
        
        if not self.is_speaking and self.consecutive_speech_frames >= self.speech_frames_threshold:
            # Speech just started
            self.is_speaking = True
            speech_started = True
            print(f"🎤 Speech started (confidence: {confidence:.2f})")
        
        elif self.is_speaking and self.consecutive_silence_frames >= self.silence_frames_threshold:
            # Speech just ended
            self.is_speaking = False
            speech_ended = True
            print(f"🔇 Speech ended (silence: {self.consecutive_silence_frames} frames)")
        
        return {
            'is_speech': is_speech,
            'is_speaking': self.is_speaking,
            'speech_started': speech_started,
            'speech_ended': speech_ended,
            'confidence': confidence
        }
    
    def reset(self):
        """Reset detector state."""
        self.ring_buffer.clear()
        self.is_speaking = False
        self.consecutive_silence_frames = 0
        self.consecutive_speech_frames = 0
