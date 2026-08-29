import builtins
import logging
import sys
import copy
from typing import Any, NoReturn, cast

import pytz

from infrastructure.file import yaml_file
from infrastructure.utils import F
from .paths import storage
from .dataclasses import (
	ConfigReloadError,
	ConfigNode,

	Secrets,
	Developer,
	DeveloperServer,
	Activity,
	Logging,
	Sandbox,
	Bot,
	Settings,
	AIData,

	Config,
	Emoji
)


log = logging.getLogger("config")

real_import = builtins.__import__


config: Config = Config.__new__(Config)
emoji: Emoji = Emoji.__new__(Emoji)




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
			storage.config,
			update_cache=False,
			use_cache=False,
		)

		if not isinstance(data, dict):
			raise TypeError(f"Expected {storage.config} to contain a mapping, got {type(data).__name__}")

	except ConfigReloadError:
		raise

	except Exception as e:
		handle_error(f"Failed to load {storage.config}", exc=e)

	try:
		_, secrets_data = await yaml_file.load(storage.env)

		if not isinstance(secrets_data, dict):
			raise TypeError(f"Expected {storage.env} to contain a mapping, got {type(secrets_data).__name__}")

		secrets = _build_secrets(secrets_data)

	except ConfigReloadError:
		raise

	except Exception as e:
		handle_error(f"Failed to load {storage.env}", exc=e)

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
