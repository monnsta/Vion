import builtins
import logging
import sys
import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, NoReturn, cast

import pytz
from discord.ext import commands

from core.lib.file import yaml_file
from core.lib.utils import F
from meta.paths import file


log = logging.getLogger(__name__)

real_import = builtins.__import__


class ConfigNode:
	def get(self, path: str, default: Any = None) -> Any:
		current: Any = self

		for part in path.split("."):
			if isinstance(current, ConfigNode):
				if not hasattr(current, part):
					return default
				current = getattr(current, part)

			elif isinstance(current, dict):
				if part not in current:
					return default
				current = current[part]

			else:
				return default

		return current

	def set(self, path: str, value: Any) -> None:
		parts = path.split(".")
		current: Any = self

		for part in parts[:-1]:
			if isinstance(current, ConfigNode):
				if not hasattr(current, part):
					setattr(current, part, ConfigNode())
				current = getattr(current, part)

			elif isinstance(current, dict):
				if part not in current:
					raise KeyError(
						f"Configuration path does not exist: {'.'.join(parts)}"
					)
				current = current[part]

			else:
				raise TypeError(
					f"Cannot traverse configuration through {part!r}"
				)

		last = parts[-1]

		if isinstance(current, ConfigNode):
			setattr(current, last, value)

		elif isinstance(current, dict):
			current[last] = value

		else:
			raise TypeError(f"Cannot set configuration path: {path}")

	def delete(self, path: str) -> None:
		parts = path.split(".")
		current: Any = self

		for part in parts[:-1]:
			if isinstance(current, ConfigNode):
				if not hasattr(current, part):
					return
				current = getattr(current, part)

			elif isinstance(current, dict):
				if part not in current:
					return
				current = current[part]

			else:
				return

		last = parts[-1]

		if isinstance(current, ConfigNode):
			if hasattr(current, last):
				delattr(current, last)

		elif isinstance(current, dict):
			current.pop(last, None)


@dataclass
class Bot(ConfigNode, commands.Bot):
	name: str
	id: int
	invite: str


@dataclass
class Activity(ConfigNode):
	status: Literal["online", "idle", "dnd", "invisible"]
	type: int
	url: str | None
	range: tuple[int, ...]
	list: list[str]


@dataclass
class Developer(ConfigNode):
	name: str
	id: int


@dataclass
class DeveloperServer(ConfigNode):
	name: str
	id: int
	invite: str


@dataclass
class Sandbox(ConfigNode):
	allowed_modules: list[str]
	allowed_builtins: list[str] | dict[str, Callable[..., Any]]


@dataclass
class Logging(ConfigNode):
	file: bool
	type: Literal["text", "html", "json"]
	cleanup_days: int


@dataclass
class Settings(ConfigNode):
	"""
	Runtime settings that intentionally remain JSON-compatible dictionaries.
	"""

	server: dict[str, Any]
	user: dict[str, Any]


@dataclass
class AIData(ConfigNode):
	"""
	Runtime AI data that intentionally remains JSON-compatible dictionaries.
	"""

	glob: dict[str, Any]
	server: dict[str, Any]
	user: dict[str, Any]


@dataclass
class Secrets(ConfigNode):
	discord: str
	assemblyai: str
	hmac: str
	gemini: list[str]


@dataclass
class Emoji(ConfigNode):
	checkmark: str
	crossmark: str
	warn: str
	info: str

	arrow_left: str
	arrow_right: str
	double_arrow_left: str
	double_arrow_right: str

	refresh: str

	char_empty: str
	char_absolute_empty: str
	char_o: str
	char_x: str

	char_0: str
	char_1: str
	char_2: str
	char_3: str
	char_4: str
	char_5: str
	char_6: str
	char_7: str
	char_8: str
	char_9: str

	avatar_airnomad: str
	avatar_earthkingdom: str
	avatar_firenation: str
	avatar_watertribe: str


@dataclass
class Config(ConfigNode):
	bot: Bot
	activity: Activity
	devs: list[Developer]
	dev_servers: list[DeveloperServer]

	domain: str
	timezone: Any

	sandbox: Sandbox
	logging: Logging

	max_restore_file_size: int

	max_stm: int
	max_ltm: int
	max_previous_response: int
	max_audit: int
	event_cooldown: int
	ai_message_cooldown_seconds: int

	gemini_models: tuple[str, ...]
	free_will_frequency: float
	temperature: float
	top_p: float
	top_k: int

	settings: Settings
	ai_data: AIData

	prompt_template: F
	fallback_response: str
	system_instructions: str
	summary_instructions: str

	secrets: Secrets

	emoji: Emoji

	cmd: ConfigNode = ConfigNode()

	dev_server_ids: list[int] = field(default_factory=list)
	dev_ids: list[int] = field(default_factory=list)


