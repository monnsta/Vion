from .text import AI
from .summarizer import Summarizer
from .voice import VoiceUtils, GeminiVoice
from .consciousness import Consciousness


ai = AI()
summarizer = Summarizer()
voice = VoiceUtils()
consciousness = Consciousness()


__all__ = ('ai', 'summarizer', 'voice', 'GeminiVoice', 'consciousness')
