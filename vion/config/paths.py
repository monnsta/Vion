"""
Path resolution and storage initialization manager.

Handles environment-based root resolution, storage object instantiation,
file verification, and target directory creation.
"""

import logging
import os
import sys
from pathlib import Path

from vion.infrastructure.file import create_path
from .dataclasses import (
	DirectoryPaths,
	Shared,
	Guild,
	User,
	Storage
)


log = logging.getLogger("config")

storage: Storage = Storage.__new__(Storage)
ROOT: Path | None = None


def resolve_root() -> Path:
	"""
	Resolve absolute root project directory path.

	Checks VION_ROOT_DIR environment variable first, falling back to parent folder.

	Returns:
		Resolved absolute Path instance.
	"""
	env_path = os.getenv("VION_ROOT_DIR")
	if env_path:
		return Path(env_path).expanduser().resolve()
	log.info("No environment variable for root path found, using project root")

	return Path(__file__).resolve().parent.parent


def init_storage(root_path: Path) -> Storage:
	"""
	Initialize directory structures and populate global storage container.

	Args:
		root_path: Absolute path to root project folder.

	Returns:
		Populated Storage object reference.
	"""
	global storage

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

	storage.dirs = dirs
	storage.env = root_path / ".env"
	storage.config = root_path / "config.py"
	storage.shared = shared
	storage.guilds = guilds
	storage.users = users

	return storage


async def validate_paths() -> None:
	"""
	Verify existence of critical configuration and environment files.

	Exits process with status code 10 if essential files are missing.
	"""
	critical_files = (
		storage.env,
		storage.config,
	)

	missing_files = [f for f in critical_files if not f.exists()]

	if missing_files:
		for f in missing_files:
			log.critical(f"Missing important file: {f}")

		if sys.stdin.isatty():
			from vion.tui import run_setup_wizard
			if run_setup_wizard(storage.dirs.root, force=True):
				if all(f.exists() for f in critical_files):
					return

		sys.exit(10)


async def setup_directory() -> None:
	"""
	Initialize filesystem paths, validate requirements, and create missing folders.
	"""
	global ROOT

	ROOT = resolve_root()
	init_storage(ROOT)

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
