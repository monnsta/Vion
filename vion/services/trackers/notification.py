"""
Notification logging module.

Manages persistent alert queues and message event notifications per target ID.
"""

from datetime import datetime, timezone

from vion.infrastructure.file import json_file
from vion.config import storage

from .base import BaseTracker


class Notification(BaseTracker):
	"""
	Manages target-bound notification logs with automatic size capping.

	Attributes:
		max_per_target: Maximum retained notifications per target entry.
	"""

	def __init__(self, max_per_target: int = 25):
		"""
		Initialize Notification manager.

		Args:
			max_per_target: Max notifications per target ID. Defaults to 25.
		"""
		super().__init__(storage.shared.notif)
		self.max_per_target = max_per_target

	async def add(
		self,
		target_id: int,
		notif_type: str,
		author_id: int,
		author_name: str,
		channel_id: int,
		channel_name: str,
		message_id: int,
		content: str
	) -> None:
		"""
		Append a new notification entry for a target entity.

		Args:
			target_id: Target entity snowflake ID.
			notif_type: Event classification label.
			author_id: Author snowflake ID.
			author_name: Author username string.
			channel_id: Origin channel snowflake ID.
			channel_name: Origin channel name string.
			message_id: Origin message snowflake ID.
			content: Notification text body.
		"""
		async with json_file.edit(self.file_path) as data:
			tid = str(target_id)
			if tid not in data:
				data[tid] = []

			entry = {
				"type": notif_type,
				"author_id": author_id,
				"author_name": author_name,
				"channel_id": channel_id,
				"channel_name": channel_name,
				"message_id": message_id,
				"content": content,
				"timestamp": datetime.now(timezone.utc).isoformat()
			}

			data[tid].append(entry)
			if len(data[tid]) > self.max_per_target:
				data[tid] = data[tid][-self.max_per_target:]

	async def get(self, target_id: int) -> list[dict]:
		"""
		Retrieve all current notifications for a target entity.

		Args:
			target_id: Target entity snowflake ID.

		Returns:
			List of notification dictionaries.
		"""
		data = await self.get_all()
		return data.get(str(target_id), [])

	async def clear(self, target_id: int) -> None:
		"""
		Clear and delete all stored notifications for a target entity.

		Args:
			target_id: Target entity snowflake ID.
		"""
		async with json_file.edit(self.file_path) as data:
			tid = str(target_id)
			if tid in data:
				del data[tid]
