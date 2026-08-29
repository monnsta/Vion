from typing import Any

from config import config


async def load_settings(manager: Any, target_id: int, scope: str) -> dict:
	success, data = await manager.settings.load(target_id)
	if success:
		return data
	return config.settings.get(scope, {})
