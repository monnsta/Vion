import logging
import asyncio
from pathlib import Path
from typing import Any

import discord

from core.lib.converter import convert_message
from core.lib.llm import GenerateContent
from core.lib.file import json_file
from meta import config, file


log = logging.getLogger(__name__)


class _EntityListStore:
	def __init__(self, key: str, max_items: int, entity_type: str = "guild"):
		self.key = key
		self.max_items = max_items
		self.entity_type = entity_type

	def _path(self, entity_id: int) -> Path:
		eid = str(entity_id)
		if self.entity_type == "guild":
			return file.server.ai_data(eid)
		elif self.entity_type == "user":
			return file.user.ai_data(eid)
		else:
			log.error(f"Unknown entity type encountered: {self.entity_type}")
			raise ValueError(f"Unknown entity type: {self.entity_type}")

	async def _load(self, entity_id: int) -> tuple[bool, dict]:
		log.debug(f"Loading {self.key} for {self.entity_type} {entity_id}")
		return await json_file.load(self._path(entity_id))

	async def _save(self, entity_id: int, data: dict) -> None:
		log.debug(f"Saving {self.key} for {self.entity_type} {entity_id}")
		await json_file.save(self._path(entity_id), data)

	def _get_list(self, data: dict) -> list[Any]:
		return data.setdefault(self.key, [])

	async def get(self, entity_id: int) -> tuple[bool, list[Any]]:
		try:
			success, data = await self._load(entity_id)
			if not success:
				log.warning(f"Failed to load data for {self.entity_type} {entity_id} while getting {self.key}")
				return False, []
			log.debug(f"Loaded {self.key} for {self.entity_type} {entity_id}")
			return True, data.get(self.key, [])
		except Exception as e:
			log.error(f"Error retrieving {self.key} for {self.entity_type} {entity_id}: {e}", exc_info=True)
			return False, []

	async def clear(self, entity_id: int) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False
			data[self.key] = []
			await self._save(entity_id, data)
			log.debug(f"Cleared {self.key} for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error clearing {self.key} for {self.entity_type} {entity_id}: {e}")
			return False


class STM(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("stm", config.max_stm, entity_type)

	async def _summarize_and_store(self, entity_id: int, dropped_items: list):
		try:
			log.info(f"Summarizing {len(dropped_items)} old STM entries for {self.entity_type} {entity_id}")
			llm = GenerateContent(
				api_key=config.secrets.gemini_api_key[0],
				model_name=config.gemini_models[0],
				system_instruction=config.summary_instructions
			)
			text_to_summarize = "\n".join(dropped_items)
			success, summary = await llm.call(f"Summarize the following past interactions concisely:\n{text_to_summarize}")

			if success and summary:
				final_note = f"[Auto-Summarized] {summary.strip()}"
				ltm = LTM(self.entity_type)
				await ltm.add(entity_id, final_note)
				log.info(f"Successfully auto-summarized and saved to LTM for {self.entity_type} {entity_id}")
			else:
				log.warning(f"Failed to summarize STM entries for {self.entity_type} {entity_id}")
		except Exception as e:
			log.error(f"Error during auto-summarization for {self.entity_type} {entity_id}: {e}", exc_info=True)


	async def add(self, entity_id: int, message) -> bool:
		try:
			entry = await convert_message(message)

			context_tag = ""
			if hasattr(message, "guild") and message.guild:
				context_tag = f"[Guild: {message.guild.name} | Channel: #{message.channel.name}]"
			elif hasattr(message, "channel") and isinstance(message.channel, discord.DMChannel):
				context_tag = "[Direct Message]"

			if isinstance(entry, dict):
				entry["_context"] = context_tag
			elif isinstance(entry, str) and context_tag:
				entry = f"{context_tag} {entry}"

			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(entry)

			if len(items) > self.max_items:
				dropped = items[:-self.max_items]
				items = items[-self.max_items:]
				asyncio.create_task(self._summarize_and_store(entity_id, dropped))

			data[self.key] = items

			await self._save(entity_id, data)
			log.debug(f"Added STM entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding STM for {self.entity_type} {entity_id}: {e}")
			return False

class LTM(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("ltm", config.max_ltm, entity_type)

	def _trim(self, items: list[Any]) -> list[Any]:
		if len(items) > self.max_items:
			log.debug(f"Trimming {self.key} list: {len(items)} -> {self.max_items}")
			return items[-self.max_items:]
		return items

	async def add(self, entity_id: int, note: str) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(note)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added LTM entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding LTM for {self.entity_type} {entity_id}: {e}")
			return False

class Audit(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("audit", config.max_audit, entity_type)

	def _trim(self, items: list[Any]) -> list[Any]:
		if len(items) > self.max_items:
			log.debug(f"Trimming {self.key} list: {len(items)} -> {self.max_items}")
			return items[-self.max_items:]
		return items

	async def add(self, entity_id: int, event) -> bool:
		try:
			entry = await convert_message(event)
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(entry)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added audit entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding audit for {self.entity_type} {entity_id}: {e}")
			return False

class Response(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("previous_response", config.max_previous_response, entity_type)

	def _trim(self, items: list[Any]) -> list[Any]:
		if len(items) > self.max_items:
			log.debug(f"Trimming {self.key} list: {len(items)} -> {self.max_items}")
			return items[-self.max_items:]
		return items

	async def add(self, entity_id: int, response_text: str) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(response_text)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added previous response entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding response for {self.entity_type} {entity_id}: {e}")
			return False


class MemoryCluster:
	@staticmethod
	async def build(guild: discord.Guild | None, user: discord.User | discord.Member | None) -> dict:
		cluster = {
			"guild_stm": [],
			"guild_ltm": [],
			"user_stm": [],
			"user_ltm": []
		}

		if guild:
			_, cluster["guild_stm"] = await guild_stm.get(guild.id)
			_, cluster["guild_ltm"] = await guild_ltm.get(guild.id)

		if user:
			_, cluster["user_stm"] = await user_stm.get(user.id)
			_, cluster["user_ltm"] = await user_ltm.get(user.id)

		return cluster


guild_stm = STM(entity_type="guild")
guild_ltm = LTM(entity_type="guild")
guild_audit = Audit(entity_type="guild")
guild_response = Response(entity_type="guild")

user_stm = STM(entity_type="user")
user_ltm = LTM(entity_type="user")
user_response = Response(entity_type="user")


__all__ = (
	'guild_stm', 'guild_ltm', 'guild_audit', 'guild_response',
	'user_stm', 'user_ltm', 'user_response', 'MemoryCluster'
)
