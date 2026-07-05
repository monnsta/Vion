import logging
import sys
from pathlib import Path

from core.lib.utils import create_path


log = logging.getLogger(__name__)

root = Path(__file__).resolve().parent.parent


class Base:
	def __init__(self) -> None:
		self.core = root / "core"
		self.meta = root / "meta"
		self.data = root / "data"
		self.logs = root / "logs"

	@property
	def asset(self) -> Path:
		return self.meta / "asset"


class Sub:
	def __init__(self, base: Base) -> None:
		self.base    = base

		self.trash   = base.data / "trash"
		self.glob    = base.data / "global"
		self.servers = base.data / "servers"
		self.users   = base.data / "users"
		self.cog     = base.core / "cog"

	@property
	def avatar(self) -> Path:
		return self.base.asset / "avatars"

	def custom_cogs(self, i: str) -> Path:
		return self.servers / i / "cog"


class File:
	def __init__(self, sub: Sub) -> None:
		self.sub    = sub

		self.server = self.ServerFiles(self)
		self.user   = self.UserFiles(self)
		self.glob   = self.GlobalFiles(self)

		self.env    = root / ".env"
		self.conf   = root / "config.ial"

	class ServerFiles:
		def __init__(self, parent: 'File') -> None:
			self.parent = parent

		def settings(self, i: str) -> Path:
			return self.parent.sub.servers / i / "settings.json"

		def ai_data(self, i: str) -> Path:
			return self.parent.sub.servers / i / "ai_data.json"

		def delete_time(self, i: str) -> Path:
			return self.parent.sub.trash / i / "delete_time.json"

		def cog(self, i: str) -> Path:
			return self.parent.sub.custom_cogs(i) / "__init__.py"

		def data(self, i: str) -> Path:
			return self.parent.sub.custom_cogs(i) / "data.json"

	class UserFiles:
		def __init__(self, parent: 'File') -> None:
			self.parent = parent

		def settings(self, i: str) -> Path:
			return self.parent.sub.users / i / "settings.json"

		def ai_data(self, i: str) -> Path:
			return self.parent.sub.users / i / "ai_data.json"

		def delete_time(self, i: str) -> Path:
			return self.parent.sub.trash / i / "delete_time.json"

	class GlobalFiles:
		def __init__(self, parent: 'File') -> None:
			self.blacklist    = parent.sub.glob / "blacklist.json"
			self.bot_activity = parent.sub.glob / "bot_activity.json"


base = Base()
sub = Sub(base)
file = File(sub)


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


__all__ = (
	'setup_directory', 'create_path',
	'base', 'sub', 'file'
)
