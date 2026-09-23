"""
Google Gemini content generation and API validation suite.

Provides API key validity verification and asynchronous context-aware prompt processing.
"""

import asyncio
import io
import logging
import tempfile
import time
import mimetypes
from pathlib import Path
from typing import Tuple, List, Any, Dict

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError


log = logging.getLogger("llm")


async def validate_key(api_key: str) -> bool | None:
	"""
	Asynchronously test Google Gemini API key authorization validity.

	Args:
		api_key: The target Google Gemini API key string.

	Returns:
		True if key is valid, False if rejected, or None if validation is inconclusive.
	"""
	try:
		client = genai.Client(api_key=api_key)
		await client.aio.models.list()
		return True
	except APIError as e:
		log.debug(
			f"APIError caught during validation with code: {e.code} message: {e.message}"
		)
		if e.code in (400, 401, 403):
			log.error(f"API key validation failed: {e}")
			return False
		elif e.code in (429, 500, 503, 504):
			log.warning(
				f"Validation inconclusive due to network/rate/service error: {e}"
			)
			return None
		log.error(f"API key validation failed with unexpected API status: {e}")
		return False
	except Exception:
		log.error(
			"An unexpected error occurred during API key validation", exc_info=True
		)
		return None


class GenerateContent:
	"""
	Content generation handler managing Gemini API client requests and file attachments.

	Attributes:
		api_key: Gemini API authorization key string.
		client: Configured google.genai Client instance.
		model_name: Target generation model identifier string.
		cooldown_until: Timestamp float representing remaining cooldown duration.
		config: Generation parameter settings configuration wrapper.
	"""

	def __init__(
		self,
		api_key: str,
		model_name: str,
		system_instruction: str | None = None,
		temperature: float = 0.6,
		top_p: float = 1.0,
		top_k: int = 45,
	) -> None:
		"""
		Initialize GenerateContent client options.

		Args:
			api_key: Target Google Gemini API key string.
			model_name: Model string identifier.
			system_instruction: Optional system instruction prompt text.
			temperature: Controls target output randomness sampling.
			top_p: Nucleus sampling cutoff threshold.
			top_k: Top-k token selection pool bound.
		"""
		log.debug(
			f"Initializing GenerateContent with model: {model_name}, temp: {temperature}, top_p: {top_p}, top_k: {top_k}"
		)
		self.api_key = api_key
		self.client = genai.Client(api_key=api_key)
		self.model_name = model_name
		self.cooldown_until: float = 0.0

		self.config = types.GenerateContentConfig(
			temperature=temperature,
			top_p=top_p,
			top_k=top_k,
			system_instruction=system_instruction,
		)
		log.debug("GenerateContent config successfully built")

	@property
	def is_cooling_down(self) -> bool:
		"""Check if client rate-limit active cooldown period has elapsed."""
		cooling = time.time() < self.cooldown_until
		if cooling:
			log.debug(
				f"Cooldown check: Active. Remaining: {self.cooldown_until - time.time():.1f}s"
			)
		return cooling

	def set_cooldown(self, seconds: float) -> None:
		"""
		Set a temporary execution rate cooldown delay.

		Args:
			seconds: Duration length in seconds.
		"""
		self.cooldown_until = time.time() + seconds
		log.debug(
			f"Cooldown set for {seconds} seconds. Active until: {self.cooldown_until}"
		)

	async def _upload_and_wait(self, path: str, mime_type: str | None = None) -> Any:
		"""
		Upload file resource to Gemini File API and poll processing status.

		Args:
			path: Target local file path string.
			mime_type: Optional explicit media MIME type string.

		Returns:
			Processable Gemini file resource object reference.

		Raises:
			RuntimeError: If remote file processing status fails or stalls.
		"""
		log.debug(f"Uploading file: {path} with MIME type: {mime_type}")

		upload_kwargs: dict[str, Any] = {"file": path}
		if mime_type:
			upload_kwargs["config"] = {"mime_type": mime_type}

		file_obj = await self.client.aio.files.upload(**upload_kwargs)  # type: ignore

		log.debug(
			f"File uploaded successfully, name: {file_obj.name}, initial state: {file_obj.state}"
		)

		poll_count = 0
		while file_obj.state == "PROCESSING":
			poll_count += 1
			log.debug(
				f"Polling file status (Attempt {poll_count}) for {file_obj.name}: {file_obj.state}"
			)
			await asyncio.sleep(1)
			if not file_obj.name:
				log.error("File name missing during processing loop.")
				raise RuntimeError("File name missing during processing.")
			file_obj = await self.client.aio.files.get(name=file_obj.name)

		if file_obj.state == "FAILED":
			log.error(
				f"File processing failed for: {file_obj.name} with state details: {file_obj}"
			)
			raise RuntimeError(f"File {file_obj.name} failed to process.")

		log.debug(
			f"File processing complete: {file_obj.name}, final state: {file_obj.state}"
		)
		return file_obj

	async def _handle_remote_file(self, url: str) -> Any:
		"""
		Download external media URL payload to local temporary store for upload.

		Args:
			url: Remote HTTP resource address string.

		Returns:
			Uploaded Gemini file reference object instance.
		"""
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

		log.debug(
			f"Temporary file created for remote download at: {tmp_path} (Size: {len(response.content)} bytes)"
		)
		try:
			return await self._upload_and_wait(tmp_path, mime_type=mime_type)
		finally:
			tmp_file = Path(tmp_path)
			if tmp_file.exists():
				tmp_file.unlink()
				log.debug(f"Cleaned up temporary file: {tmp_path}")

	async def _process_input(self, item: Any) -> Any:
		"""
		Transform raw multi-modal inputs into Gemini Part objects or uploaded file targets.

		Args:
			item: URL string, file path, BytesIO stream, or raw byte sequence.

		Returns:
			Transformed payload representation ready for model context inclusion.
		"""
		log.debug(f"Processing input item of type: {type(item)}")
		if isinstance(item, str):
			if item.startswith(("http://", "https://")):
				log.debug(f"Input identified as remote URL: {item}")
				return await self._handle_remote_file(item)
			if Path(item).is_file():
				log.debug(f"Detected local file path: {item}")
				return await self._upload_and_wait(item)
			log.debug(
				f"Input string is neither a valid URL nor an existing local file: {item}"
			)

		if isinstance(item, (io.BytesIO, io.IOBase)):
			log.debug("Detected file-like input stream")

			item.seek(0)
			filename = getattr(item, "name", "file")
			mime_type, _ = mimetypes.guess_type(filename)
			data_bytes = item.read()
			log.debug(
				f"File-like input details - Name: {filename}, Guessed MIME: {mime_type}, Size: {len(data_bytes)} bytes"
			)

			return types.Part.from_bytes(
				data=data_bytes, mime_type=mime_type or "application/octet-stream"
			)

		if isinstance(item, bytes):
			log.debug(f"Detected raw bytes input of size: {len(item)} bytes")

			return types.Part.from_bytes(
				data=item, mime_type="application/octet-stream"
			)

		log.debug(
			f"Input passed through without specialized transformation: {type(item)}"
		)
		return item

	async def call(
		self, prompt: str, inputs: List[Any] | None = None
	) -> Tuple[bool, str]:
		"""
		Submit prompt text and attached context inputs to Gemini model endpoint.

		Args:
			prompt: The user text prompt string.
			inputs: Optional list of media inputs (URLs, paths, file streams, bytes).

		Returns:
			Tuple containing (success_boolean, output_text_response_or_error_msg).
		"""
		log.debug(
			f"call() invoked with prompt length: {len(prompt)} chars, inputs count: {len(inputs) if inputs else 0}"
		)
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
				log.debug(
					f"Finished processing all inputs in {time.time() - start_time:.2f}s"
				)

			payload = list(processed_parts) + [prompt]
			log.debug(
				f"Sending payload to Gemini API model '{self.model_name}' with total parts: {len(payload)}"
			)

			api_start_time = time.time()
			response = await self.client.aio.models.generate_content(
				model=self.model_name, contents=payload, config=self.config
			)
			log.debug(
				f"Gemini API response received in {time.time() - api_start_time:.2f}s"
			)

			if response.candidates and len(response.candidates) > 0:
				log.debug(
					f"Content generation successful. Candidate count: {len(response.candidates)}"
				)
				if not response.text:
					log.warning(
						"AI sent a candidate response, but response.text is null/empty"
					)
					return False, "AI sent a null response"
				log.debug(f"Response text length: {len(response.text)} chars")
				return True, response.text

			log.warning("AI returned no candidates or content structure empty")
			return False, "AI returned no content."

		except APIError as e:
			log.debug(
				f"APIError caught in call() with code: {e.code}, message: {e.message}"
			)
			if e.code == 429:
				cooldown_seconds = 20.0
				log.warning("Rate limit (429) hit, parsing details for retry delay")

				try:
					details: List[Dict[str, Any]] = getattr(e, "details", []) or []
					for detail in details:
						if isinstance(detail, dict) and "retryDelay" in detail:
							cooldown_seconds = float(
								str(detail["retryDelay"]).rstrip("s")
							)
							log.debug(
								f"Extracted custom retryDelay: {cooldown_seconds}s"
							)
							break
				except Exception:
					log.debug(
						"Failed to parse custom retryDelay from error details, using default",
						exc_info=True,
					)

				self.set_cooldown(cooldown_seconds)
				return (
					False,
					f"Rate limit reached (429). Retry after {cooldown_seconds}s",
				)

			elif e.code in (401, 403):
				log.error(f"Auth error (Code {e.code}). Key might be invalid.")
				return False, f"Authentication error: {e.message}"

			log.error(f"Gemini API error occurred (Status {e.code}): {e}")
			return False, f"API Error ({e.code}): {e.message}"

		except Exception as e:
			log.error("Unexpected error during call execution", exc_info=True)
			return False, f"Utility Error: {str(e)}"
