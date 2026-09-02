"""
AI Engine Module Package.

Provides high-level interfaces and instances for text generation, text summarization,
voice management / TTS / transcription, and event-driven consciousness evaluation.
"""

from .text import AI
from .summarizer import Summarizer
from .voice import VoiceUtils, GeminiVoice
from .consciousness import Consciousness


ai = AI()
summarizer = Summarizer()
voice = VoiceUtils()
consciousness = Consciousness()


__all__ = ('ai', 'summarizer', 'voice', 'GeminiVoice', 'consciousness')
