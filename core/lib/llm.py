import asyncio
import io
import logging
import tempfile
import time
import wave
import mimetypes
from enum import Enum
from pathlib import Path
from typing import Tuple, List, Any, Dict

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError


log = logging.getLogger(__name__)


async def validate_key(api_key: str) -> bool | None:
	try:
		client = genai.Client(api_key=api_key)
		await client.aio.models.list()
		return True
	except APIError as e:
		log.debug(f"APIError caught during validation with code: {e.code} message: {e.message}")
		if e.code in (400, 401, 403):
			log.error(f"API key validation failed: {e}")
			return False
		elif e.code in (429, 500, 503, 504):
			log.warning(f"Validation inconclusive due to network/rate/service error: {e}")
			return None
		log.error(f"API key validation failed with unexpected API status: {e}")
		return False
	except Exception:
		log.error("An unexpected error occurred during API key validation", exc_info=True)
		return None


class GenerateContent:
	def __init__(
		self,
		api_key: str,
		model_name: str,
		system_instruction: str | None = None,
		temperature: float = 0.6,
		top_p: float = 1.0,
		top_k: int = 45
	):
		log.debug(f"Initializing GenerateContent with model: {model_name}, temp: {temperature}, top_p: {top_p}, top_k: {top_k}")
		self.api_key = api_key
		self.client = genai.Client(api_key=api_key)
		self.model_name = model_name
		self.cooldown_until: float = 0.0

		self.config = types.GenerateContentConfig(
			temperature=temperature,
			top_p=top_p,
			top_k=top_k,
			system_instruction=system_instruction
		)
		log.debug("GenerateContent config successfully built")

	@property
	def is_cooling_down(self) -> bool:
		cooling = time.time() < self.cooldown_until
		if cooling:
			log.debug(f"Cooldown check: Active. Remaining: {self.cooldown_until - time.time():.1f}s")
		return cooling

	def set_cooldown(self, seconds: float):
		self.cooldown_until = time.time() + seconds
		log.debug(f"Cooldown set for {seconds} seconds. Active until: {self.cooldown_until}")

	async def _upload_and_wait(self, path: str, mime_type: str | None = None) -> Any:
		log.debug(f"Uploading file: {path} with MIME type: {mime_type}")

		upload_kwargs: dict[str, Any] = {"file": path}
		if mime_type:
			upload_kwargs["config"] = {"mime_type": mime_type}

		file_obj = await self.client.aio.files.upload(**upload_kwargs) # type: ignore

		log.debug(f"File uploaded successfully, name: {file_obj.name}, initial state: {file_obj.state}")

		poll_count = 0
		while file_obj.state == "PROCESSING":
			poll_count += 1
			log.debug(f"Polling file status (Attempt {poll_count}) for {file_obj.name}: {file_obj.state}")
			await asyncio.sleep(1)
			if not file_obj.name:
				log.error("File name missing during processing loop.")
				raise RuntimeError("File name missing during processing.")
			file_obj = await self.client.aio.files.get(name=file_obj.name)

		if file_obj.state == "FAILED":
			log.error(f"File processing failed for: {file_obj.name} with state details: {file_obj}")
			raise RuntimeError(f"File {file_obj.name} failed to process.")

		log.debug(f"File processing complete: {file_obj.name}, final state: {file_obj.state}")
		return file_obj

	async def _handle_remote_file(self, url: str) -> Any:
		log.debug(f"Downloading remote file from URL: {url}")
		async with httpx.AsyncClient(follow_redirects=True) as client:
			response = await client.get(url)
			log.debug(f"Remote file download status code: {response.status_code}")
			response.raise_for_status()

			mime_type = response.headers.get("Content-Type")
			log.debug(f"Detected remote file MIME type from header: {mime_type}")

			with tempfile.NamedTemporaryFile(delete=False) as tmp:
				tmp.write(response.content)
				tmp_path = tmp.name

		log.debug(f"Temporary file created for remote download at: {tmp_path} (Size: {len(response.content)} bytes)")
		try:
			return await self._upload_and_wait(tmp_path, mime_type=mime_type)
		finally:
			tmp_file = Path(tmp_path)
			if tmp_file.exists():
				tmp_file.unlink()
				log.debug(f"Cleaned up temporary file: {tmp_path}")

	async def _process_input(self, item: Any) -> Any:
		log.debug(f"Processing input item of type: {type(item)}")
		if isinstance(item, str):
			if item.startswith(("http://", "https://")):
				log.debug(f"Input identified as remote URL: {item}")
				return await self._handle_remote_file(item)
			if Path(item).is_file():
				log.debug(f"Detected local file path: {item}")
				return await self._upload_and_wait(item)
			log.debug(f"Input string is neither a valid URL nor an existing local file: {item}")

		if isinstance(item, (io.BytesIO, io.IOBase)):
			log.debug("Detected file-like input stream")

			item.seek(0)
			filename = getattr(item, "name", "file")
			mime_type, _ = mimetypes.guess_type(filename)
			data_bytes = item.read()
			log.debug(f"File-like input details - Name: {filename}, Guessed MIME: {mime_type}, Size: {len(data_bytes)} bytes")

			return types.Part.from_bytes(
				data=data_bytes,
				mime_type=mime_type or "application/octet-stream"
			)

		if isinstance(item, bytes):
			log.debug(f"Detected raw bytes input of size: {len(item)} bytes")

			return types.Part.from_bytes(
				data=item,
				mime_type="application/octet-stream"
			)

		log.debug(f"Input passed through without specialized transformation: {type(item)}")
		return item

	async def call(self, prompt: str, inputs: List[Any] | None = None) -> Tuple[bool, str]:
		log.debug(f"call() invoked with prompt length: {len(prompt)} chars, inputs count: {len(inputs) if inputs else 0}")
		if self.is_cooling_down:
			remaining = self.cooldown_until - time.time()
			log.debug(f"Rate limited. Cooldown remaining: {remaining:.1f}s")
			return False, f"Rate limited. Cooldown remaining: {remaining:.1f}s"

		log.debug("Starting content generation call execution")
		try:
			processed_parts = []
			if inputs:
				log.debug(f"Processing {len(inputs)} input items concurrently")
				start_time = time.time()
				processed_parts = await asyncio.gather(
					*[self._process_input(i) for i in inputs]
				)
				log.debug(f"Finished processing all inputs in {time.time() - start_time:.2f}s")

			payload = list(processed_parts) + [prompt]
			log.debug(f"Sending payload to Gemini API model '{self.model_name}' with total parts: {len(payload)}")

			api_start_time = time.time()
			response = await self.client.aio.models.generate_content(
				model=self.model_name,
				contents=payload,
				config=self.config
			)
			log.debug(f"Gemini API response received in {time.time() - api_start_time:.2f}s")

			if response.candidates and len(response.candidates) > 0:
				log.debug(f"Content generation successful. Candidate count: {len(response.candidates)}")
				if not response.text:
					log.warning("AI sent a candidate response, but response.text is null/empty")
					return False, "AI sent a null response"
				log.debug(f"Response text length: {len(response.text)} chars")
				return True, response.text

			log.warning("AI returned no candidates or content structure empty")
			return False, "AI returned no content."

		except APIError as e:
			log.debug(f"APIError caught in call() with code: {e.code}, message: {e.message}")
			if e.code == 429:
				cooldown_seconds = 20.0
				log.warning("Rate limit (429) hit, parsing details for retry delay")

				try:
					details: List[Dict[str, Any]] = getattr(e, "details", []) or []
					for detail in details:
						if isinstance(detail, dict) and "retryDelay" in detail:
							cooldown_seconds = float(str(detail["retryDelay"]).rstrip("s"))
							log.debug(f"Extracted custom retryDelay: {cooldown_seconds}s")
							break
				except Exception:
					log.debug("Failed to parse custom retryDelay from error details, using default", exc_info=True)

				self.set_cooldown(cooldown_seconds)
				return False, f"Rate limit reached (429). Retry after {cooldown_seconds}s"

			elif e.code in (401, 403):
				log.error(f"Auth error (Code {e.code}). Key might be invalid.")
				return False, f"Authentication error: {e.message}"

			log.error(f"Gemini API error occurred (Status {e.code}): {e}")
			return False, f"API Error ({e.code}): {e.message}"

		except Exception as e:
			log.error("Unexpected error during call execution", exc_info=True)
			return False, f"Utility Error: {str(e)}"


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
		model_name: str = "gemini-3.1-flash-tts-preview"
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
		voice: GeminiVoice | str = GeminiVoice.KORE
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
					system_instruction="You are a strict text-to-speech engine. Generate audio from the given text transcript exactly as written. Do not answer questions, provide context, or generate text.",
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


