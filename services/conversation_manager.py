"""
Conversation context manager to maintain call history.
"""
from typing import Dict, List
import asyncio
from datetime import datetime, timedelta

# In-memory conversation storage
_conversations: Dict[str, List[Dict[str, str]]] = {}
_conversation_timestamps: Dict[str, datetime] = {}

# Lock for thread-safe operations
_conv_lock = asyncio.Lock()


async def add_message(call_sid: str, role: str, content: str):
    """
    Add a message to the conversation history.
    
    Args:
        call_sid: Twilio Call SID
        role: 'user' or 'assistant'
        content: Message content
    """
    async with _conv_lock:
        if call_sid not in _conversations:
            _conversations[call_sid] = []
        
        _conversations[call_sid].append({
            "role": role,
            "content": content
        })
        
        _conversation_timestamps[call_sid] = datetime.now()
        
        # Keep last 10 messages only to avoid token limits
        if len(_conversations[call_sid]) > 10:
            _conversations[call_sid] = _conversations[call_sid][-10:]
    
    

async def get_conversation(call_sid: str) -> List[Dict[str, str]]:
    """
    Get conversation history for a call.
    
    Args:
        call_sid: Twilio Call SID
        
    Returns:
        List of message dictionaries
    """
    async with _conv_lock:
        return _conversations.get(call_sid, []).copy()


async def cleanup_old_conversations(max_age_minutes: int = 60):
    """
    Clean up conversations older than max_age_minutes.
    """
    async with _conv_lock:
        now = datetime.now()
        to_delete = []
        
        for call_sid, timestamp in _conversation_timestamps.items():
            if now - timestamp > timedelta(minutes=max_age_minutes):
                to_delete.append(call_sid)
        
        for call_sid in to_delete:
            _conversations.pop(call_sid, None)
            _conversation_timestamps.pop(call_sid, None)


# Start background cleanup task
async def start_cleanup_task():
    """Background task to cleanup old conversations."""
    while True:
        await asyncio.sleep(600)  # Every 10 minutes
        await cleanup_old_conversations()
