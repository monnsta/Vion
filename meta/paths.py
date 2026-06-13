import asyncio
import logging
import os
from pathlib import Path

from core.lib.bttrdict import BD, Method


log = logging.getLogger(__name__)

root = Path(__file__).resolve().parent.parent


base = BD(
	data	= root / "data",
	logs	= root / "logs",
	meta	= root / "meta",
	core	= root / "core"

)

sub = BD(
	trash  	= base.data / "trash",
	glob   	= base.data / "global",
	servers	= base.data / "servers",
	users  	= base.data / "users",
	cog    	= base.core / "cog",

	custom_cogs	= Method(lambda self, i: self.servers / i / "cog")
)

file = BD(
	server = BD(
		settings   	= lambda i: sub.servers / i / "settings.json",
		ai_data    	= lambda i: sub.servers / i / "ai_data.json",
		delete_time	= lambda i: sub.trash   / i / "delete_time.json",

		cog 	= lambda i: sub.custom_cogs(i) / "__init__.py",
		data	= lambda i: sub.custom_cogs(i) / "data.json"
	),

	user = BD(
		settings   	= lambda i: sub.users / i / "settings.json",
		ai_data    	= lambda i: sub.users / i / "ai_data.json",
		delete_time	= lambda i: sub.trash / i / "delete_time.json"
	),

	glob = BD(
		blacklist   	= sub.glob / "blacklist.json",
		bot_obj     	= sub.glob / "bot_info.json",
		bot_activity	= sub.glob / "bot_activity.json"
	),

	env 	= root / ".env",
	conf	= root / "configure.ial"
)


class CreatePath:
	async def process_path(self, path: str | Path, is_dir: bool = False) -> None:
		path_obj = Path(path)

		if is_dir:
			dir_to_create = path_obj
		else:
			dir_to_create = path_obj.parent

		try:
			if dir_to_create and not dir_to_create.exists():
				log.debug(f"Creating directory: {dir_to_create}")
				await asyncio.to_thread(dir_to_create.mkdir, parents=True, exist_ok=True)

			if not is_dir:
				log.debug(f"Touching file: {path_obj}")
				await asyncio.to_thread(path_obj.touch, exist_ok=True)
		except Exception:
			log.error(f"An unexpected error occurred while processing {path}", exc_info=True)

	async def __call__(self, *paths: tuple[str | Path, bool] | str | Path) -> None:
		log.debug(f"Starting path processing for {len(paths)} paths.")
		tasks = []
		for path in paths:
			if isinstance(path, tuple):
				tasks.append(self.process_path(*path))
			else:
				tasks.append(self.process_path(path))
		await asyncio.gather(*tasks)
		log.debug("Path processing batch complete.")
create_path = CreatePath()

def setup_directory() -> None:
	log.info("Initializing filesystem setup...")

	asyncio.run(create_path(
		(base.data,   True),
		(base.logs,   True),
		(sub.servers, True),
		(sub.users,   True),
		(sub.trash,   True),
		(sub.glob,    True),

		file.glob.blacklist,
		file.glob.bot_activity
	))

	log.info("Filesystem setup complete.")

for obj in (base, sub, file): obj.freeze()


__all__ = (
	'setup_directory', 'create_path',
	'base', 'sub', 'file'
)
