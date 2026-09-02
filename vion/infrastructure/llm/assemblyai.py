"""
AssemblyAI transcription client service wrapper.

Handles file/stream processing, audio upload, and asynchronous status polling.
"""

import asyncio
import io
import logging
from pathlib import Path
from typing import Tuple, Any

import httpx


log = logging.getLogger("llm")


class AssemblyAITranscriber:
	"""
	Asynchronous client for AssemblyAI speech-to-text API.

	Attributes:
		api_key: AssemblyAI authorization key string.
		base_url: Base endpoint URL string for the AssemblyAI API.
		headers: HTTP request headers configured with authorization key.
		config: Additional task payload configuration dictionary.
	"""

	def __init__(self, api_key: str, **config_kwargs: Any) -> None:
		"""
		Initialize the AssemblyAITranscriber instance.

		Args:
			api_key: Authentication API key.
			**config_kwargs: Extra payload parameters forwarded to transcription API.
		"""
		log.debug("Initializing AssemblyAITranscriber")
		self.api_key = api_key
		self.base_url = "https://api.assemblyai.com/v2"
		self.headers = {"authorization": self.api_key}
		self.config = config_kwargs

	async def _upload_data(self, data: bytes) -> str:
		"""
		Upload raw audio byte stream to AssemblyAI staging storage.

		Args:
			data: Raw audio binary bytes payload.

		Returns:
			Target remote upload URL string.

		Raises:
			httpx.HTTPStatusError: If remote upload request fails.
		"""
		log.debug(f"Uploading raw data of size {len(data)} bytes to AssemblyAI")
		async with httpx.AsyncClient(timeout=None) as client:
			response = await client.post(
				f"{self.base_url}/upload",
				headers=self.headers,
				content=data
			)
			response.raise_for_status()
			upload_url = str(response.json().get("upload_url"))
			log.debug("Data uploaded successfully, received upload URL")
			return upload_url

	async def _process_input(self, item: Any) -> str:
		"""
		Parse and resolve raw input payload into a remote processable URL string.

		Args:
			item: URL string, local file path, file stream, or raw bytes.

		Returns:
			AssemblyAI readable remote resource URL string.

		Raises:
			ValueError: If input format or data type is unsupported.
		"""
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
		"""
		Submit an audio object for processing and poll until completion.

		Args:
			item: Source audio object (URL string, Path, Stream, or bytes).

		Returns:
			Tuple containing (success_boolean, transcribed_text_or_error_message).
		"""
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
