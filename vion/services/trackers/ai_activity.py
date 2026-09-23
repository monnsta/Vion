"""
AI activity logging module.

Handles tracking interaction metrics across global, guild, and user scopes,
generating stats, ranks, and leaderboards.
"""

import copy
from datetime import datetime, timezone
from typing import Literal

from vion.infrastructure.file import json_file
from vion.config import storage

from .base import BaseTracker


class Activity(BaseTracker):
	"""
	Tracks AI interactions and builds timeline analytics across different scopes.
	"""

	def __init__(self):
		"""Initialize Activity tracker with default storage path and metric templates."""
		super().__init__(storage.shared.activity)
		self._template = {"interactions": 0, "timeline": {}}

	async def log_activity(self, guild_id: int | None, user_id: int | None) -> None:
		"""
		Log an interaction event and increment timeline counters.

		Args:
			guild_id: Optional target guild snowflake ID.
			user_id: Optional target user snowflake ID.
		"""
		time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00")

		async with json_file.edit(self.file_path) as data:
			if "global" not in data:
				data["global"] = copy.deepcopy(self._template)
			data.setdefault("guilds", {})
			data.setdefault("users", {})

			targets = [("global", "global")]
			if guild_id:
				targets.append(("guilds", str(guild_id)))
			if user_id:
				targets.append(("users", str(user_id)))

			for category, key in targets:
				if category == "global":
					target_dict = data["global"]
				else:
					if key not in data[category]:
						data[category][key] = copy.deepcopy(self._template)
					target_dict = data[category][key]

				if "timeline" not in target_dict:
					target_dict["timeline"] = {}

				target_dict["interactions"] += 1

				if time_str not in target_dict["timeline"]:
					target_dict["timeline"][time_str] = 0
				target_dict["timeline"][time_str] += 1

	async def get_stats(
		self,
		target_type: Literal["global", "guild", "user"],
		target_id: int | None = None,
	) -> dict:
		"""
		Retrieve interaction statistics and optional ranking for a target scope.

		Args:
			target_type: Scope type ('global', 'guild', or 'user').
			target_id: Optional target snowflake ID for 'guild' or 'user'.

		Returns:
			Dictionary containing interaction stats and rank position if applicable.
		"""
		data = await self.get_all()

		if target_type == "global":
			return copy.deepcopy(data.get("global", self._template))

		category = "guilds" if target_type == "guild" else "users"
		items = data.get(category, {})
		target_stats = copy.deepcopy(items.get(str(target_id), self._template))

		sorted_items = sorted(
			items.items(), key=lambda x: x[1].get("interactions", 0), reverse=True
		)
		rank = 0
		for idx, (item_id, _) in enumerate(sorted_items, start=1):
			if str(item_id) == str(target_id):
				rank = idx
				break

		target_stats["rank"] = rank if rank > 0 else len(items) + 1
		return target_stats

	async def get_leaderboard(
		self, target_type: Literal["guild", "user"], limit: int = 10
	) -> list[tuple[str, int]]:
		"""
		Retrieve ranked list of top interactive targets.

		Args:
			target_type: Scope type ('guild' or 'user').
			limit: Maximum number of entries to return. Defaults to 10.

		Returns:
			List of tuples containing (target_id_str, total_interactions).
		"""
		data = await self.get_all()
		category = "guilds" if target_type == "guild" else "users"
		items = data.get(category, {})

		sorted_items = sorted(
			items.items(), key=lambda x: x[1].get("interactions", 0), reverse=True
		)
		return [
			(item_id, stats.get("interactions", 0))
			for item_id, stats in sorted_items[:limit]
		]
