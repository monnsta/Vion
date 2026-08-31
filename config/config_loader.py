import builtins
import logging
import sys
import copy
import importlib.util
from typing import Any, NoReturn

from infrastructure.utils import F
from infrastructure.file import yaml_file
from .paths import storage
from .dataclasses import (
	ConfigReloadError,
	ConfigNode,

	Bot,
	Activity,
	Sandbox,
	Logging,
	Settings,
	AIData,
	Secrets,

	Config,
	Emoji
)


log = logging.getLogger("config")

real_import = builtins.__import__


config: Config = Config.__new__(Config)
emoji: Emoji = Emoji.__new__(Emoji)

config.bot = Bot.__new__(Bot)
config.activity = Activity.__new__(Activity)
config.sandbox = Sandbox.__new__(Sandbox)
config.logging = Logging.__new__(Logging)
config.settings = Settings.__new__(Settings)
config.ai_data = AIData.__new__(AIData)
config.secrets = Secrets.__new__(Secrets)
config.cmd = ConfigNode()


async def load_config(reload: bool = False):
	global config, emoji

	log.info("Setting up config..." if not reload else "Reloading config...")

	def handle_error(msg: str, exc: Exception | None = None) -> NoReturn:
		log.critical(msg, exc_info=exc if exc else True)
		if reload:
			raise ConfigReloadError(msg) from exc
		sys.exit(10)

	if not storage.config.exists():
		handle_error(f"Configuration file missing: {storage.config}")

	config_dir = str(storage.config.parent)
	if config_dir not in sys.path:
		sys.path.insert(0, config_dir)

	try:
		spec = importlib.util.spec_from_file_location("user_config", storage.config)
		if not spec or not spec.loader:
			raise ImportError("Failed to create module spec for config.")

		user_config = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(user_config)

	except ConfigReloadError:
		raise
	except Exception as e:
		handle_error(f"Failed to load user config from {storage.config}", exc=e)

	if hasattr(config, "sandbox") and getattr(config.sandbox, "allowed_modules", None):
		allowed_modules = tuple(config.sandbox.allowed_modules)
		allowed_exact = set(allowed_modules)
		allowed_prefixes = tuple(f"{module}." for module in allowed_modules)

		def safe_import(
			name: str,
			globals: dict[str, Any] | None = None,
			locals: dict[str, Any] | None = None,
			fromlist: tuple[str, ...] = (),
			level: int = 0,
		):
			if name in allowed_exact or name.startswith(allowed_prefixes):
				return real_import(name, globals, locals, fromlist, level)
			raise ImportError(f"Module '{name}' is not allowed in sandbox")

		config.sandbox.allowed_modules = list(allowed_modules)
		if hasattr(config.sandbox, "allowed_builtins"):
			if isinstance(config.sandbox.allowed_builtins, (list, tuple, set)):
				config.sandbox.allowed_builtins = {
					name: getattr(builtins, name)
					for name in config.sandbox.allowed_builtins
					if hasattr(builtins, name)
				}
			config.sandbox.allowed_builtins["__import__"] = safe_import

	if hasattr(config, "emoji") and config.emoji:
		emoji.__dict__.update(config.emoji.__dict__)

	if getattr(config, "system_instructions", None):
		config.system_instructions = F(config.system_instructions).format(config=config)

	if getattr(config, "summary_instructions", None):
		config.summary_instructions = F(config.summary_instructions).format(config=config)

	_, secrets_data = await yaml_file.load(storage.env)
	config.secrets = Secrets(
		discord=secrets_data["discord"],
		assemblyai=secrets_data["assemblyai"],
		hmac=secrets_data["hmac"],
		gemini=secrets_data["gemini"]
	)

	log.info(f"Configuration {'reloaded' if reload else 'loaded'} successfully.")