class AssemblyAITranscriber:
	def __init__(self, api_key: str, **config_kwargs: Any):
		log.debug("Initializing AssemblyAITranscriber")
		self.api_key = api_key
		self.base_url = "https://api.assemblyai.com/v2"
		self.headers = {"authorization": self.api_key}
		self.config = config_kwargs

	async def _upload_data(self, data: bytes) -> str:
		log.debug(f"Uploading raw data of size {len(data)} bytes to AssemblyAI")
		async with httpx.AsyncClient(timeout=None) as client:
			response = await client.post(
				f"{self.base_url}/upload",
				headers=self.headers,
				content=data
			)
			response.raise_for_status()
			upload_url = response.json().get("upload_url")
			log.debug("Data uploaded successfully, received upload URL")
			return upload_url

	async def _process_input(self, item: Any) -> str:
		log.debug(f"Processing input item of type: {type(item)} for AssemblyAI")
		if isinstance(item, str):
			if item.startswith(("http://", "https://")):
				log.debug(f"AssemblyAI: Detected remote URL: {item}")
				return item

			if Path(item).is_file():
				log.debug(f"AssemblyAI: Uploading local file: {item}")
				file_data = Path(item).read_bytes()
				return await self._upload_data(file_data)

		if isinstance(item, (io.BytesIO, io.IOBase)):
			log.debug("AssemblyAI: Reading from file-like stream")
			item.seek(0)
			data = item.read()
			if isinstance(data, str):
				data = data.encode('utf-8')
			return await self._upload_data(data)

		if isinstance(item, bytes):
			log.debug("AssemblyAI: Handling raw bytes payload")
			return await self._upload_data(item)

		raise ValueError(f"Unsupported input type for AssemblyAI transcription: {type(item)}")

	async def call(self, item: Any) -> Tuple[bool, str]:
		log.debug("Starting AssemblyAI transcription process")
		try:
			audio_url = await self._process_input(item)

			async with httpx.AsyncClient() as client:
				payload = {"audio_url": audio_url, **self.config}
				log.debug("Submitting transcription job to AssemblyAI endpoint")
				submit_resp = await client.post(
					f"{self.base_url}/transcript",
					json=payload,
					headers=self.headers
				)
				submit_resp.raise_for_status()
				transcript_id = submit_resp.json()["id"]
				log.debug(f"Job submitted successfully. Tracking ID: {transcript_id}")

				poll_count = 0
				while True:
					poll_count += 1
					await asyncio.sleep(3)

					poll_resp = await client.get(
						f"{self.base_url}/transcript/{transcript_id}",
						headers=self.headers
					)
					poll_resp.raise_for_status()

					result = poll_resp.json()
					status = result.get("status")

					log.debug(f"Polling AssemblyAI (Attempt {poll_count}): {status}")

					if status == "completed":
						log.debug("Transcription completed successfully.")
						return True, result.get("text", "")
					elif status == "error":
						error_msg = result.get("error", "Unknown processing error from AssemblyAI")
						log.error(f"AssemblyAI transcription failed: {error_msg}")
						return False, error_msg

		except httpx.HTTPStatusError as e:
			log.error(f"HTTP error during AssemblyAI network request: {e}")
			return False, f"API Error: {e.response.text}"
		except Exception as e:
			log.error("Unexpected error in AssemblyAI execution chain", exc_info=True)
			return False, f"Utility Error: {str(e)}"


__all__ = (
	'validate_key',
	'GenerateContent',
	'GeminiTTS',
	'GeminiVoice',
	'AssemblyAITranscriber'
)
