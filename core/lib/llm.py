import asyncio
import logging
import os
import pathlib
import tempfile
from typing      import Tuple, List, Optional, Union, Any

import httpx
from google      import generativeai as genai


log = logging.getLogger(__name__)


async def validate_key(api_key: str) -> bool:
	try:
		genai.configure(api_key=api_key)
		await asyncio.to_thread(genai.list_models)
		return True
	except Exception:
		log.error(f"API key validation failed", exc_info=True)
		return False

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
		genai.configure(api_key=api_key)
		self.model = genai.GenerativeModel(
			model_name=model_name,
			generation_config={
				"temperature": temperature,
				"top_p": top_p,
				"top_k": top_k,
			},
			system_instruction=system_instruction
		)

	@staticmethod
	async def _upload_and_wait(path: str) -> Any:
		log.info(f"Uploading file: {path}")
		file_obj = await asyncio.to_thread(genai.upload_file, path=path)
		log.debug(f"File uploaded, initial state: {file_obj.state.name}")

		while file_obj.state.name == "PROCESSING":
			log.debug(f"Waiting for file {file_obj.name} to process...")
			await asyncio.sleep(1)
			file_obj = await asyncio.to_thread(genai.get_file, file_obj.name)

		if file_obj.state.name == "FAILED":
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
			if os.path.exists(tmp_path):
				os.remove(tmp_path)
				log.debug(f"Cleaned up temporary file: {tmp_path}")

	async def _process_input(self, item: Any) -> Any:
		if isinstance(item, str):
			if item.startswith(("http://", "https://")):
				return await self._handle_remote_file(item)
			if pathlib.Path(item).is_file():
				log.debug(f"Detected local file path: {item}")
				return await self._upload_and_wait(item)
		
		if isinstance(item, bytes):
			log.debug("Detected raw bytes input")
			return {"mime_type": "application/octet-stream", "data": item}
			
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
			response = await self.model.generate_content_async(payload)
			
			if response.candidates and len(response.candidates) > 0:
				log.info("Content generation successful")
				return True, response.text
			
			log.warning("AI returned no candidates or content")
			return False, "AI returned no content."

		except Exception as e:
			log.error("Error during call execution", exc_info=True)
			return False, f"Utility Error: {str(e)}"
