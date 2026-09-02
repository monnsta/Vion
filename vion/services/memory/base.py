import logging
from pathlib import Path
from typing import Any

from infrastructure.file import json_file
from config import storage


log = logging.getLogger("memory")


class EntityListStore:
	def __init__(self, key: str, max_items: int, entity_type: str = "guild"):
		self.key = key
		self.max_items = max_items
		self.entity_type = entity_type

	def _path(self, entity_id: int) -> Path:
		if self.entity_type == "global":
			return storage.shared.ai_data

		eid = str(entity_id)
		if self.entity_type == "guild":
			return storage.guilds.ai_data(eid)
		elif self.entity_type == "user":
			return storage.guilds.ai_data(eid)
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
