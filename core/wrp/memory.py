import logging
from pathlib import Path
from typing import Any

import discord

from core.lib.converter import convert_message
from core.lib.file import json_file
from meta import config, file


log = logging.getLogger(__name__)


class _EntityListStore:
	def __init__(self, key: str, max_items: int, entity_type: str = "guild"):
		self.key = key
		self.max_items = max_items
		self.entity_type = entity_type

	def _path(self, entity_id: int) -> Path:
		if self.entity_type == "global":
			return file.glob.ai_data

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

	def _trim(self, items: list[Any]) -> list[Any]:
		if len(items) > self.max_items:
			log.debug(f"Trimming {self.key} list: {len(items)} -> {self.max_items}")
			return items[-self.max_items:]
		return items

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
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added STM entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding STM for {self.entity_type} {entity_id}: {e}")
			return False

class LTM(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("ltm", config.max_ltm, entity_type)

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

	async def add(self, entity_id: int, event) -> bool:
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(event)
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
			"guild_audit": [],
			"global_stm": [],
			"global_ltm": [],
			"guild_stm": [],
			"guild_ltm": [],
			"user_stm": [],
			"user_ltm": []
		}

		_, cluster["global_stm"] = await global_stm.get(0)
		_, cluster["global_ltm"] = await global_ltm.get(0)

		if guild:
			_, cluster["guild_audit"] = await guild_audit.get(guild.id)
			_, cluster["guild_stm"] = await guild_stm.get(guild.id)
			_, cluster["guild_ltm"] = await guild_ltm.get(guild.id)

		if user:
			_, cluster["user_stm"] = await user_stm.get(user.id)
			_, cluster["user_ltm"] = await user_ltm.get(user.id)

		return cluster


global_stm = STM(entity_type="global")
global_ltm = LTM(entity_type="global")

guild_stm = STM(entity_type="guild")
guild_ltm = LTM(entity_type="guild")
guild_audit = Audit(entity_type="guild")
guild_response = Response(entity_type="guild")

user_stm = STM(entity_type="user")
user_ltm = LTM(entity_type="user")
user_response = Response(entity_type="user")


__all__ = (
	'global_stm', 'global_ltm',
	'guild_stm', 'guild_ltm', 'guild_audit', 'guild_response',
	'user_stm', 'user_ltm', 'user_response', 'MemoryCluster'
)
