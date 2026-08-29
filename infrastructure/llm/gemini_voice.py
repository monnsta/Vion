import io
import logging
import time
import wave
from enum import Enum
from typing import Tuple, List, Any, Dict

from google import genai
from google.genai import types
from google.genai.errors import APIError


log = logging.getLogger("llm")


class GeminiVoice(str, Enum):
	ZEPHYR = "Zephyr"
	PUCK = "Puck"
	CHARON = "Charon"
	KORE = "Kore"
	FENRIR = "Fenrir"
	LEDA = "Leda"
	ORUS = "Orus"
	AOEDE = "Aoede"
	CALLIRRHOE = "Callirrhoe"
	AUTONOE = "Autonoe"
	ENCELADUS = "Enceladus"
	IAPETUS = "Iapetus"
	UMBRIEL = "Umbriel"
	ALGIEBA = "Algieba"
	DESPINA = "Despina"
	ERINOME = "Erinome"
	ALGENIB = "Algenib"
	RASALGETHI = "Rasalgethi"
	LAOMEDEIA = "Laomedeia"
	ACHERNAR = "Achernar"
	ALNILAM = "Alnilam"
	SCHEDAR = "Schedar"
	GACRUX = "Gacrux"
	PULCHERRIMA = "Pulcherrima"
	ACHIRD = "Achird"
	ZUBENELGENUBI = "Zubenelgenubi"
	VINDEMIATRIX = "Vindemiatrix"
	SADACHBIA = "Sadachbia"
	SADALTAGER = "Sadaltager"
	SULAFAT = "Sulafat"

class GeminiTTS:
	def __init__(
		self,
		api_key: str,
		model_name: str = "gemini-2.5-flash-preview-tts"
	):
		log.debug(f"Initializing GeminiTTS with model: {model_name}")

		self.api_key = api_key
		self.client = genai.Client(api_key=api_key)
		self.model_name = model_name
		self.cooldown_until: float = 0.0

	@property
	def is_cooling_down(self) -> bool:
		cooling = time.time() < self.cooldown_until

		if cooling:
			log.debug(f"TTS cooldown active. Remaining: {self.cooldown_until - time.time():.1f}s")

		return cooling

	def set_cooldown(self, seconds: float) -> None:
		self.cooldown_until = time.time() + seconds

		log.debug(f"TTS cooldown set for {seconds}s. Active until: {self.cooldown_until}")

	@staticmethod
	def _pcm_to_wav(
		pcm: bytes,
		channels: int = 1,
		sample_rate: int = 24000,
		sample_width: int = 2,
	) -> bytes:
		buffer = io.BytesIO()

		with wave.open(buffer, "wb") as wav:
			wav.setnchannels(channels)
			wav.setsampwidth(sample_width)
			wav.setframerate(sample_rate)
			wav.writeframes(pcm)

		return buffer.getvalue()

	@staticmethod
	def _normalize_voice(voice: GeminiVoice | str) -> GeminiVoice | None:
		if isinstance(voice, GeminiVoice):
			return voice

		try:
			return GeminiVoice(voice)
		except ValueError:
			normalized = voice.strip().lower()

			for candidate in GeminiVoice:
				if candidate.value.lower() == normalized:
					return candidate

		return None

	async def call(
		self,
		text: str,
		voice: GeminiVoice | str = GeminiVoice.CHARON
	) -> Tuple[bool, bytes]:
		if not text or not text.strip():
			log.warning("GeminiTTS.call() received empty text.")
			return False, b""

		if self.is_cooling_down:
			remaining = self.cooldown_until - time.time()

			log.debug(f"Gemini TTS request rejected due to cooldown. Remaining: {remaining:.1f}s")

			return False, b""

		voice_obj = self._normalize_voice(voice)

		if voice_obj is None:
			log.warning(f"Unknown Gemini TTS voice: {voice!r}")
			return False, b""

		log.debug(f"Starting Gemini TTS generation (model={self.model_name}, voice={voice_obj.value}, text_length={len(text)})")

		try:
			response = await self.client.aio.models.generate_content(
				model=self.model_name,
				contents=text,
				config=types.GenerateContentConfig(
					response_modalities=["AUDIO"],
					speech_config=types.SpeechConfig(
						voice_config=types.VoiceConfig(
							prebuilt_voice_config=types.PrebuiltVoiceConfig(
								voice_name=voice_obj.value
							)
						)
					),
				),
			)

			if not response.candidates:
				log.warning("Gemini TTS returned no candidates.")
				return False, b""

			for candidate in response.candidates:
				if not candidate.content or not candidate.content.parts:
					continue

				for part in candidate.content.parts:
					if not part.inline_data or not part.inline_data.data:
						continue

					pcm = part.inline_data.data

					if isinstance(pcm, str):
						pcm = pcm.encode("latin1")

					wav = self._pcm_to_wav(pcm)

					log.debug(f"Gemini TTS generation succeeded (voice={voice_obj.value}, PCM={len(pcm)} bytes, WAV={len(wav)} bytes)")

					return True, wav

			log.warning("Gemini TTS returned a candidate, but no inline audio data was present.")

			return False, b""

		except APIError as e:
			log.debug(f"Gemini TTS APIError caught (code={e.code}, message={e.message})")

			if e.code == 429:
				cooldown_seconds = 20.0

				try:
					details: List[Dict[str, Any]] = (getattr(e, "details", []) or [])

					for detail in details:
						if (isinstance(detail, dict) and "retryDelay" in detail):
							cooldown_seconds = float(str(detail["retryDelay"]).rstrip("s"))
							break

				except Exception:
					log.debug("Failed to parse TTS retry delay.", exc_info=True)

				self.set_cooldown(cooldown_seconds)

				log.warning(f"Gemini TTS rate limited. Retry after {cooldown_seconds}s.")

				return False, b""

			if e.code in (401, 403):
				log.error(f"Gemini TTS authentication error ({e.code}).")

				return False, b""

			log.error(f"Gemini TTS API error ({e.code}): {e}")

			return False, b""

		except Exception:
			log.error("Unexpected error during Gemini TTS generation.", exc_info=True)

			return False, b""
