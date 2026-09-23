"""
Base classes for memory storage primitives.

Provides abstract and concrete storage handlers backed by persistent JSON file storage.
"""

import logging
from pathlib import Path
from typing import Any

from vion.infrastructure.file import json_file
from vion.config import storage


log = logging.getLogger("memory")


class EntityListStore:
	"""
	List-based data store bound to an entity type and scoped JSON storage path.

	Attributes:
		key: Key under which items are stored in the JSON file.
		max_items: Maximum capacity of the list before older items are trimmed.
		entity_type: Entity scope designation ('global', 'guild', or 'user').
	"""

	def __init__(self, key: str, max_items: int, entity_type: str = "guild"):
		"""
		Initialize an EntityListStore instance.

		Args:
			key: Storage dictionary key.
			max_items: Maximum allowed item limit.
			entity_type: Scope string ('global', 'guild', or 'user').
		"""
		self.key = key
		self.max_items = max_items
		self.entity_type = entity_type

	def _path(self, entity_id: int) -> Path:
		"""
		Resolve storage path for given entity ID based on configured type.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Resolved Path instance pointing to the entity's JSON store.

		Raises:
			ValueError: If an unknown entity type is configured.
		"""
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
		"""
		Load underlying JSON payload for entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, data_dict).
		"""
		log.debug(f"Loading {self.key} for {self.entity_type} {entity_id}")
		return await json_file.load(self._path(entity_id))

	async def _save(self, entity_id: int, data: dict) -> None:
		"""
		Persist JSON payload for entity.

		Args:
			entity_id: Target entity snowflake ID.
			data: Dictionary object to serialize.
		"""
		log.debug(f"Saving {self.key} for {self.entity_type} {entity_id}")
		await json_file.save(self._path(entity_id), data)

	def _get_list(self, data: dict) -> list[Any]:
		"""Retrieve or initialize list under configured key."""
		return data.setdefault(self.key, [])

	def _trim(self, items: list[Any]) -> list[Any]:
		"""Trim list to maximum allowed size keeping latest entries."""
		if len(items) > self.max_items:
			log.debug(f"Trimming {self.key} list: {len(items)} -> {self.max_items}")
			return items[-self.max_items :]
		return items

	async def get(self, entity_id: int) -> tuple[bool, list[Any]]:
		"""
		Retrieve stored item list for entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, items_list).
		"""
		try:
			success, data = await self._load(entity_id)
			if not success:
				log.warning(
					f"Failed to load data for {self.entity_type} {entity_id} while getting {self.key}"
				)
				return False, []
			log.debug(f"Loaded {self.key} for {self.entity_type} {entity_id}")
			return True, data.get(self.key, [])
		except Exception as e:
			log.error(
				f"Error retrieving {self.key} for {self.entity_type} {entity_id}: {e}",
				exc_info=True,
			)
			return False, []

	async def clear(self, entity_id: int) -> bool:
		"""
		Clear stored list entries for target entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			True if cleared and persisted successfully, False otherwise.
		"""
		try:
			success, data = await self._load(entity_id)
			if not success:
				return False
			data[self.key] = []
			await self._save(entity_id, data)
			log.debug(f"Cleared {self.key} for {self.entity_type} {entity_id}")
			return True
		except Exception as e:
			log.error(
				f"Error clearing {self.key} for {self.entity_type} {entity_id}: {e}"
			)
			return False
