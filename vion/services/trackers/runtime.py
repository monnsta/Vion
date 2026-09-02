from datetime import datetime, timezone
from typing import Literal

from infrastructure.file import json_file
from config import storage

from .base import BaseTracker


class Runtime(BaseTracker):
    def __init__(self):
        super().__init__(storage.shared.runtime)

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

