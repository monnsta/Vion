# Copyright (c) 2026 monnsta. All rights reserved.

import asyncio
import logging
import os
from pathlib import Path

from core.lib.dataclass import Data, Method, Computed


log = logging.getLogger(__name__)

root = Path(__file__).resolve().parent.parent


base = Data(
	core 	= root / "core",
	meta 	= root / "meta",
	asset	= Computed(lambda self: self.meta / "asset"),

	data	= root / "data",
	logs	= root / "logs",

)

sub = Data(
	trash  	= base.data / "trash",
	glob   	= base.data / "global",
	servers	= base.data / "servers",
	users  	= base.data / "users",

	cog   	= base.core / "cog",
	avatar	= base.asset / "avatars",

	custom_cogs	= Method(lambda self, i: self.servers / i / "cog")
)

file = Data(
	server = Data(
		settings   	= lambda i: sub.servers / i / "settings.json",
		ai_data    	= lambda i: sub.servers / i / "ai_data.json",
		delete_time	= lambda i: sub.trash   / i / "delete_time.json",

		cog 	= lambda i: sub.custom_cogs(i) / "__init__.py",
		data	= lambda i: sub.custom_cogs(i) / "data.json"
	),

	user = Data(
		settings   	= lambda i: sub.users / i / "settings.json",
		ai_data    	= lambda i: sub.users / i / "ai_data.json",
		delete_time	= lambda i: sub.trash / i / "delete_time.json"
	),

	glob = Data(
		blacklist   	= sub.glob / "blacklist.json",
		bot_activity	= sub.glob / "bot_activity.json"
	),

	env 	= root / ".env",
	conf	= root / "config.ial"
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


async def validate_paths():
	critical_files = (
		file.env,
		file.conf
	)

	missing_files = [f for f in critical_files if not f.exists()]

	if missing_files:
		for f in missing_files:
			log.critical(f"Missing important file: {f}")
		sys.exit(10)

async def setup_directory() -> None:
	await validate_paths()

	log.info("Initializing filesystem setup...")

	await create_path(
		(base.data,   True),
		(base.logs,   True),
		(sub.servers, True),
		(sub.users,   True),
		(sub.trash,   True),
		(sub.glob,    True),

		file.glob.blacklist,
		file.glob.bot_activity
	)


for obj in (base, sub, file): obj.freeze()
create_path = CreatePath()


__all__ = (
	'setup_directory', 'create_path',
	'base', 'sub', 'file'
)
