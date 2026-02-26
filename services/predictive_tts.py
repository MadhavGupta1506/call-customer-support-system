"""
Predictive TTS service - Pre-generates TTS for likely next responses.
Significantly reduces perceived latency by having audio ready before it's needed.
"""
import asyncio
from typing import Dict, List
from services.sarvam_service import generate_sarvam_tts

# Conversation flow predictions based on typical call patterns
PREDICTIVE_RESPONSES = {
    "after_greeting": [
        "आगे बढ़ने से पहले, आप किस भाषा में बात करना पसंद करेंगे — हिंदी या इंग्लिश?",
        "अभी आप एक मिनट बात कर सकते हैं?",
    ],
    "after_language_selection": [
        "धन्यवाद। मैं आपकी इन्दौर, मध्य प्रदेश से पुणे, महाराष्ट्र तक घर का सामान शिफ्ट करने की इन्क्वायरी के बारे में कॉल कर रही हूं। बस कुछ बातें पक्की कर लूं ताकि हम ठीक से मदद कर सकें।",
    ],
    "common_questions": [
        "क्या हमारी ब्रांच से किसी ने आपको पहले कॉल किया है और कोटेशन भेजा है?",
        "आप एक BHK, दो BHK या तीन BHK शिफ्ट कर रहे हैं?",
        "पिकअप का फ्लोर नंबर क्या है? लिफ्ट है या नहीं?",
        "आप कोटेशन ईमेल पर चाहेंगे या व्हाट्सऐप पर?",
        "किस दिन और समय पर सर्वे के लिए सुविधाजनक रहेगा?",
    ],
    "common_acknowledgments": [
        "धन्यवाद।",
        "ठीक है।",
        "समझ गया।",
        "देरी के लिए माफी चाहती हूं। हम तुरंत आपकी मदद करेंगे।",
    ]
}

# Pre-generation status tracking
_pregeneration_status: Dict[str, bool] = {}
_pregeneration_lock = asyncio.Lock()


async def prewarm_predictive_tts():
    """Pre-generate TTS for all predictive responses in background."""
    all_responses = []
    for category, responses in PREDICTIVE_RESPONSES.items():
        all_responses.extend(responses)
    
    # Generate all in parallel
    tasks = [generate_sarvam_tts(response) for response in all_responses]
    await asyncio.gather(*tasks, return_exceptions=True)


async def trigger_contextual_pregeneration(context_key: str):
    """
    Trigger pre-generation of likely next responses based on conversation context.
    This runs in background and doesn't block the main flow.
    
    Args:
        context_key: Key indicating current conversation state
    """
    async with _pregeneration_lock:
        # Avoid duplicate pre-generation
        if _pregeneration_status.get(context_key, False):
            return
        _pregeneration_status[context_key] = True
    
    # Get predicted responses for this context
    predicted_responses = PREDICTIVE_RESPONSES.get(context_key, [])
    
    if predicted_responses:
        # Fire and forget - don't wait for completion
        for response in predicted_responses:
            asyncio.create_task(generate_sarvam_tts(response))


def get_conversation_context(user_text: str, conversation_history: List) -> str:
    """
    Determine conversation context to predict next likely responses.
    
    Args:
        user_text: Current user input
        conversation_history: Previous conversation
        
    Returns:
        Context key for predictive pre-generation
    """
    user_lower = user_text.lower().strip()
    
    # Determine context based on user input and history
    if len(conversation_history) <= 2:
        return "after_greeting"
    
    if any(keyword in user_lower for keyword in ["हिंदी", "hindi", "इंग्लिश", "english"]):
        return "after_language_selection"
    
    if any(keyword in user_lower for keyword in ["हाँ", "yes", "ठीक", "okay", "ok"]):
        return "common_questions"
    
    return "common_acknowledgments"
