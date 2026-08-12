import builtins
import logging
import sys
from typing import List, Tuple, Dict, Any, Callable, Literal, cast

import pytz

from core.lib.dataclass import Data, AntiFreeze
from core.lib.utils import F
from core.lib.file import yaml_file
from meta.paths import file


log = logging.getLogger(__name__)

real_import = builtins.__import__


class Config(Data):
	class Bot(Data):
		name: str
		id: int
		invite: str

	class Activity(Data):
		status: Literal["online", "idle", "dnd", "invisible"]
		type: int
		url: str
		range: Tuple[int, ...]
		list: List[str]

	class Sandbox(Data):
		allowed_modules: Tuple[str, ...]
		allowed_builtins: Dict[str, Callable]

	class Logging(Data):
		file: bool
		type: Literal["text", "html", "json"]
		cleanup_days: int

	class Settings(Data):
		server: dict
		user: dict

	class AIData(Data):
		server: dict
		user: dict

	class Secrets(Data):
		discord: str
		assemblyai: str
		hmac: str
		gemini: list[str]

	bot: Bot
	activity: Activity
	devs: List[Tuple[str, int]]
	dev_servers: List[Tuple[str, int, str]]
	domain: str
	timezone: Any
	default_prefix: Tuple[str, ...]
	sandbox: Sandbox
	logging: Logging
	max_prefix: int
	max_restore_file_size: int
	max_stm: int
	max_ltm: int
	max_previous_response: int
	max_audit: int
	ai_message_cooldown_seconds: int
	gemini_models: Tuple[str, ...]
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
	cmd: Data
	dev_server_ids: List[int]
	dev_ids: List[int]
	ial: str

class Emoji(Data):
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


config: Config = Config()
emoji: Emoji = Emoji()


async def load_config(reload: bool = False):
	global config, emoji
	log.info("Setting up config..." if not reload else "Reloading config...")

	if not yaml_file:
		log.critical("ial parser not found, please install the required dependencies")
		sys.exit(10)

	try:
		_, data = await yaml_file.load(file.conf, update_cache=False, use_cache=False)
	except Exception:
		log.critical(f"Failed to load {file.conf}", exc_info=True)
		sys.exit(10)

	try:
		preserved_cmd = config.cmd if reload and config.get('cmd') else Data()

		if reload:
			config.clear()
			emoji.clear()

		config.update(Data.load(data))
	except Exception:
		log.critical("An error occurred while parsing config into Data object", exc_info=True)
		sys.exit(10)

	allowed_prefixes = tuple(f"{m}." for m in config.sandbox.allowed_modules)
	allowed_exact = set(config.sandbox.allowed_modules)

	def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
		if name in allowed_exact or name.startswith(allowed_prefixes):
			return real_import(name, globals, locals, fromlist, level)
		raise ImportError(f"Module '{name}' is not allowed in sandbox")

	for parent in [config.settings, config.ai_data]:
		for attr in ['server', 'user']:
			val = getattr(parent, attr)
			setattr(parent, attr, AntiFreeze(val.to_dict()))

	for obj in [config.devs, config.dev_servers]:
		for i in range(len(obj)):
			if len(obj[i]) == 3:
				obj[i] = (obj[i][0], int(obj[i][1]), obj[i][2])
			else:
				obj[i] = (obj[i][0], int(obj[i][1]))

	config.dev_server_ids = [int(dsid) for _, dsid, _ in config.dev_servers]
	config.dev_ids = [int(did) for _, did in config.devs]

	emoji.update(Data.load(config.emoji.to_dict(update_self=False)))
	config.delete("emoji")

	config.activity.range = tuple(config.activity.range)
	config.timezone = pytz.timezone(config.timezone)

	_, secrets_data = await yaml_file.load(file.env)
	config.secrets = Data.load(secrets_data) # type: ignore

	config.sandbox.allowed_builtins = {name: getattr(builtins, name) for name in config.sandbox.allowed_builtins}
	config.sandbox.allowed_builtins["__import__"] = safe_import

	config.system_instructions = F(config.system_instructions).format(config=config)
	config.summary_instructions = F(config.summary_instructions).format(config=config)
	config.prompt_template = F(cast(str, config.prompt_template))

	config.cmd = preserved_cmd


__all__ = ('load_config', 'emoji', 'config')
