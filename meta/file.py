import asyncio
import logging
import os

from core.lib.bttrdict  import BD, Method


log = logging.getLogger(__name__)

join = os.path.join


base = BD(
	data             = join("data", ""),
	logs             = join("logs", ""),
	meta             = join("meta", ""),
	core             = join("core", "")
)

sub = BD(
	env              = join(base.meta, ".env"),
	bin              = join(base.data, "bin", ""),
	glob             = join(base.data, "global", ""),
	servers          = join(base.data, "servers", ""),
	users            = join(base.data, "users", ""),

	cog              = join(base.core, "cog", ""),
	custom_cogs      = lambda i: join(sub.servers, i, "custom_cogs", "")
)

file = BD(
	server = BD(
		settings     = lambda i: join(sub.servers, i, "settings.json"),
		ai_data      = lambda i: join(sub.servers, i, "ai_data.json"),
		delete_time  = lambda i: join(sub.bin, i, "delete_time.json"),

		commands     = lambda i: join(sub.custom_cogs(i), "commands.py"),
		events       = lambda i: join(sub.custom_cogs(i), "events.py"),
		data         = lambda i: join(sub.custom_cogs(i), "data.json")
	),

	user = BD(
		settings     = lambda i: join(sub.users, i, "settings.json"),
		ai_data      = lambda i: join(sub.users, i, "ai_data.json"),
		delete_time  = lambda i: join(sub.bin, i, "delete_time.json")
	),

	glob = BD(
		blacklist    = join(sub.glob, "blacklist.json"),
		bot_obj      = join(sub.glob, "bot_info.json"),
		bot_activity = join(sub.glob, "bot_activity.json"),
		server_list  = join(sub.glob, "server_list.json")
	),

	sys_inst         = join(base.meta, "system_instructions.txt")
)


class CreatePath:
	@staticmethod
	def _touch_file(path) -> None:
		with open(path, mode='a'):
			pass

	async def process_path(self, path: str) -> None:
		is_folder = path.endswith(os.sep) or path.endswith('/')
		
		if is_folder:
			dir_to_create = path
			is_file = False
		else:
			dir_to_create = os.path.dirname(path)
			is_file = True

		try:
			if dir_to_create and not os.path.exists(dir_to_create):
				log.debug(f"Creating directory: {dir_to_create}")
				await asyncio.to_thread(os.makedirs, dir_to_create, exist_ok=True)

			if is_file:
				log.debug(f"Touching file: {path}")
				await asyncio.to_thread(self._touch_file, path)
		except Exception:
			log.error(f"An unexpected error occurred while processing {path}", exc_info=True)

	async def __call__(self, *paths: str) -> None:
		log.debug(f"Starting path processing for {len(paths)} paths.")
		tasks = [self.process_path(p) for p in paths]
		await asyncio.gather(*tasks)
		log.debug("Path processing batch complete.")
create_path = CreatePath()

def setup_directory() -> None:
	log.info("Initializing filesystem setup...")
	asyncio.run(create_path(
		base.data,
		base.logs,

		sub.servers,
		sub.users,
		sub.bin,
		sub.glob,

		file.glob.blacklist,
		file.glob.bot_activity
	))
	log.info("Filesystem setup complete.")

base.freeze()
sub.freeze()
file.freeze()


__all__ = (
	'setup_directory', 'create_path',
	'base', 'sub', 'file'
)