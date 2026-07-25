import asyncio
import copy
from datetime import datetime
from typing import Literal

from core.lib.file import json_file
from meta import file


class AIActivityTracker:
	def __init__(self):
		self.file_path = file.glob.bot_activity
		self._lock = asyncio.Lock()

		self._template = {
			"interactions": 0,
			"timeline": {}
		}

	async def _load(self) -> dict:
		success, data = await json_file.load(self.file_path)
		if not success or not isinstance(data, dict):
			data = {}

		if "global" not in data:
			data["global"] = copy.deepcopy(self._template)
		data.setdefault("guilds", {})
		data.setdefault("users", {})

		return data

	async def _save(self, data: dict) -> None:
		await json_file.save(self.file_path, data)

	async def log_activity(
		self,
		guild_id: int | None,
		user_id: int | None
	) -> None:
		time_str = datetime.now().strftime("%Y-%m-%d %H:00")

		async with self._lock:
			data = await self._load()

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

			await self._save(data)

	async def get_stats(self, target_type: Literal['global', 'guild', 'user'], target_id: int | None = None) -> dict:
		data = await self._load()

		if target_type == 'global':
			return copy.deepcopy(data.get("global", self._template))

		category = "guilds" if target_type == 'guild' else "users"
		items = data.get(category, {})
		target_stats = copy.deepcopy(items.get(str(target_id), self._template))

		sorted_items = sorted(items.items(), key=lambda x: x[1].get("interactions", 0), reverse=True)
		rank = 0
		for idx, (item_id, _) in enumerate(sorted_items, start=1):
			if str(item_id) == str(target_id):
				rank = idx
				break

		target_stats["rank"] = rank if rank > 0 else len(items) + 1
		return target_stats

	async def get_leaderboard(self, target_type: Literal['guild', 'user'], limit: int = 10) -> list[tuple[str, int]]:
		data = await self._load()
		category = "guilds" if target_type == 'guild' else "users"
		items = data.get(category, {})

		sorted_items = sorted(items.items(), key=lambda x: x[1].get("interactions", 0), reverse=True)
		return [(item_id, stats.get("interactions", 0)) for item_id, stats in sorted_items[:limit]]


tracker = AIActivityTracker()
