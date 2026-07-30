import copy
from datetime import datetime, timezone
from typing import Literal

from core.lib.file import json_file
from meta import file


class BaseTracker:
    def __init__(self, file_path):
        self.file_path = file_path

    async def get_all(self) -> dict:
        success, data = await json_file.load(self.file_path)
        return data if success and isinstance(data, dict) else {}


class Activity(BaseTracker):
    def __init__(self):
        super().__init__(file.glob.bot_activity)
        self._template = {
            "interactions": 0,
            "timeline": {}
        }

    async def log_activity(self, guild_id: int | None, user_id: int | None) -> None:
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

    async def get_stats(self, target_type: Literal['global', 'guild', 'user'], target_id: int | None = None) -> dict:
        data = await self.get_all()

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
        data = await self.get_all()
        category = "guilds" if target_type == 'guild' else "users"
        items = data.get(category, {})

        sorted_items = sorted(items.items(), key=lambda x: x[1].get("interactions", 0), reverse=True)
        return [(item_id, stats.get("interactions", 0)) for item_id, stats in sorted_items[:limit]]


class Notification(BaseTracker):
    def __init__(self, max_per_target: int = 25):
        super().__init__(file.glob.bot_notif)
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
        data = await self.get_all()
        return data.get(str(target_id), [])

    async def clear(self, target_id: int) -> None:
        async with json_file.edit(self.file_path) as data:
            tid = str(target_id)
            if tid in data:
                del data[tid]


class Runtime(BaseTracker):
    def __init__(self):
        super().__init__(file.glob.bot_runtime)

    async def mark_event(self, event_type: Literal['startup', 'shutdown', 'disconnect', 'resume']) -> None:
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
        async with json_file.edit(self.file_path) as data:
            for k, v in kwargs.items():
                data[k] = v

    async def get_last_offline(self) -> datetime | None:
        data = await self.get_all()
        
        disconnect_str = data.get("last_disconnect")
        shutdown_str = data.get("last_shutdown")
        
        times = []
        if disconnect_str:
            times.append(datetime.fromisoformat(disconnect_str))
        if shutdown_str:
            times.append(datetime.fromisoformat(shutdown_str))
            
        return max(times) if times else None


activity = Activity()
notif = Notification()
runtime = Runtime()


__all__ = ('activity', 'notif', 'runtime')
