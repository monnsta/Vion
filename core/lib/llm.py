import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Tuple, List, Optional, Union, Any

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
		if e.code in (400, 401, 403):
			log.error(f"API key validation failed: {e}")
			return False
		elif e.code in (500, 503, 504):
			log.warning(f"Validation inconclusive due to network/service error: {e}")
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
		system_instruction: Optional[str] = None,
		temperature: float = 0.6,
		top_p: float = 1.0,
		top_k: int = 45
	):
		log.debug(f"Initializing GenerateContent with model: {model_name}")
		self.client = genai.Client(api_key=api_key)
		self.model_name = model_name

		self.config = types.GenerateContentConfig(
			temperature=temperature,
			top_p=top_p,
			top_k=top_k,
			system_instruction=system_instruction
		)

	async def _upload_and_wait(self, path: str) -> Any:
		log.info(f"Uploading file: {path}")
		file_obj = await self.client.aio.files.upload(file=Path(path))
		log.debug(f"File uploaded, initial state: {file_obj.state}")

		while file_obj.state == "PROCESSING":
			log.debug(f"Waiting for file {file_obj.name} to process...")
			await asyncio.sleep(1)
			file_obj = await self.client.aio.files.get(name=file_obj.name)

		if file_obj.state == "FAILED":
			log.error(f"File processing failed for: {file_obj.name}")
			raise RuntimeError(f"File {file_obj.name} failed to process.")

		log.info(f"File processing complete: {file_obj.name}")
		return file_obj

	async def _handle_remote_file(self, url: str) -> Any:
		log.info(f"Downloading remote file: {url}")
		async with httpx.AsyncClient(follow_redirects=True) as client:
			response = await client.get(url)
			response.raise_for_status()

			with tempfile.NamedTemporaryFile(delete=False) as tmp:
				tmp.write(response.content)
				tmp_path = tmp.name

		log.debug(f"Temporary file created at: {tmp_path}")
		try:
			return await self._upload_and_wait(tmp_path)
		finally:
			tmp_file = Path(tmp_path)
			if tmp_file.exists():
				tmp_file.unlink()
				log.debug(f"Cleaned up temporary file: {tmp_path}")

	async def _process_input(self, item: Any) -> Any:
		if isinstance(item, str):
			if item.startswith(("http://", "https://")):
				return await self._handle_remote_file(item)
			if Path(item).is_file():
				log.debug(f"Detected local file path: {item}")
				return await self._upload_and_wait(item)

		if isinstance(item, bytes):
			log.debug("Detected raw bytes input")
			return types.Part.from_bytes(data=item, mime_type="application/octet-stream")

		return item

	async def call(self, prompt: str, inputs: Optional[List[Any]] = None) -> Tuple[bool, str]:
		log.info("Starting content generation call")
		try:
			processed_parts = []
			if inputs:
				log.debug(f"Processing {len(inputs)} input items")
				processed_parts = await asyncio.gather(
					*[self._process_input(i) for i in inputs]
				)

			payload = processed_parts + [prompt]
			log.debug("Sending payload to Gemini API")

			response = await self.client.aio.models.generate_content(
				model=self.model_name,
				contents=payload,
				config=self.config
			)

			if response.candidates and len(response.candidates) > 0:
				log.info("Content generation successful")
				return True, response.text

			log.warning("AI returned no candidates or content")
			return False, "AI returned no content."

		except Exception as e:
			log.error("Error during call execution", exc_info=True)
			return False, f"Utility Error: {str(e)}"


__all__ = ('validate_key', 'GenerateContent')