config: Config = Config.__new__(Config)
emoji: Emoji = Emoji.__new__(Emoji)


class ConfigReloadError(Exception):
	"""Raised when reloading the configuration fails."""


def _require_mapping(data: Any, name: str) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise TypeError(f"Configuration section '{name}' must be a mapping, got {type(data).__name__}")

	return data


def _build_secrets(data: dict[str, Any]) -> Secrets:
	return Secrets(
		discord=str(data["discord"]),
		assemblyai=str(data["assemblyai"]),
		hmac=str(data["hmac"]),
		gemini=[str(key) for key in data["gemini"]],
	)


def _build_emoji(data: dict[str, Any]) -> Emoji:
	return Emoji(
		checkmark=data["checkmark"],
		crossmark=data["crossmark"],
		warn=data["warn"],
		info=data["info"],

		arrow_left=data["arrow_left"],
		arrow_right=data["arrow_right"],
		double_arrow_left=data["double_arrow_left"],
		double_arrow_right=data["double_arrow_right"],

		refresh=data["refresh"],

		char_empty=data["char_empty"],
		char_absolute_empty=data["char_absolute_empty"],
		char_o=data["char_o"],
		char_x=data["char_x"],

		char_0=data["char_0"],
		char_1=data["char_1"],
		char_2=data["char_2"],
		char_3=data["char_3"],
		char_4=data["char_4"],
		char_5=data["char_5"],
		char_6=data["char_6"],
		char_7=data["char_7"],
		char_8=data["char_8"],
		char_9=data["char_9"],

		avatar_airnomad=data["avatar_airnomad"],
		avatar_earthkingdom=data["avatar_earthkingdom"],
		avatar_firenation=data["avatar_firenation"],
		avatar_watertribe=data["avatar_watertribe"],
	)


def _build_config(
	data: dict[str, Any],
	secrets: Secrets,
	preserved_cmd: ConfigNode | None = None,
) -> Config:
	bot_data = _require_mapping(data["bot"], "bot")
	activity_data = _require_mapping(data["activity"], "activity")
	sandbox_data = _require_mapping(data["sandbox"], "sandbox")
	logging_data = _require_mapping(data["logging"], "logging")
	settings_data = _require_mapping(data["settings"], "settings")
	ai_data = _require_mapping(data["ai_data"], "ai_data")

	settings_server = _require_mapping(settings_data["server"], "settings.server")
	settings_user = _require_mapping(settings_data["user"], "settings.user")

	ai_glob = _require_mapping(ai_data["glob"], "ai_data.glob")
	ai_server = _require_mapping(ai_data["server"], "ai_data.server")
	ai_user = _require_mapping(ai_data["user"], "ai_data.user")

	devs = [
		Developer(
			name=str(item[0]),
			id=int(item[1]),
		)
		for item in data["devs"]
	]

	dev_servers = [
		DeveloperServer(
			name=str(item[0]),
			id=int(item[1]),
			invite=str(item[2]),
		)
		for item in data["dev_servers"]
	]

	activity = Activity(
		status=activity_data["status"],
		type=int(activity_data["type"]),
		url=activity_data.get("url"),
		range=tuple(int(value) for value in activity_data["range"]),
		list=list(activity_data["list"]),
	)

	sandbox = Sandbox(
		allowed_modules=list(sandbox_data["allowed_modules"]),
		allowed_builtins=list(sandbox_data["allowed_builtins"]),
	)

	config = Config(
		bot=Bot(
			name=str(bot_data["name"]),
			id=int(bot_data["id"]),
			invite=str(bot_data["invite"])
		),

		activity=activity,

		devs=devs,
		dev_servers=dev_servers,

		domain=str(data["domain"]),
		timezone=pytz.timezone(str(data["timezone"])),

		sandbox=sandbox,

		logging=Logging(
			file=bool(logging_data["file"]),
			type=logging_data["type"],
			cleanup_days=int(logging_data["cleanup_days"]),
		),

		max_restore_file_size=int(data["max_restore_file_size"]),

		max_stm=int(data["max_stm"]),
		max_ltm=int(data["max_ltm"]),
		max_previous_response=int(data["max_previous_response"]),
		max_audit=int(data["max_audit"]),
		event_cooldown=int(data["event_cooldown"]),
		ai_message_cooldown_seconds=int(data.get("ai_message_cooldown_seconds", 5)),

		gemini_models=tuple(str(model) for model in data["gemini_models"]),

		free_will_frequency=float(data["free_will_frequency"]),
		temperature=float(data["temperature"]),
		top_p=float(data["top_p"]),
		top_k=int(data["top_k"]),

		settings=Settings(
			server=settings_server,
			user=settings_user,
		),

		ai_data=AIData(
			glob=ai_glob,
			server=ai_server,
			user=ai_user,
		),

		prompt_template=F(cast(str, data["prompt_template"])),
		fallback_response=str(data["fallback_response"]),
		system_instructions=str(data["system_instructions"]),
		summary_instructions=str(data["summary_instructions"]),

		secrets=secrets,

		emoji=_build_emoji(_require_mapping(data["emoji"], "emoji")),

		cmd=copy.deepcopy(preserved_cmd) if preserved_cmd else ConfigNode(),
	)

	# Derived values.
	config.dev_server_ids = [
		server.id
		for server in config.dev_servers
	]

	config.dev_ids = [
		developer.id
		for developer in config.devs
	]

	# Convert sandbox configuration into its runtime representation.
	allowed_modules = tuple(config.sandbox.allowed_modules)

	allowed_exact = set(allowed_modules)
	allowed_prefixes = tuple(
		f"{module}."
		for module in allowed_modules
	)

	def safe_import(
		name: str,
		globals: dict[str, Any] | None = None,
		locals: dict[str, Any] | None = None,
		fromlist: tuple[str, ...] = (),
		level: int = 0,
	):
		if name in allowed_exact or name.startswith(allowed_prefixes):
			return real_import(
				name,
				globals,
				locals,
				fromlist,
				level,
			)

		raise ImportError(
			f"Module '{name}' is not allowed in sandbox"
		)

	config.sandbox.allowed_modules = list(allowed_modules)

	config.sandbox.allowed_builtins = {
		name: getattr(builtins, name)
		for name in config.sandbox.allowed_builtins
		if hasattr(builtins, name)
	}

	config.sandbox.allowed_builtins["__import__"] = safe_import

	# Format configuration-dependent prompts only after the complete
	# Config object exists.
	config.system_instructions = F(
		config.system_instructions
	).format(config=config)

	config.summary_instructions = F(
		config.summary_instructions
	).format(config=config)

	return config


