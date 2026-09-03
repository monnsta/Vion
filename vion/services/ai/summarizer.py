"""
Text summarization module using LLM pipelines.
"""

import logging

from vion.infrastructure.llm import GenerateContent
from vion.config import config


log = logging.getLogger("ai")


class Summarizer:
	"""Handles text summarization requests across configured LLM fallback models."""

	def __init__(self) -> None:
		"""Initialize summarization models using keys and parameters from configuration."""
		log.info("Initializing Summarizer engine.")
		self.modules = [
			GenerateContent(
				k, m,
				config.summary_instructions,
				config.temperature,
				config.top_p, config.top_k
			)
			for m in config.gemini_models
			for k in config.secrets.gemini
		]

	async def summarize(self, text: str) -> str | None:
		"""
		Summarize the provided string using available LLM models.

		Args:
			text: String content to be summarized.

		Returns:
			Summarized text string if successful, None if empty or all models failed.
		"""
		if not text.strip():
			return None

		active_pipeline = [m for m in self.modules if not m.is_cooling_down]
		if not active_pipeline:
			log.warning("No active modules available for summarization.")
			return None

		for idx, model in enumerate(active_pipeline):
			log.debug(f"Attempting summarizer call (Index: {idx})")
			success, response = await model.call(text)
			if success and response:
				log.info("Summarization successfully completed.")
				return response.strip()

		log.warning("All summarizer models failed to produce a response.")
		return None
