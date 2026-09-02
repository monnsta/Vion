from datetime import datetime, timezone

from infrastructure.file import json_file
from config import storage

from .base import BaseTracker


class Notification(BaseTracker):
    def __init__(self, max_per_target: int = 25):
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