async def load_config(reload: bool = False):
	global config, emoji

	log.info("Setting up config..." if not reload else "Reloading config...")

	def handle_error(msg: str, exc: Exception | None = None) -> NoReturn:
		log.critical(msg, exc_info=exc if exc else True)

		if reload:
			raise ConfigReloadError(msg) from exc

		sys.exit(10)

	if not yaml_file:
		handle_error("yaml parser not found, please install the required dependencies")

	try:
		_, data = await yaml_file.load(
			file.conf,
			update_cache=False,
			use_cache=False,
		)

		if not isinstance(data, dict):
			raise TypeError(f"Expected {file.conf} to contain a mapping, got {type(data).__name__}")

	except ConfigReloadError:
		raise

	except Exception as e:
		handle_error(f"Failed to load {file.conf}", exc=e)

	try:
		_, secrets_data = await yaml_file.load(file.env)

		if not isinstance(secrets_data, dict):
			raise TypeError(f"Expected {file.env} to contain a mapping, got {type(secrets_data).__name__}")

		secrets = _build_secrets(secrets_data)

	except ConfigReloadError:
		raise

	except Exception as e:
		handle_error(f"Failed to load {file.env}", exc=e)

	preserved_cmd: ConfigNode | None = None

	if reload and config is not None:
		preserved_cmd = copy.deepcopy(config.cmd)

	try:
		new_config = _build_config(
			data,
			secrets,
			preserved_cmd,
		)

	except ConfigReloadError:
		raise

	except Exception as e:
		handle_error("An error occurred while parsing configuration", exc=e)

	config.__dict__.update(new_config.__dict__)
	emoji.__dict__.update(new_config.emoji.__dict__)

	log.info(f"Configuration {"reloaded" if reload else "loaded"} successfully.")


__all__ = (
	"ConfigNode",

	"Activity",
	"Developer",
	"DeveloperServer",
	"Sandbox",
	"Logging",
	"Settings",
	"AIData",
	"Secrets",
	"Emoji",
	"Config",

	"ConfigReloadError",

	"load_config",

	"emoji",
	"config",
)
