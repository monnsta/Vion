import logging
from pathlib import Path
from typing import Any

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


class Memory(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("memory", config.max_memory, entity_type)

	async def add(self, entity_id: int, message) -> bool:
		try:
			entry = await convert_message(message)
			success, data = await self._load(entity_id)
			if not success:
				return False

			items = self._get_list(data)
			items.append(entry)
			data[self.key] = self._trim(items)

			await self._save(entity_id, data)
			log.debug(f"Added memory entry for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(f"Error adding memory for {self.entity_type} {entity_id}: {e}")
			return False

class Audit(_EntityListStore):
	def __init__(self, entity_type="guild"):
		super().__init__("audit", config.max_audit, entity_type)

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


guild_memory = Memory(entity_type="guild")
guild_audit = Audit(entity_type="guild")
guild_response = Response(entity_type="guild")

user_memory = Memory(entity_type="user")
user_response = Response(entity_type="user")


__all__ = ('guild_memory', 'guild_audit', 'guild_response', 'user_memory', 'user_response')
