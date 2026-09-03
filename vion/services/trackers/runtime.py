"""
Runtime analytics and lifecycle tracking module.

Monitors system connection events, startup/shutdown history, and uptime statistics.
"""

from datetime import datetime, timezone
from typing import Literal

from vion.infrastructure.file import json_file
from vion.config import storage

from .base import BaseTracker


class Runtime(BaseTracker):
	"""
	Tracks application lifecycle events and runtime states.
	"""

	def __init__(self):
		"""Initialize Runtime tracker with default storage path."""
		super().__init__(storage.shared.runtime)

	async def mark_event(self, event_type: Literal['startup', 'shutdown', 'disconnect', 'resume']) -> None:
		"""
		Record a lifecycle event and append to historical log.

		Args:
			event_type: Classification of the lifecycle event.
		"""
		async with json_file.edit(self.file_path) as data:
			now = datetime.now(timezone.utc).isoformat()

			data.setdefault("history", [])
			data.setdefault("total_starts", 0)
			data.setdefault("total_disconnects", 0)

			data[f"last_{event_type}"] = now

			if event_type == 'startup':
				data["total_starts"] += 1
			elif event_type == 'disconnect':
				data["total_disconnects"] += 1

			data["history"].append({"event": event_type, "timestamp": now})
			if len(data["history"]) > 50:
				data["history"] = data["history"][-50:]

	async def update_stats(self, **kwargs) -> None:
		"""
		Update arbitrary runtime statistics keys.

		Args:
			**kwargs: Key-value pairs to set in runtime data storage.
		"""
		async with json_file.edit(self.file_path) as data:
			for k, v in kwargs.items():
				data[k] = v

	async def get_last_offline(self) -> datetime | None:
		"""
		Calculate the most recent offline timestamp from disconnect or shutdown records.

		Returns:
			Datetime object of latest offline state, or None if no timestamps recorded.
		"""
		data = await self.get_all()

		disconnect_str = data.get("last_disconnect")
		shutdown_str = data.get("last_shutdown")

		times = []
		if disconnect_str:
			times.append(datetime.fromisoformat(disconnect_str))
		if shutdown_str:
			times.append(datetime.fromisoformat(shutdown_str))

		return max(times) if times else None
