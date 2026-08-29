import logging
import sys
from pathlib import Path

from infrastructure.file import create_path
from .dataclasses import (
	DirectoryPaths,
	Shared,
	Guild,
	User,
	Storage
)


log = logging.getLogger("config")


def build_storage_registry(root_path: Path) -> Storage:
	data_dir = root_path / "data"

	dirs = DirectoryPaths(
		root = root_path,
		data = data_dir,
		logs = root_path / "logs",
		cogs = root_path / "extensions",
		trash = data_dir / "trash",
		shared = data_dir / "global",
		guilds = data_dir / "servers",
		users = data_dir / "users",
		custom_cog_dir_name = "cog",
	)

	shared = Shared(
		blacklist = dirs.shared / "blacklist.json",
		activity = dirs.shared / "bot_activity.json",
		notif = dirs.shared / "bot_notif.json",
		runtime = dirs.shared / "bot_runtime.json",
		ai_data = dirs.shared / "ai_data.json",
	)

	guilds = Guild(
		dirs = dirs,
		base_dir = dirs.guilds,

		settings_filename = "settings.json",
		ai_data_filename = "ai_data.json",
		delete_time_filename = "delete_time.json",
		custom_cog_filename = "__init__.py",
		custom_cog_data_filename = "data.json",
	)

	users = User(
		dirs = dirs,
		base_dir = dirs.users,

		settings_filename = "settings.json",
		ai_data_filename = "ai_data.json",
		delete_time_filename = "delete_time.json",
	)

	return Storage(
		dirs=dirs,

		env=root_path / ".env",
		config=root_path / "config.yml",
		shared=shared,
		guilds=guilds,
		users=users,
	)


ROOT = Path(__file__).resolve().parent.parent

storage = build_storage_registry(ROOT)


async def validate_paths() -> None:
	critical_files = (
		storage.env,
		storage.config,
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
		(storage.dirs.data, True),
		(storage.dirs.logs, True),
		(storage.dirs.guilds, True),
		(storage.dirs.users, True),
		(storage.dirs.trash, True),
		(storage.dirs.shared, True),

		storage.shared.blacklist,
		storage.shared.activity,
		storage.shared.notif,
		storage.shared.runtime,
		storage.shared.ai_data,
	)
