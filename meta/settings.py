import builtins
import ial
import json
import logging
import sys

import pytz

from core.lib.dataclass import Data, AntiFreeze
from core.lib.utils import F
from core.lib.file import ial_file
from meta.paths import file


log = logging.getLogger(__name__)

real_import = builtins.__import__


config = Data()
emoji  = Data()


async def load_config():
	global config, emoji
	log.info("Setting up config...")
	if not ial_file:
		log.critical("ial parser not found, please install the required dependencies")
		sys.exit(10)
	try:
		success, data = await ial_file.load(file.conf, update_cache=False, use_cache=False)
	except ial.MultiError as e:
		for i, error in enumerate(e.errors):
			log.error(f"{i}. {error}", exc_info=True)

	if not success: # type: ignore
		log.critical(f"Failed to load {file.conf}")
		sys.exit(10)

	try:
		config.update(Data.load(data)) # type: ignore
	except Exception:
		log.critical("An error occurred while parsing config into Data object", exc_info=True)
		sys.exit(10)

	log.debug(json.dumps({k: v for k, v in data.items() if k != "system_instructions"})) #type: ignore

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
			obj[i] = tuple(obj[i])

	config.dev_server_ids = [dsid for _, dsid, _ in config.dev_servers]
	config.dev_ids = [did for _, did in config.devs]

	emoji.update(Data.load(config.emoji.to_dict(update_self=False)))
	config.delete("emoji")

	config.activity.range = tuple(config.activity.range)
	config.timezone = pytz.timezone(config.timezone)

	_, secrets_data = await ial_file.load(file.env)
	config.secrets = Data.load(secrets_data)

	config.sandbox.allowed_builtins = {name: getattr(builtins, name) for name in config.sandbox.allowed_builtins}
	config.sandbox.allowed_builtins["__import__"] = safe_import

	config.system_instructions = F(config.system_instructions).format()
	config.prompt_template = F(config.prompt_template)

	config.cmd = Data()


__all__ = ('load_config', 'emoji', 'config')
